"""How much light gets past the array and reaches the crop.

This is the module the whole project turns on. Everything else -- the PV yield,
the water balance, the economics -- is standard practice borrowed from mature
tools. What makes an array agrivoltaic rather than merely elevated is the light
budget on the ground underneath it.

Two transmission paths are modelled separately:

Beam
    A tilted row of slant width ``W`` casts a shadow on flat ground whose width,
    measured perpendicular to the row axis, is

        L = W * |cos(tilt) + sin(tilt) * tan(phi)|

    where ``phi`` is the solar zenith projected onto the plane perpendicular to
    the rows. Dividing by the pitch and recognising ``GCR = W / pitch`` gives the
    shaded ground fraction directly. Clearance height shifts the shadow along the
    ground but does not change its width, which is why tall agrivoltaic mounts
    buy uniformity of shade rather than less shade.

Diffuse
    Ground between the rows sees a restricted sky dome. The average sky view
    factor over the inter-row strip comes from pvlib's 2-D view factor
    integration.

Ground-reflected light bouncing back down onto the canopy is neglected. It is a
small positive term, so the model is mildly conservative about crop light.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pvlib

from .geometry import PanelArray

# Above this zenith the sun is at the horizon, tan() explodes, and the ground is
# fully shaded anyway. pvlib uses the same guard internally.
MAX_ZENITH = 87.0

# Photosynthetically active radiation as a fraction of broadband shortwave, by
# energy. Ranges 0.45-0.50 in the literature; 0.45 is the conventional value and
# the conservative one for crop light.
PAR_FRACTION = 0.45


def unshaded_beam_fraction(solar_zenith, solar_azimuth, array: PanelArray):
    """Fraction of ground not in a row's beam shadow, 0-1.

    Derived from row geometry rather than called out of pvlib's private API, so
    that the assumption is visible and testable. `tests/test_shading.py` pins it
    against pvlib's own implementation.
    """
    zenith = np.minimum(np.asarray(solar_zenith, dtype=float), MAX_ZENITH)
    tan_phi = pvlib.bifacial.utils._solar_projection_tangent(
        zenith, solar_azimuth, array.azimuth
    )
    shadow_over_pitch = array.gcr * np.abs(
        pvlib.tools.cosd(array.tilt) + pvlib.tools.sind(array.tilt) * tan_phi
    )
    return 1.0 - np.clip(shadow_over_pitch, 0.0, 1.0)


def ground_sky_view_factor(array: PanelArray) -> float:
    """Average fraction of the sky dome visible from the ground between rows.

    Depends only on geometry, so it is computed once per array rather than per
    timestep. Widening the pitch pushes this towards 1. Raising the array does
    not: for an infinite row array the mean is set by GCR, and clearance height
    only makes the shade more uniform along the ground.
    """
    # pvlib returns an array shaped like `surface_tilt`; ours is always scalar.
    view_factor = pvlib.bifacial.utils.vf_ground_sky_2d_integ(
        surface_tilt=array.tilt,
        gcr=array.gcr,
        height=array.row_centre_height,
        pitch=array.pitch,
    )
    return float(np.ravel(view_factor)[0])


def canopy_irradiance(irradiance: pd.DataFrame, solar_position: pd.DataFrame,
                      array: PanelArray) -> pd.DataFrame:
    """Shortwave irradiance reaching the crop canopy, in W/m2.

    Returns the beam and diffuse components on a horizontal canopy plane, their
    total, and the open-field total for comparison.
    """
    unshaded = unshaded_beam_fraction(
        solar_position["apparent_zenith"], solar_position["azimuth"], array
    )
    cos_zenith = np.maximum(
        pvlib.tools.cosd(solar_position["apparent_zenith"].to_numpy()), 0.0
    )

    beam = irradiance["dni"].to_numpy() * cos_zenith * unshaded
    diffuse = irradiance["dhi"].to_numpy() * ground_sky_view_factor(array)

    return pd.DataFrame(
        {
            "beam": beam,
            "diffuse": diffuse,
            "total": beam + diffuse,
            "open_field": irradiance["ghi"].to_numpy(),
        },
        index=irradiance.index,
    )


def transmission_ratio(canopy: pd.DataFrame) -> float:
    """Season- or year-integrated share of open-field light reaching the canopy.

    This single number is what the crop model consumes. A conventional solar
    farm sits near 0.1; a well-designed agrivoltaic array lands at 0.6-0.8.
    """
    open_field = canopy["open_field"].sum()
    if open_field <= 0:
        raise ValueError("no incident light over the requested period")
    return float(canopy["total"].sum() / open_field)


def canopy_par(canopy: pd.DataFrame) -> pd.Series:
    """Photosynthetically active radiation reaching the canopy, in W/m2."""
    return canopy["total"] * PAR_FRACTION
