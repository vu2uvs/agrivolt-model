"""LER's edge cases are where it misleads people, so that is what is tested."""

import pytest

from agrivolt import metrics


def test_ler_adds_the_two_ratios():
    result = metrics.land_equivalent_ratio(2.0, 2.5, 4_000_000, 8_000_000)
    assert result.crop_ratio == pytest.approx(0.8)
    assert result.energy_ratio == pytest.approx(0.5)
    assert result.total == pytest.approx(1.3)


def test_ler_is_undefined_rather_than_infinite_on_fallow_land():
    """Konkan rabi: the land grows nothing today, so there is nothing to divide by.

    Returning a huge number here would be the single easiest way to accidentally
    publish a spectacular and meaningless result.
    """
    result = metrics.land_equivalent_ratio(0.7, 0.0, 4_000_000, 8_000_000)
    assert result.crop_ratio is None
    assert result.total is None
    assert "undefined" in result.interpretation


def test_ler_says_so_when_a_design_is_worse_than_the_monocultures():
    result = metrics.land_equivalent_ratio(0.5, 2.5, 2_000_000, 8_000_000)
    assert result.total < 1.0
    assert "opening up" in result.interpretation


def test_zero_energy_baseline_is_rejected():
    with pytest.raises(ValueError, match="must be positive"):
        metrics.land_equivalent_ratio(2.0, 2.5, 4_000_000, 0)


def test_system_comparison_handles_a_zero_baseline():
    result = metrics.system_comparison(0.0, 5.0, 1_000_000)
    assert result["food_change_percent"] is None
    assert result["food_change_tonnes"] == pytest.approx(5.0)
