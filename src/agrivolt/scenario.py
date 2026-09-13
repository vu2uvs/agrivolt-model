"""Compose the stages into one runnable scenario.

A scenario is a YAML file: a site, an array geometry, a weather window, and the
crops in the rotation. This module reads it, runs every year in the window
independently, and reports the spread as well as the mean -- a single-year
agrivoltaic number is close to meaningless when Indian rainfall varies by a
factor of two between years.

Nothing here does physics. If a calculation is happening in this file rather
than being delegated to one of the stage modules, that is a bug.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from . import crop as crop_model
from . import economics, irradiance, metrics, pv, shading, water
from .geometry import PanelArray
from .site import Site

# A conventional ground mount sits low; only agrivoltaic arrays pay for clearance.
CONVENTIONAL_CLEARANCE_M = 1.5


@dataclass(frozen=True)
class CropPlan:
    """One crop in the rotation, and what it costs to grow it here."""

    key: str
    irrigation_mm: float = 0.0
    grown_in_baseline: bool = True


def _conventional_array(array: PanelArray) -> PanelArray:
    """The same modules packed as a normal solar farm -- the energy denominator."""
    return PanelArray(
        collector_width=array.collector_width,
        pitch=array.collector_width / metrics.CONVENTIONAL_GCR,
        tilt=array.tilt,
        azimuth=array.azimuth,
        clearance_height=CONVENTIONAL_CLEARANCE_M,
        module_efficiency=array.module_efficiency,
        ground_utilisation=array.ground_utilisation,
    )


def _season_slice(frame: pd.DataFrame, season: pd.DatetimeIndex) -> pd.DataFrame:
    """Rows of `frame` falling inside the growing season."""
    return frame.loc[(frame.index >= season[0]) & (frame.index <= season[-1])]


def _run_crop(plan: CropPlan, crop: crop_model.Crop, year: int,
              canopy: pd.DataFrame, daily: pd.DataFrame, site: Site,
              cropped_area_ha: float) -> dict:
    """Model one crop for one season, both with and without the array."""
    season = crop.season_index(year)
    season_canopy = _season_slice(canopy, season)
    season_daily = _season_slice(daily, season)

    if season_canopy.empty or season_daily.empty:
        raise ValueError(
            f"weather does not cover the {crop.name} season starting {season[0].date()}"
        )

    transmission = shading.transmission_ratio(season_canopy)

    # The array modifies the water balance through radiation and through wind.
    et0_open = water.reference_evapotranspiration(
        season_daily, site.latitude, site.altitude_m
    )
    et0_shaded = water.reference_evapotranspiration(
        season_daily, site.latitude, site.altitude_m,
        radiation_scale=transmission,
        wind_scale=water.SHELTERED_WIND_FACTOR,
    )

    kc = crop.crop_coefficient_curve(year).reindex(season_daily.index).ffill().bfill()
    balance_open = water.water_balance(
        season_daily["precipitation"], et0_open * kc, plan.irrigation_mm
    )
    balance_shaded = water.water_balance(
        season_daily["precipitation"], et0_shaded * kc, plan.irrigation_mm
    )

    repro = crop.heat_sensitive_window(year)
    repro_temps = season_daily.loc[
        (season_daily.index >= repro[0]) & (season_daily.index <= repro[-1]), "temp_max"
    ]

    under_array = crop_model.estimate_yield(
        crop, transmission, balance_shaded["relative_transpiration"], repro_temps,
        shaded=True,
    )
    open_field = crop_model.estimate_yield(
        crop, 1.0, balance_open["relative_transpiration"], repro_temps, shaded=False,
    )

    baseline_yield = open_field.yield_t_ha if plan.grown_in_baseline else 0.0
    baseline_margin = (
        economics.crop_margin(
            baseline_yield, cropped_area_ha,
            crop.price_inr_per_tonne, crop.cultivation_cost_inr_per_ha,
        )
        if plan.grown_in_baseline
        else 0.0
    )

    return {
        "crop": crop.name,
        "season": crop.season,
        "light_transmission": round(transmission, 4),
        "under_array": under_array.as_dict(),
        "open_field": open_field.as_dict(),
        "grown_in_baseline": plan.grown_in_baseline,
        "baseline_yield_t_ha": round(baseline_yield, 3),
        "water": {
            "under_array": balance_shaded,
            "open_field": balance_open,
            "demand_reduction_mm": round(
                balance_open["crop_water_demand_mm"]
                - balance_shaded["crop_water_demand_mm"],
                1,
            ),
        },
        "margin_inr": round(
            economics.crop_margin(
                under_array.yield_t_ha, cropped_area_ha,
                crop.price_inr_per_tonne, crop.cultivation_cost_inr_per_ha,
            )
        ),
        "baseline_margin_inr": round(baseline_margin),
    }


def _run_year(year: int, site: Site, array: PanelArray, module: pv.ModuleSpec,
              plans: list[CropPlan], crops: dict[str, crop_model.Crop],
              hourly: pd.DataFrame, daily: pd.DataFrame) -> dict:
    """One weather year, start to finish."""
    solar_position = irradiance.solar_position(
        hourly.index, site.latitude, site.longitude, site.altitude_m
    )
    split = irradiance.decompose(hourly["ghi"], solar_position["apparent_zenith"])
    canopy = shading.canopy_irradiance(split, solar_position, array)

    capacity_kw = array.dc_capacity_kw(site.area_ha)
    energy = pv.generation(split, solar_position, hourly, array, module, capacity_kw)

    conventional = _conventional_array(array)
    conventional_capacity_kw = conventional.dc_capacity_kw(site.area_ha)
    conventional_energy = pv.generation(
        split, solar_position, hourly, conventional, module, conventional_capacity_kw
    )

    window = energy.index.year == year
    annual_kwh = float(energy[window].sum())
    conventional_kwh = float(conventional_energy[window].sum())

    cropped_area_ha = array.cropped_area_ha(site.area_ha)
    crop_results = [
        _run_crop(plan, crops[plan.key], year, canopy, daily, site, cropped_area_ha)
        for plan in plans
    ]

    total_margin = sum(result["margin_inr"] for result in crop_results)
    baseline_margin = sum(result["baseline_margin_inr"] for result in crop_results)

    # LER is reported against the crop that is actually grown here today. A crop
    # the array makes newly possible has no baseline to divide by.
    primary = next((r for r in crop_results if r["grown_in_baseline"]), crop_results[0])
    ler = metrics.land_equivalent_ratio(
        agrivoltaic_yield_t_ha=primary["under_array"]["yield_t_ha"],
        open_field_yield_t_ha=primary["baseline_yield_t_ha"],
        agrivoltaic_energy_kwh=annual_kwh,
        conventional_energy_kwh=conventional_kwh,
    )

    comparison = metrics.system_comparison(
        baseline_food_t=sum(
            r["baseline_yield_t_ha"] * cropped_area_ha for r in crop_results
        ),
        agrivoltaic_food_t=sum(
            r["under_array"]["yield_t_ha"] * cropped_area_ha for r in crop_results
        ),
        agrivoltaic_energy_kwh=annual_kwh,
    )

    return {
        "year": year,
        "energy": {
            "dc_capacity_kw": round(capacity_kw, 1),
            "annual_kwh": round(annual_kwh),
            "specific_yield_kwh_per_kwp": round(
                pv.specific_yield(annual_kwh, capacity_kw), 1
            ),
            "bifacial_gain_percent": round(
                100 * pv.bifacial_gain(split, solar_position, array, module), 2
            ),
            "conventional_baseline_kwh": round(conventional_kwh),
            "conventional_capacity_kw": round(conventional_capacity_kw, 1),
        },
        "crops": crop_results,
        "crop_margin_inr": total_margin,
        "baseline_crop_margin_inr": baseline_margin,
        "land_equivalent_ratio": ler.as_dict(),
        "system_comparison": comparison,
    }


def _spread(values: list) -> dict:
    """Mean and range across weather years."""
    clean = [v for v in values if v is not None]
    if not clean:
        return {"mean": None, "min": None, "max": None, "years": 0}
    return {
        "mean": round(statistics.fmean(clean), 4),
        "min": round(min(clean), 4),
        "max": round(max(clean), 4),
        "years": len(clean),
    }


def load(path: Path) -> dict:
    """Parse a scenario YAML into the objects the model runs on."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    site_config = dict(raw["site"])
    acres = site_config.pop("acres", None)
    site = (
        Site.from_acres(acres, **site_config) if acres is not None else Site(**site_config)
    )

    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "site": site,
        "array": PanelArray(**raw["array"]),
        "module": pv.ModuleSpec(**raw.get("module", {})),
        "plans": [CropPlan(**entry) for entry in raw["crops"]],
        "weather": raw["weather"],
    }


def run(path: Path, array: PanelArray | None = None) -> dict:
    """Run a scenario file and return the result document.

    `array` overrides the geometry in the file, which is how the pitch sweep
    reuses a scenario without writing a temporary file per candidate.
    """
    config = load(path)
    site: Site = config["site"]
    array = array or config["array"]
    start_year = config["weather"]["start_year"]
    end_year = config["weather"]["end_year"]

    hourly = site.hourly_weather(start_year, end_year)
    # Rabi seasons run past new year, so the daily record needs one extra year.
    daily = site.daily_weather(start_year, end_year + 1)

    crops = crop_model.load_crops()
    years = [
        _run_year(
            year, site, array, config["module"], config["plans"], crops, hourly, daily
        )
        for year in range(start_year, end_year + 1)
    ]

    assumptions = economics.FinanceAssumptions.load()
    mean_energy = statistics.fmean(y["energy"]["annual_kwh"] for y in years)
    mean_margin = statistics.fmean(y["crop_margin_inr"] for y in years)
    capacity_kw = array.dc_capacity_kw(site.area_ha)

    return {
        "scenario": config["name"],
        "description": config["description"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "site": {
            "name": site.name,
            "district": site.district,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "area_ha": round(site.area_ha, 3),
            "agroclimatic_zone": site.agroclimatic_zone,
        },
        "array": {
            "collector_width_m": array.collector_width,
            "pitch_m": array.pitch,
            "tilt_deg": array.tilt,
            "clearance_height_m": array.clearance_height,
            "gcr": round(array.gcr, 4),
            "dc_capacity_kw": round(capacity_kw, 1),
            "ground_sky_view_factor": round(shading.ground_sky_view_factor(array), 4),
        },
        "weather_years": [start_year, end_year],
        "across_years": {
            "annual_kwh": _spread([y["energy"]["annual_kwh"] for y in years]),
            "crop_margin_inr": _spread([y["crop_margin_inr"] for y in years]),
            "land_equivalent_ratio": _spread(
                [y["land_equivalent_ratio"]["total"] for y in years]
            ),
        },
        "economics": economics.summarise(
            capacity_kw, mean_energy, mean_margin, assumptions
        ),
        "years": years,
        "provenance": {
            "weather": "NASA POWER, hourly RE and daily AG communities",
            "tariff": "MERC order of 5 August 2026, MSKVY 2.0, weighted average",
            "crop_parameters": "config/crops.yaml -- literature midpoints, uncalibrated",
            "model_version": "0.1.0",
        },
    }
