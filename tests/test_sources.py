"""Source tests, dominated by one lesson.

NASA POWER defaults to Local Solar Time. This code originally labelled the
hourly index UTC and handed it to pvlib, which derives solar position from UTC
plus longitude. The result paired midday irradiance with a near-sunset sun --
and produced a perfectly plausible annual energy figure while doing it, which is
why it survived a first pass.

Nothing in the physics tests could catch that, because each stage was correct in
isolation. The only thing that catches it is checking that the sun is where the
light says it is.
"""

import numpy as np
import pandas as pd
import pvlib
import pytest

from agrivolt.sources import nasa_power

ROHA = (18.43, 73.12)


def test_hourly_is_requested_in_utc():
    """pvlib needs UTC, so the request must say so rather than take a default."""
    params = nasa_power.build_params(
        *ROHA, "20230101", "20231231", nasa_power.HOURLY_PARAMETERS, "RE", "UTC"
    )
    assert params["time-standard"] == "UTC"


def test_daily_is_requested_in_local_solar_time():
    """A crop season is measured in local days, not UTC ones."""
    params = nasa_power.build_params(
        *ROHA, "20230101", "20231231", nasa_power.DAILY_PARAMETERS, "AG", "LST"
    )
    assert params["time-standard"] == "LST"


def _cached_hourly(year: int = 2023) -> pd.DataFrame:
    try:
        return nasa_power.hourly(*ROHA, year, year)
    except Exception as exc:  # network down, or nothing cached yet
        pytest.skip(f"hourly POWER data unavailable: {exc}")


@pytest.mark.parametrize("month", [3, 6, 12])
def test_peak_irradiance_coincides_with_the_sun_being_highest(month):
    """The regression test for the time standard bug.

    Take the hour of peak measured irradiance and the hour of minimum solar
    zenith, both derived from the same index. If the index carries the wrong
    time standard they diverge by hours, and every downstream number is built on
    irradiance paired with the wrong sun.
    """
    weather = _cached_hourly()
    window = weather[weather.index.month == month]

    position = pvlib.solarposition.get_solarposition(window.index, *ROHA)
    hours = window.index.hour

    brightest = int(window.groupby(hours)["ghi"].mean().idxmax())
    highest = int(position["apparent_zenith"].groupby(hours).mean().idxmin())

    assert abs(brightest - highest) <= 1, (
        f"peak irradiance at {brightest:02d}h but the sun is highest at "
        f"{highest:02d}h -- the index time standard is wrong"
    )


def test_no_irradiance_once_the_sun_is_well_below_the_horizon():
    """A second, blunter check on the same alignment.

    The threshold is 100 degrees rather than 90 on purpose. These are hourly
    means, so the hour containing sunset legitimately carries real irradiance
    even though the sun is below the horizon at the timestamp, and twilight
    contributes a few W/m2 for a while after. Ten degrees below the horizon is
    past all of that: anything there is a timing error, not dusk.
    """
    weather = _cached_hourly()
    position = pvlib.solarposition.get_solarposition(weather.index, *ROHA)

    night = position["apparent_zenith"] > 100
    assert night.sum() > 1000, "expected a substantial night sample"
    assert float(weather.loc[night, "ghi"].max()) == 0.0


def test_twilight_irradiance_stays_marginal():
    """Between the horizon and 10 degrees below it, light should be a trace."""
    weather = _cached_hourly()
    position = pvlib.solarposition.get_solarposition(weather.index, *ROHA)

    twilight = (position["apparent_zenith"] > 95) & (position["apparent_zenith"] <= 100)
    peak = float(weather["ghi"].max())
    assert float(weather.loc[twilight, "ghi"].max()) < 0.05 * peak


def test_daily_carries_local_dates():
    try:
        daily = nasa_power.daily(*ROHA, 2023, 2023)
    except Exception as exc:
        pytest.skip(f"daily POWER data unavailable: {exc}")
    assert str(daily.index.tz) == nasa_power.INDIA_TZ
    assert daily.index[0].strftime("%m-%d") == "01-01"


def test_hourly_columns_are_physical():
    weather = _cached_hourly()
    assert weather["ghi"].between(0, 1400).all()
    assert weather["relative_humidity"].between(0, 100).all()
    assert not np.isnan(weather["temp_air"]).any()
