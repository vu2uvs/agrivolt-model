"""Geometry is simple enough that the tests are mostly about refusing nonsense."""

import pytest

from agrivolt.geometry import PanelArray


def test_gcr_is_width_over_pitch():
    array = PanelArray(collector_width=2.5, pitch=10.0, tilt=20.0)
    assert array.gcr == pytest.approx(0.25)


def test_overlapping_rows_are_rejected():
    with pytest.raises(ValueError, match="narrower than the collector width"):
        PanelArray(collector_width=5.0, pitch=3.0, tilt=20.0)


def test_impossible_tilt_is_rejected():
    with pytest.raises(ValueError, match="outside 0-90"):
        PanelArray(collector_width=2.0, pitch=8.0, tilt=120.0)


def test_row_centre_sits_above_the_lower_edge():
    flat = PanelArray(collector_width=4.0, pitch=12.0, tilt=0.0, clearance_height=3.0)
    tilted = PanelArray(collector_width=4.0, pitch=12.0, tilt=30.0, clearance_height=3.0)
    assert flat.row_centre_height == pytest.approx(3.0)
    assert tilted.row_centre_height == pytest.approx(3.0 + 2.0 * 0.5)


def test_capacity_scales_with_coverage():
    """Halving the pitch must double the capacity on the same parcel."""
    sparse = PanelArray(collector_width=2.0, pitch=16.0, tilt=20.0)
    dense = PanelArray(collector_width=2.0, pitch=8.0, tilt=20.0)
    assert dense.dc_capacity_kw(1.0) == pytest.approx(2 * sparse.dc_capacity_kw(1.0))
