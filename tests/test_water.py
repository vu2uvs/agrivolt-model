"""FAO-56 has published reference values for its intermediate quantities, which
makes the vapour pressure functions checkable against the paper rather than
against our own output.
"""

import numpy as np
import pandas as pd
import pytest

from agrivolt import water


def test_saturation_vapour_pressure_matches_fao56_table():
    """FAO-56 Table 2.1: 2.338 kPa at 20 C, 3.168 kPa at 25 C."""
    assert water._saturation_vapour_pressure(20.0) == pytest.approx(2.338, abs=1e-3)
    assert water._saturation_vapour_pressure(25.0) == pytest.approx(3.168, abs=1e-3)


def test_psychrometric_constant_at_sea_level():
    """FAO-56: gamma = 0.665e-3 * 101.3 kPa = 0.0674 kPa/C at sea level."""
    assert water._psychrometric_constant(0.0) == pytest.approx(0.0674, abs=1e-4)
    # Pressure falls with altitude, so gamma must fall with it.
    assert water._psychrometric_constant(1000.0) < water._psychrometric_constant(0.0)


def test_extraterrestrial_radiation_peaks_in_the_local_summer():
    """At 18 N the top-of-atmosphere flux must peak nearer June than December."""
    days = np.arange(1, 366)
    radiation = water.extraterrestrial_radiation(days, 18.43)
    assert 120 < int(days[np.argmax(radiation)]) < 200
    assert np.all(radiation > 0)


def _weather(days: int = 30, **overrides) -> pd.DataFrame:
    base = {
        "temp_mean": 28.0, "temp_max": 34.0, "temp_min": 22.0,
        "relative_humidity": 60.0, "wind_speed": 2.0,
        "solar_radiation": 20.0, "precipitation": 0.0,
    }
    base.update(overrides)
    index = pd.date_range("2023-03-01", periods=days, freq="D", tz="UTC")
    return pd.DataFrame({k: [v] * days for k, v in base.items()}, index=index)


def test_reference_et_lands_in_a_physical_range():
    """A hot, dry, sunny March day in Maharashtra: single-digit mm, not 50."""
    et0 = water.reference_evapotranspiration(_weather(), latitude=18.43)
    assert et0.between(3.0, 12.0).all()


def test_shading_reduces_reference_et():
    """The whole water argument depends on this being true."""
    weather = _weather()
    open_field = water.reference_evapotranspiration(weather, 18.43).sum()
    shaded = water.reference_evapotranspiration(
        weather, 18.43, radiation_scale=0.7, wind_scale=water.SHELTERED_WIND_FACTOR
    ).sum()
    assert shaded < open_field


def test_relative_transpiration_is_capped_at_one():
    """Surplus water does not raise yield, so the ratio must not exceed 1."""
    balance = water.water_balance(
        pd.Series([100.0] * 10), pd.Series([1.0] * 10), irrigation_mm=500
    )
    assert balance["relative_transpiration"] == 1.0
    assert balance["deficit_mm"] == 0.0
