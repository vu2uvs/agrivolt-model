"""Land Equivalent Ratio and the other numbers that make the comparison fair.

LER is the metric the agrivoltaic field settled on, and the one worth leading
with, because it answers the only question that matters to someone holding
land: how much land would I need to produce this much food and this much
electricity separately?

    LER = (crop yield under the array / crop yield in the open field)
        + (energy from the array / energy from a conventional solar farm on the
           same land)

Above 1.0, the combined system does more with the hectare than the two
monocultures could. Values of 1.2-1.7 are typical of the published trials.

Two traps this module is careful about:

  * The energy denominator has to be a *conventional* solar farm on the same
    parcel, not the agrivoltaic array itself. Comparing the array to itself
    gives 1.0 and means nothing. The convention here is a ground mount at the
    reference GCR in `conventional_gcr`.
  * When the counterfactual crop yield is zero -- Konkan rabi fallow, where the
    land currently grows nothing at all -- the crop ratio is undefined, not
    infinite. The function says so rather than returning a number that would
    look spectacular and be meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass

# GCR of the conventional Indian fixed-tilt ground mount used as the energy
# denominator. Indian arrays are spaced wider than European ones to clear
# December shadows at 18-28 degrees north, so 0.40 rather than the 0.45 the
# European literature assumes.
#
# LER is more sensitive to this constant than to anything in the crop model:
# packing the reference plant tighter makes any agrivoltaic design look worse.
# Quote LER with the denominator stated, or it means nothing.
CONVENTIONAL_GCR = 0.40


@dataclass
class LandEquivalentRatio:
    crop_ratio: float | None
    energy_ratio: float
    total: float | None
    interpretation: str

    def as_dict(self) -> dict:
        return {
            "crop_ratio": round(self.crop_ratio, 4) if self.crop_ratio is not None else None,
            "energy_ratio": round(self.energy_ratio, 4),
            "total": round(self.total, 4) if self.total is not None else None,
            "interpretation": self.interpretation,
        }


def land_equivalent_ratio(agrivoltaic_yield_t_ha: float, open_field_yield_t_ha: float,
                          agrivoltaic_energy_kwh: float,
                          conventional_energy_kwh: float) -> LandEquivalentRatio:
    """Compute LER, refusing to invent a crop ratio when there is no baseline."""
    if conventional_energy_kwh <= 0:
        raise ValueError("conventional energy baseline must be positive")

    energy_ratio = agrivoltaic_energy_kwh / conventional_energy_kwh

    if open_field_yield_t_ha <= 0:
        return LandEquivalentRatio(
            crop_ratio=None,
            energy_ratio=energy_ratio,
            total=None,
            interpretation=(
                "The land grows nothing in this season without the array, so no "
                "crop ratio exists and LER is undefined. Judge this case on "
                "absolute output instead: the crop and the electricity are both "
                "additional."
            ),
        )

    crop_ratio = agrivoltaic_yield_t_ha / open_field_yield_t_ha
    total = crop_ratio + energy_ratio

    if total > 1.0:
        verdict = (
            f"The array and the crop together do the work of {total:.2f} hectares "
            f"per hectare of land."
        )
    else:
        verdict = (
            f"At {total:.2f}, this design does less than the two monocultures "
            f"would separately. The geometry needs opening up."
        )

    return LandEquivalentRatio(crop_ratio, energy_ratio, total, verdict)


def system_comparison(baseline_food_t: float, agrivoltaic_food_t: float,
                      agrivoltaic_energy_kwh: float) -> dict:
    """Total annual output of the parcel, with and without the array.

    LER divides, and division fails when the denominator is zero. On a Konkan
    parcel that lies fallow from October to June, the rabi crop the array pays
    for has no open-field counterpart, so it vanishes from LER entirely. This
    reports the same comparison as absolute quantities, where an added crop
    shows up as what it is.
    """
    food_change = agrivoltaic_food_t - baseline_food_t
    if baseline_food_t > 0:
        food_change_pct = round(100 * food_change / baseline_food_t, 1)
    else:
        food_change_pct = None

    return {
        "baseline_food_tonnes": round(baseline_food_t, 2),
        "agrivoltaic_food_tonnes": round(agrivoltaic_food_t, 2),
        "food_change_tonnes": round(food_change, 2),
        "food_change_percent": food_change_pct,
        "energy_added_kwh": round(agrivoltaic_energy_kwh),
        "summary": (
            f"Food output moves from {baseline_food_t:.1f} to "
            f"{agrivoltaic_food_t:.1f} tonnes a year, and the parcel additionally "
            f"delivers {agrivoltaic_energy_kwh / 1e6:.2f} GWh of electricity that "
            f"it does not produce today."
        ),
    }
