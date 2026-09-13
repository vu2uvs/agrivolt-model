"""The light model is the part of this project that is actually novel, so it
carries the most tests. Two kinds here: agreement with pvlib's independent
implementation of the same geometry, and physical properties that must hold for
any correct model regardless of implementation.
"""

import numpy as np
import pvlib
import pytest

from agrivolt import shading
from agrivolt.geometry import PanelArray


@pytest.fixture
def array():
    return PanelArray(collector_width=2.3, pitch=9.0, tilt=18.0, clearance_height=4.0)


def test_beam_shading_matches_pvlib(array):
    """Our derivation and pvlib's must agree across the whole sky.

    We derive the shadow width from row geometry rather than calling pvlib's
    private helper, so that the assumption is visible in `shading.py`. This test
    is what makes that safe: if either implementation drifts, it fails.
    """
    rng = np.random.default_rng(0)
    zenith = rng.uniform(0, 87, 2000)
    azimuth = rng.uniform(0, 360, 2000)

    ours = shading.unshaded_beam_fraction(zenith, azimuth, array)
    theirs = pvlib.bifacial.utils._unshaded_ground_fraction(
        array.tilt, array.azimuth, zenith, azimuth, array.gcr
    )
    np.testing.assert_allclose(ours, theirs, atol=1e-12)


def test_unshaded_fraction_is_bounded(array):
    zenith = np.linspace(0, 90, 200)
    fraction = shading.unshaded_beam_fraction(zenith, np.full(200, 180.0), array)
    assert np.all(fraction >= 0.0)
    assert np.all(fraction <= 1.0)


def test_overhead_sun_shades_exactly_the_module_footprint(array):
    """With the sun at zenith, the shadow is the module's own horizontal extent."""
    fraction = shading.unshaded_beam_fraction(0.0, 180.0, array)
    expected = 1 - array.gcr * np.cos(np.radians(array.tilt))
    assert fraction == pytest.approx(expected, abs=1e-12)


def test_wider_pitch_lets_through_more_diffuse():
    """Sky view factor must rise monotonically as rows are spread apart."""
    view_factors = [
        shading.ground_sky_view_factor(
            PanelArray(collector_width=2.3, pitch=pitch, tilt=18.0, clearance_height=4.0)
        )
        for pitch in (3.0, 5.0, 9.0, 15.0, 25.0)
    ]
    assert view_factors == sorted(view_factors)
    assert all(0.0 <= v <= 1.0 for v in view_factors)


def test_clearance_height_barely_changes_average_ground_light():
    """Height buys uniformity of shade, not more of it.

    A tempting intuition says raising the array lets more light reach the crop.
    For an infinite row array it does not: the rows intercept a share of the sky
    set by GCR, and lifting them only spreads the same deficit more evenly along
    the ground. Averaged between rows the view factor is nearly invariant.

    This matters for design. Clearance height is bought for tractor access and
    for the even light distribution that keeps a crop uniform -- it is not a
    lever on total light, and a scenario that leans on it as one is mistaken.
    """
    view_factors = [
        shading.ground_sky_view_factor(
            PanelArray(collector_width=2.3, pitch=9.0, tilt=18.0, clearance_height=h)
        )
        for h in (1.5, 3.0, 6.0, 10.0)
    ]
    assert max(view_factors) - min(view_factors) < 0.01
