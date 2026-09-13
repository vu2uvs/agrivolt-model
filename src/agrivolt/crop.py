"""Crop response to life under a solar array.

Three channels, applied multiplicatively:

Light
    Less radiation reaches the canopy, so less biomass accumulates. Modelled as
    a power law in the transmission ratio. The exponent is the crop's shade
    sensitivity: near 1.0 for light-hungry C4 cereals whose photosynthesis is
    still climbing at full sun, well below 1.0 for legumes and alliums that
    saturate early and lose little to partial shade.

Water
    Shade cuts evapotranspiration. In a rainfed or deficit-irrigated system that
    closes part of the water gap and recovers yield. FAO-33's linear yield
    response to relative transpiration.

Heat
    The channel the European agrivoltaic literature has little reason to model
    and Indian sites cannot ignore. Yield in Maharashtra is frequently set by a
    handful of days when the canopy exceeds a crop's critical temperature during
    flowering or grain fill. A few degrees of shade cooling across those days is
    worth more than the light it costs.

The three are treated as independent, which they are not -- water stress and
heat stress compound in reality. The assumption is conservative for the water
and heat channels and so understates the agrivoltaic case rather than inflating
it. Replacing this with a coupled daily model (AquaCrop) is the top item on the
roadmap.

Parameter provenance is recorded per crop in `config/crops.yaml`. Values are
literature midpoints, not site calibrations, and are labelled as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

CROP_LIBRARY = Path(__file__).resolve().parents[2] / "config" / "crops.yaml"

# Maximum canopy cooling under a fully shading array, in kelvin. Field studies
# of agrivoltaic microclimate report 1-3 K; the model scales this by how much
# light the array actually intercepts.
MAX_CANOPY_COOLING_K = 3.0


@dataclass(frozen=True)
class GrowthStages:
    """FAO-56 four-stage crop calendar, lengths in days."""

    initial: int
    development: int
    mid: int
    late: int

    @property
    def total(self) -> int:
        return self.initial + self.development + self.mid + self.late


@dataclass(frozen=True)
class Crop:
    """A crop as the model needs to see it."""

    name: str
    season: str
    sowing_month: int
    sowing_day: int
    stages: GrowthStages
    kc_initial: float
    kc_mid: float
    kc_end: float
    yield_response_factor: float      # FAO-33 Ky
    shade_sensitivity: float          # exponent on the transmission ratio
    heat_sensitivity: float           # yield lost per unit stressed-day fraction
    critical_temp_c: float            # canopy temperature above which yield is hurt
    reference_yield_t_ha: float       # open-field district average
    price_inr_per_tonne: float
    cultivation_cost_inr_per_ha: float
    source: str = ""
    notes: str = ""

    def sowing_date(self, year: int) -> date:
        return date(year, self.sowing_month, self.sowing_day)

    def season_index(self, year: int) -> pd.DatetimeIndex:
        start = pd.Timestamp(self.sowing_date(year), tz="UTC")
        return pd.date_range(start, periods=self.stages.total, freq="D")

    def crop_coefficient_curve(self, year: int) -> pd.Series:
        """Daily Kc across the season, FAO-56 piecewise linear."""
        s = self.stages
        curve = np.concatenate([
            np.full(s.initial, self.kc_initial),
            np.linspace(self.kc_initial, self.kc_mid, s.development, endpoint=False),
            np.full(s.mid, self.kc_mid),
            np.linspace(self.kc_mid, self.kc_end, s.late),
        ])
        return pd.Series(curve, index=self.season_index(year), name="kc")

    def heat_sensitive_window(self, year: int) -> pd.DatetimeIndex:
        """Flowering through grain fill -- the stages heat actually damages.

        This spans the mid and late stages together, not just the mid one. The
        distinction matters: terminal heat stress in chickpea and wheat is
        specifically a grain-filling phenomenon, and a rabi crop sown in October
        reaches grain fill in February, when Vidarbha and Marathwada start
        running above 35 C. Scoping the window to the mid stage alone ends it in
        January and misses the event entirely.
        """
        index = self.season_index(year)
        start = self.stages.initial + self.stages.development
        return index[start:]


def load_crops(path: Path | None = None) -> dict[str, Crop]:
    """Read the crop library from YAML."""
    raw = yaml.safe_load((path or CROP_LIBRARY).read_text(encoding="utf-8"))
    crops = {}
    for key, entry in raw["crops"].items():
        stages = GrowthStages(**entry.pop("stages"))
        crops[key] = Crop(name=key, stages=stages, **entry)
    return crops


def light_factor(transmission: float, crop: Crop) -> float:
    """Relative yield from available light alone."""
    return float(np.clip(transmission, 0.0, 1.0) ** crop.shade_sensitivity)


def water_factor(relative_transpiration: float, crop: Crop) -> float:
    """Relative yield from water supply alone. FAO-33 eq. 1."""
    loss = crop.yield_response_factor * (1.0 - relative_transpiration)
    return float(np.clip(1.0 - loss, 0.0, 1.0))


def heat_factor(daily_temp_max: pd.Series, crop: Crop, cooling_k: float = 0.0) -> float:
    """Relative yield from heat stress during the reproductive window.

    `cooling_k` is how many kelvin the array takes off canopy temperature.
    """
    if daily_temp_max.empty:
        return 1.0
    stressed = (daily_temp_max - cooling_k) > crop.critical_temp_c
    stressed_fraction = float(stressed.mean())
    return float(np.clip(1.0 - crop.heat_sensitivity * stressed_fraction, 0.0, 1.0))


def canopy_cooling(transmission: float) -> float:
    """Kelvin of canopy cooling delivered by an array of a given transmission."""
    return MAX_CANOPY_COOLING_K * (1.0 - float(np.clip(transmission, 0.0, 1.0)))


@dataclass
class YieldEstimate:
    """A yield estimate with its three drivers kept visible.

    The components matter as much as the total: they are what tells you whether
    a site works because of water, because of heat, or not at all.
    """

    crop: str
    light_factor: float
    water_factor: float
    heat_factor: float
    relative_yield: float
    yield_t_ha: float
    canopy_cooling_k: float
    drivers: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "crop": self.crop,
            "relative_yield": round(self.relative_yield, 4),
            "yield_t_ha": round(self.yield_t_ha, 3),
            "factors": {
                "light": round(self.light_factor, 4),
                "water": round(self.water_factor, 4),
                "heat": round(self.heat_factor, 4),
            },
            "canopy_cooling_k": round(self.canopy_cooling_k, 2),
            **self.drivers,
        }


def estimate_yield(crop: Crop, transmission: float, relative_transpiration: float,
                   season_temp_max: pd.Series, shaded: bool = True) -> YieldEstimate:
    """Combine the three channels into a yield.

    Pass `shaded=False` to get the open-field baseline, which uses the same code
    path with no light reduction and no cooling -- so the comparison cannot drift
    between the two arms.
    """
    effective_transmission = transmission if shaded else 1.0
    cooling = canopy_cooling(transmission) if shaded else 0.0

    light = light_factor(effective_transmission, crop)
    water = water_factor(relative_transpiration, crop)
    heat = heat_factor(season_temp_max, crop, cooling)
    relative = light * water * heat

    return YieldEstimate(
        crop=crop.name,
        light_factor=light,
        water_factor=water,
        heat_factor=heat,
        relative_yield=relative,
        yield_t_ha=relative * crop.reference_yield_t_ha,
        canopy_cooling_k=cooling,
    )
