"""Evapotranspiration and the seasonal water balance.

Water is the reason agrivoltaics might work better in Maharashtra than in the
European trials the field grew out of. Shade costs a crop light, which costs
yield. Shade also cuts evapotranspiration, which in a water-limited system buys
yield back. Where the second effect dominates, the sign of the whole
intervention flips.

Reference evapotranspiration follows FAO-56 Penman-Monteith in full -- the
Hargreaves shortcut is not usable here, because the shortcut's whole point is
avoiding the radiation term and the radiation term is exactly what the array
modifies.

Reference: Allen et al. (1998), FAO Irrigation and Drainage Paper 56.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SOLAR_CONSTANT = 0.0820        # MJ / m2 / min
STEFAN_BOLTZMANN = 4.903e-9    # MJ / K4 / m2 / day
ALBEDO_REFERENCE_CROP = 0.23
SOIL_HEAT_FLUX_DAILY = 0.0     # negligible at a daily step

# Wind under an elevated array is slowed by the row structure. 0.8 is the
# mid-range of reported reductions; it is a modest term next to radiation.
SHELTERED_WIND_FACTOR = 0.80


def _saturation_vapour_pressure(temp_c):
    """Saturation vapour pressure at temperature, kPa. FAO-56 eq. 11."""
    return 0.6108 * np.exp(17.27 * temp_c / (temp_c + 237.3))


def _slope_vapour_pressure_curve(temp_c):
    """Slope of the saturation vapour pressure curve, kPa/degC. FAO-56 eq. 13."""
    return 4098 * _saturation_vapour_pressure(temp_c) / (temp_c + 237.3) ** 2


def _psychrometric_constant(altitude_m: float) -> float:
    """Psychrometric constant, kPa/degC. FAO-56 eq. 7 and 8."""
    pressure_kpa = 101.3 * ((293 - 0.0065 * altitude_m) / 293) ** 5.26
    return 0.665e-3 * pressure_kpa


def extraterrestrial_radiation(day_of_year, latitude_deg: float):
    """Radiation at the top of the atmosphere, MJ/m2/day. FAO-56 eq. 21.

    Needed only to work out how clear the sky was, which in turn sets net
    longwave loss.
    """
    phi = np.radians(latitude_deg)
    doy = np.asarray(day_of_year, dtype=float)
    inverse_distance = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    declination = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    # Clipped for latitudes and seasons where the sun does not set or rise.
    sunset_hour_angle = np.arccos(np.clip(-np.tan(phi) * np.tan(declination), -1, 1))
    return (
        (24 * 60 / np.pi)
        * SOLAR_CONSTANT
        * inverse_distance
        * (
            sunset_hour_angle * np.sin(phi) * np.sin(declination)
            + np.cos(phi) * np.cos(declination) * np.sin(sunset_hour_angle)
        )
    )


def reference_evapotranspiration(daily: pd.DataFrame, latitude: float,
                                 altitude_m: float = 0.0,
                                 radiation_scale: float = 1.0,
                                 wind_scale: float = 1.0) -> pd.Series:
    """Daily reference evapotranspiration, mm/day. FAO-56 eq. 6.

    `radiation_scale` and `wind_scale` are how the array enters the water
    balance: pass the canopy light transmission ratio and
    `SHELTERED_WIND_FACTOR` to get ET0 underneath the modules, or leave both at
    1.0 for the open field.
    """
    temp_mean = daily["temp_mean"]
    temp_max = daily["temp_max"]
    temp_min = daily["temp_min"]
    wind = daily["wind_speed"] * wind_scale
    solar = daily["solar_radiation"] * radiation_scale

    saturation = (
        _saturation_vapour_pressure(temp_max) + _saturation_vapour_pressure(temp_min)
    ) / 2
    actual = saturation * daily["relative_humidity"] / 100
    vapour_deficit = (saturation - actual).clip(lower=0)

    clear_sky = (0.75 + 2e-5 * altitude_m) * extraterrestrial_radiation(
        daily.index.dayofyear, latitude
    )
    # Cloudiness is a property of the sky, so it is judged on open-field
    # radiation even when the canopy is shaded by the array.
    cloudiness = (daily["solar_radiation"] / clear_sky).clip(0.3, 1.0)

    net_shortwave = (1 - ALBEDO_REFERENCE_CROP) * solar
    net_longwave = (
        STEFAN_BOLTZMANN
        * (((temp_max + 273.16) ** 4 + (temp_min + 273.16) ** 4) / 2)
        * (0.34 - 0.14 * np.sqrt(actual))
        * (1.35 * cloudiness - 0.35)
    )
    net_radiation = net_shortwave - net_longwave

    slope = _slope_vapour_pressure_curve(temp_mean)
    gamma = _psychrometric_constant(altitude_m)

    radiation_term = 0.408 * slope * (net_radiation - SOIL_HEAT_FLUX_DAILY)
    aerodynamic_term = gamma * (900 / (temp_mean + 273)) * wind * vapour_deficit

    et0 = (radiation_term + aerodynamic_term) / (slope + gamma * (1 + 0.34 * wind))
    return et0.clip(lower=0).rename("et0_mm")


def water_balance(precipitation: pd.Series, crop_et: pd.Series,
                  irrigation_mm: float = 0.0,
                  effective_rain_fraction: float = 0.75) -> dict[str, float]:
    """Season totals of supply against demand, all in mm.

    Rainfall is discounted to an effective fraction: on the lateritic slopes of
    the Konkan a large share of monsoon rain runs off rather than entering the
    root zone. `relative_transpiration` is the ratio the FAO-33 yield response
    consumes, capped at 1 because surplus water does not raise yield.
    """
    demand = float(crop_et.sum())
    effective_rain = float(precipitation.sum()) * effective_rain_fraction
    supply = effective_rain + irrigation_mm
    return {
        "crop_water_demand_mm": round(demand, 1),
        "effective_rainfall_mm": round(effective_rain, 1),
        "irrigation_mm": round(irrigation_mm, 1),
        "deficit_mm": round(max(demand - supply, 0.0), 1),
        "relative_transpiration": round(min(supply / demand, 1.0) if demand > 0 else 1.0, 4),
    }
