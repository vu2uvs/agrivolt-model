"""Crop response tests are property based: the parameter values are uncertain,
but the shape of the response is not negotiable.
"""

import pandas as pd
import pytest

from agrivolt import crop as crop_model


@pytest.fixture
def crops():
    return crop_model.load_crops()


def test_library_loads_and_is_internally_consistent(crops):
    assert crops
    for name, crop in crops.items():
        assert crop.stages.total > 0
        assert 0 < crop.shade_sensitivity <= 1.0, name
        assert crop.reference_yield_t_ha > 0, name
        assert crop.source, f"{name} has no provenance"
        assert len(crop.crop_coefficient_curve(2023)) == crop.stages.total


def test_less_light_never_raises_the_light_factor(crops):
    crop = crops["sorghum_rabi"]
    factors = [crop_model.light_factor(t, crop) for t in (0.2, 0.4, 0.6, 0.8, 1.0)]
    assert factors == sorted(factors)
    assert factors[-1] == pytest.approx(1.0)


def test_shade_tolerant_crops_lose_less_light_than_light_hungry_ones(crops):
    """Sorghum is C4 and close to light limited; cowpea saturates well below full sun."""
    at_seventy_percent = 0.7
    sorghum = crop_model.light_factor(at_seventy_percent, crops["sorghum_rabi"])
    cowpea = crop_model.light_factor(at_seventy_percent, crops["cowpea_rabi"])
    assert cowpea > sorghum


def test_water_factor_follows_fao33(crops):
    crop = crops["chickpea_rabi"]
    assert crop_model.water_factor(1.0, crop) == pytest.approx(1.0)
    expected = 1 - crop.yield_response_factor * 0.5
    assert crop_model.water_factor(0.5, crop) == pytest.approx(expected)


def test_cooling_relieves_heat_stress(crops):
    """The India-specific channel: a few kelvin across flowering is worth yield."""
    crop = crops["chickpea_rabi"]
    hot = pd.Series([crop.critical_temp_c + 1.5] * 30)
    assert crop_model.heat_factor(hot, crop, cooling_k=0.0) < 1.0
    assert crop_model.heat_factor(hot, crop, cooling_k=3.0) == pytest.approx(1.0)


def test_shade_can_beat_open_field_when_water_is_the_binding_constraint(crops):
    """The central claim of the project, as an executable assertion.

    Under a deficit, the array's water saving outweighs the light it costs, and
    the shaded crop out-yields the open-field one. If this ever stops holding,
    the thesis is wrong and the README needs rewriting.
    """
    crop = crops["cowpea_rabi"]
    temps = pd.Series([30.0] * 30)

    shaded = crop_model.estimate_yield(
        crop, transmission=0.70, relative_transpiration=0.42,
        season_temp_max=temps, shaded=True,
    )
    open_field = crop_model.estimate_yield(
        crop, transmission=1.0, relative_transpiration=0.28,
        season_temp_max=temps, shaded=False,
    )
    assert shaded.yield_t_ha > open_field.yield_t_ha


def test_factors_stay_within_zero_and_one(crops):
    crop = crops["paddy_kharif"]
    estimate = crop_model.estimate_yield(
        crop, transmission=0.0, relative_transpiration=0.0,
        season_temp_max=pd.Series([50.0] * 10), shaded=True,
    )
    assert 0.0 <= estimate.relative_yield <= 1.0
