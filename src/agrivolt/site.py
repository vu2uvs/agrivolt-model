"""A site is the unit of analysis: a patch of land with a climate."""

from __future__ import annotations

from dataclasses import dataclass

from .sources import nasa_power

HECTARES_PER_ACRE = 0.404686


@dataclass(frozen=True)
class Site:
    """A parcel of farmland under consideration.

    `area_ha` is gross parcel area. What fraction of it can actually carry
    modules is an array property, not a site property -- see
    `geometry.PanelArray.ground_utilisation`.
    """

    name: str
    district: str
    latitude: float
    longitude: float
    area_ha: float
    altitude_m: float = 0.0
    agroclimatic_zone: str = ""

    @classmethod
    def from_acres(cls, acres: float, **kwargs) -> "Site":
        return cls(area_ha=acres * HECTARES_PER_ACRE, **kwargs)

    def hourly_weather(self, start_year: int, end_year: int):
        return nasa_power.hourly(self.latitude, self.longitude, start_year, end_year)

    def daily_weather(self, start_year: int, end_year: int):
        return nasa_power.daily(self.latitude, self.longitude, start_year, end_year)
