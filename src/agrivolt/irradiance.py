"""Solar geometry and the split of global irradiance into beam and diffuse.

NASA POWER gives global horizontal irradiance only. Both the PV model and the
canopy light model need beam and diffuse separately, because a module row
intercepts the two very differently: beam arrives from one direction and casts
a hard shadow, diffuse arrives from the whole sky dome and leaks between rows.

The Erbs correlation is used for the split. It is the conservative choice for
hourly reanalysis input -- the sharper models (DIRINT, DISC) are tuned to
ground-station data of a quality that does not exist for rural Maharashtra.
"""

from __future__ import annotations

import pandas as pd
import pvlib


def solar_position(times: pd.DatetimeIndex, latitude: float, longitude: float,
                   altitude: float = 0.0) -> pd.DataFrame:
    """Apparent solar position. `times` must be timezone aware."""
    if times.tz is None:
        raise ValueError("times must be timezone aware; POWER data is UTC")
    return pvlib.solarposition.get_solarposition(times, latitude, longitude, altitude)


def decompose(ghi: pd.Series, solar_zenith: pd.Series) -> pd.DataFrame:
    """Split GHI into direct normal and diffuse horizontal, in W/m2."""
    split = pvlib.irradiance.erbs(ghi, solar_zenith, ghi.index)
    return pd.DataFrame({"ghi": ghi, "dni": split["dni"], "dhi": split["dhi"]})
