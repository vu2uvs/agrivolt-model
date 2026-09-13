"""Array geometry.

Everything downstream of this module depends on exactly four numbers: how wide
a module row is, how far apart the rows are, how steeply they are tilted, and
how high they are off the ground. In a conventional solar farm you shrink the
pitch until the rows nearly touch, because land is the thing you are trying to
use up. In an agrivoltaic array the pitch is the design variable you spend
crop yield on, so it gets a first-class representation here.
"""

from __future__ import annotations

from dataclasses import dataclass

# Standard test conditions irradiance, W/m2. Nameplate DC watts are defined here.
STC_IRRADIANCE = 1000.0

SQUARE_METRES_PER_HECTARE = 10_000.0


@dataclass(frozen=True)
class PanelArray:
    """A field of parallel, tilted module rows.

    Attributes
    ----------
    collector_width:
        Slant width of one row, measured up the tilted plane, in metres.
    pitch:
        Ground distance between the centres of adjacent rows, in metres.
    tilt:
        Module tilt from horizontal, in degrees.
    azimuth:
        Direction the modules face, degrees clockwise from north. 180 is south.
    clearance_height:
        Ground to the lower edge of the row, in metres. Agrivoltaic arrays sit
        high enough to drive a tractor under; this is the main cost premium
        over a conventional ground mount.
    module_efficiency:
        Fraction of STC irradiance converted to DC power, 0-1.
    ground_utilisation:
        Fraction of the parcel that can actually carry rows once inverter pads,
        access tracks, setbacks and headlands are removed.
    """

    collector_width: float
    pitch: float
    tilt: float
    azimuth: float = 180.0
    clearance_height: float = 3.5
    module_efficiency: float = 0.21
    ground_utilisation: float = 0.85

    def __post_init__(self) -> None:
        if self.pitch < self.collector_width:
            raise ValueError(
                f"pitch {self.pitch} m is narrower than the collector width "
                f"{self.collector_width} m: rows would overlap"
            )
        if not 0 <= self.tilt <= 90:
            raise ValueError(f"tilt {self.tilt} deg is outside 0-90")

    @property
    def gcr(self) -> float:
        """Ground coverage ratio: collector width over pitch.

        The single most important agrivoltaic design number. A conventional
        Indian ground mount runs 0.4-0.5; agrivoltaic arrays run 0.2-0.35.
        """
        return self.collector_width / self.pitch

    @property
    def row_centre_height(self) -> float:
        """Height of the row's midpoint above ground, in metres."""
        import math

        return self.clearance_height + 0.5 * self.collector_width * math.sin(
            math.radians(self.tilt)
        )

    def module_area(self, parcel_ha: float) -> float:
        """Total module surface area on a parcel, in square metres."""
        return parcel_ha * SQUARE_METRES_PER_HECTARE * self.ground_utilisation * self.gcr

    def dc_capacity_kw(self, parcel_ha: float) -> float:
        """Nameplate DC capacity on a parcel, in kW."""
        watts = self.module_area(parcel_ha) * self.module_efficiency * STC_IRRADIANCE
        return watts / 1000.0

    def cropped_area_ha(self, parcel_ha: float) -> float:
        """Parcel area still available to grow a crop, in hectares.

        Rows are elevated, so the ground beneath them stays cultivable. What is
        genuinely lost is the footprint of piles, inverter pads and tracks.
        """
        return parcel_ha * self.ground_utilisation
