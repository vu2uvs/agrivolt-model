"""Time-resolved profiles, for plotting rather than for a bottom line.

The scenario document answers "is this worth building". These answer "what does
a day under the array actually look like", which is the question people ask
second and the one that is far easier to show than to say.

Three profiles, all derived from the same hourly canopy irradiance the yield
model already consumes, so nothing here is a separate estimate that could drift
away from the headline numbers:

  diurnal  -- mean hourly open-field PAR, canopy PAR and DC power for a month
  monthly  -- how light transmission and generation move through the year
  heatmap  -- transmission on a month-by-hour grid

The heatmap is the one worth looking at. A single annual transmission figure
hides the fact that a December morning under the array is a fundamentally
different place from a June noon, and a crop experiences the grid, not the
average.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .geometry import PanelArray
from .pv import ModuleSpec, generation
from .shading import PAR_FRACTION, canopy_irradiance
from .site import Site

# Local time. POWER is UTC, and a plot of an Indian day labelled in UTC is
# actively misleading -- solar noon would land at half past six in the morning.
INDIA_UTC_OFFSET_HOURS = 5.5

# Below this the sun is effectively down and a transmission ratio computed from
# two near-zero numbers is noise, not information.
DAYLIGHT_THRESHOLD_WM2 = 20.0


def _to_local(frame: pd.DataFrame | pd.Series):
    return frame.tz_convert("Asia/Kolkata")


def diurnal(canopy: pd.DataFrame, power: pd.Series, month: int) -> dict:
    """Mean hourly profile for one month, in local time.

    Averaging a whole month rather than picking a single clear day is
    deliberate: a hand-picked day is a best case, and the mean is what the crop
    and the meter actually see.
    """
    local_canopy = _to_local(canopy)
    local_power = _to_local(power)

    selection = local_canopy.index.month == month
    by_hour = local_canopy[selection].groupby(local_canopy[selection].index.hour)
    power_by_hour = local_power[selection].groupby(local_power[selection].index.hour)

    hours = list(range(24))
    open_par = (by_hour["open_field"].mean() * PAR_FRACTION).reindex(hours, fill_value=0.0)
    canopy_par = (by_hour["total"].mean() * PAR_FRACTION).reindex(hours, fill_value=0.0)
    dc_power = power_by_hour.mean().reindex(hours, fill_value=0.0)

    return {
        "month": month,
        "hours": hours,
        "open_par_wm2": [round(v, 1) for v in open_par],
        "canopy_par_wm2": [round(v, 1) for v in canopy_par],
        "power_kw": [round(v, 1) for v in dc_power],
        "peak_open_par_wm2": round(float(open_par.max()), 1),
        "peak_power_kw": round(float(dc_power.max()), 1),
        "par_debit_percent": round(
            100 * (1 - canopy_par.sum() / open_par.sum()) if open_par.sum() else 0.0, 1
        ),
    }


def monthly(canopy: pd.DataFrame, power: pd.Series) -> dict:
    """Transmission and generation by calendar month."""
    local_canopy = _to_local(canopy)
    local_power = _to_local(power)

    grouped = local_canopy.groupby(local_canopy.index.month)
    transmission = grouped["total"].sum() / grouped["open_field"].sum()
    energy = local_power.groupby(local_power.index.month).sum()

    months = list(range(1, 13))
    return {
        "months": months,
        "transmission": [round(float(transmission.get(m, 0)), 4) for m in months],
        "mwh": [round(float(energy.get(m, 0)) / 1000, 1) for m in months],
    }


def transmission_heatmap(canopy: pd.DataFrame) -> dict:
    """Light transmission on a 12 x 24 month-by-hour grid, in local time.

    Cells where the sun is effectively down are returned as null rather than
    zero. A zero would plot as total shade, which is the opposite of true --
    there is simply no light to transmit, and colouring night as heavy shading
    would be a straightforwardly false picture.
    """
    local = _to_local(canopy)
    keyed = local.groupby([local.index.month, local.index.hour])[["total", "open_field"]].sum()

    grid = []
    for month in range(1, 13):
        row = []
        for hour in range(24):
            try:
                cell = keyed.loc[(month, hour)]
            except KeyError:
                row.append(None)
                continue
            # Mean W/m2 over the hours that contributed to this cell.
            open_field = cell["open_field"]
            row.append(
                round(float(cell["total"] / open_field), 4)
                if open_field > DAYLIGHT_THRESHOLD_WM2
                else None
            )
        grid.append(row)

    populated = [v for row in grid for v in row if v is not None]
    return {
        "months": list(range(1, 13)),
        "hours": list(range(24)),
        "grid": grid,
        "min": round(min(populated), 4) if populated else None,
        "max": round(max(populated), 4) if populated else None,
    }


def build(site: Site, array: PanelArray, module: ModuleSpec,
          hourly_weather: pd.DataFrame, split: pd.DataFrame,
          solar_position: pd.DataFrame, diurnal_month: int = 3) -> dict:
    """Every profile for one site and geometry."""
    canopy = canopy_irradiance(split, solar_position, array)
    power = generation(
        split, solar_position, hourly_weather, array, module,
        array.dc_capacity_kw(site.area_ha),
    )

    return {
        "diurnal": diurnal(canopy, power, diurnal_month),
        "monthly": monthly(canopy, power),
        "heatmap": transmission_heatmap(canopy),
    }
