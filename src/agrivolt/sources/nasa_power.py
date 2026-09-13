"""NASA POWER — solar irradiance and meteorology.

POWER is the backbone of this model: global coverage, no API key, a record
going back to 1981, and an agroclimatology community that already serves the
variables FAO-56 wants. Indian ground stations with public hourly irradiance
essentially do not exist, so a reanalysis product is the honest starting point.

Two granularities are used:

  * hourly  -- drives the PV and shading calculation, which needs solar position
  * daily   -- drives the water balance and crop model

Timestamps are UTC. Solar position is derived from UTC plus longitude by pvlib,
which avoids every local-time and daylight-saving ambiguity. Convert to
Asia/Kolkata only for display.

Docs: https://power.larc.nasa.gov/docs/services/api/temporal/
"""

from __future__ import annotations

import pandas as pd

from .cache import fetch_json

BASE = "https://power.larc.nasa.gov/api/temporal"

FILL_VALUE = -999.0

# POWER caps an hourly point request at roughly a year, so requests are chunked.
HOURLY_CHUNK_YEARS = 1

HOURLY_PARAMETERS = (
    "ALLSKY_SFC_SW_DWN",  # global horizontal irradiance, W/m2
    "T2M",                # air temperature at 2 m, degC
    "WS2M",               # wind speed at 2 m, m/s
    "RH2M",               # relative humidity at 2 m, %
)

DAILY_PARAMETERS = (
    "ALLSKY_SFC_SW_DWN",  # MJ/m2/day
    "T2M",                # degC
    "T2M_MAX",
    "T2M_MIN",
    "RH2M",               # %
    "WS2M",               # m/s
    "PRECTOTCORR",        # mm/day
)


def _to_frame(payload: dict, index_format: str) -> pd.DataFrame:
    parameters = payload["properties"]["parameter"]
    frame = pd.DataFrame(parameters)
    frame.index = pd.to_datetime(frame.index, format=index_format, utc=True)
    frame.index.name = "timestamp"
    return frame.replace(FILL_VALUE, pd.NA).astype("float64").sort_index()


def _request(temporal: str, lat: float, lon: float, start: str, end: str,
             parameters: tuple[str, ...], community: str, index_format: str) -> pd.DataFrame:
    payload = fetch_json(
        f"{BASE}/{temporal}/point",
        {
            "parameters": ",".join(parameters),
            "community": community,
            "latitude": lat,
            "longitude": lon,
            "start": start,
            "end": end,
            "format": "JSON",
        },
        label=f"power-{temporal}-{lat:.3f}-{lon:.3f}-{start}",
    )
    return _to_frame(payload, index_format)


def hourly(lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    """Hourly irradiance and meteorology, UTC indexed.

    Columns: ghi (W/m2), temp_air (degC), wind_speed (m/s), relative_humidity (%).
    """
    chunks = [
        _request(
            "hourly", lat, lon,
            f"{year}0101", f"{year}1231",
            HOURLY_PARAMETERS, "RE", "%Y%m%d%H",
        )
        for year in range(start_year, end_year + 1, HOURLY_CHUNK_YEARS)
    ]
    frame = pd.concat(chunks).sort_index()
    return frame.rename(columns={
        "ALLSKY_SFC_SW_DWN": "ghi",
        "T2M": "temp_air",
        "WS2M": "wind_speed",
        "RH2M": "relative_humidity",
    })


def daily(lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    """Daily meteorology, UTC indexed.

    Columns: solar_radiation (MJ/m2/day), temp_mean/max/min (degC),
    relative_humidity (%), wind_speed (m/s), precipitation (mm).
    """
    frame = _request(
        "daily", lat, lon,
        f"{start_year}0101", f"{end_year}1231",
        DAILY_PARAMETERS, "AG", "%Y%m%d",
    )
    return frame.rename(columns={
        "ALLSKY_SFC_SW_DWN": "solar_radiation",
        "T2M": "temp_mean",
        "T2M_MAX": "temp_max",
        "T2M_MIN": "temp_min",
        "RH2M": "relative_humidity",
        "WS2M": "wind_speed",
        "PRECTOTCORR": "precipitation",
    })
