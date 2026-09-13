"""Two revenue streams, one balance sheet.

An agrivoltaic project is a twenty-five year infrastructure asset with a farm
attached. Those two halves have completely different risk profiles: the
electricity is contracted at a fixed tariff for the life of the plant, the crop
is exposed to weather and to mandi prices that move by a factor of three within
a season. Keeping them as separate lines all the way to the bottom of the model
is the point -- a blended "revenue per hectare" number hides exactly the thing
an investor is trying to price.

All currency is nominal Indian rupees. Discounting is nominal, so the discount
rate must include inflation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ASSUMPTIONS_FILE = Path(__file__).resolve().parents[2] / "config" / "assumptions.yaml"

IRR_LOWER_BOUND = -0.99
IRR_UPPER_BOUND = 3.0
IRR_TOLERANCE = 1e-7
IRR_MAX_ITERATIONS = 200

LAKH = 100_000
CRORE = 10_000_000


@dataclass(frozen=True)
class FinanceAssumptions:
    """Every economic number the model uses, in one place.

    Loaded from `config/assumptions.yaml`, where each value carries a source.
    Nothing in the code should hard-code a rupee figure.
    """

    capex_inr_per_wp: float
    opex_inr_per_kw_year: float
    tariff_inr_per_kwh: float
    tariff_escalation: float
    degradation_rate: float
    project_life_years: int
    discount_rate: float
    crop_price_escalation: float

    @classmethod
    def load(cls, path: Path | None = None) -> "FinanceAssumptions":
        raw = yaml.safe_load((path or ASSUMPTIONS_FILE).read_text(encoding="utf-8"))
        return cls(**{key: entry["value"] for key, entry in raw["finance"].items()})


def net_present_value(cashflows: list[float], discount_rate: float) -> float:
    """NPV of a series whose first element is year 0."""
    return sum(cf / (1 + discount_rate) ** year for year, cf in enumerate(cashflows))


def internal_rate_of_return(cashflows: list[float]) -> float | None:
    """IRR by bisection.

    Bisection rather than Newton because it cannot diverge, and this runs on
    cashflows a user supplied rather than ones we control. Returns None when no
    sign change exists in the bracket, which is the honest answer for a project
    that never pays back.
    """
    low, high = IRR_LOWER_BOUND, IRR_UPPER_BOUND
    npv_low = net_present_value(cashflows, low)
    npv_high = net_present_value(cashflows, high)
    if npv_low * npv_high > 0:
        return None

    for _ in range(IRR_MAX_ITERATIONS):
        mid = (low + high) / 2
        npv_mid = net_present_value(cashflows, mid)
        if abs(npv_mid) < IRR_TOLERANCE:
            return mid
        if npv_low * npv_mid < 0:
            high = mid
        else:
            low, npv_low = mid, npv_mid
    return (low + high) / 2


def levelised_cost(capex: float, annual_opex: float, annual_energy_kwh: float,
                   assumptions: FinanceAssumptions) -> float:
    """LCOE in INR/kWh: discounted lifetime cost over discounted lifetime energy.

    Energy is discounted as well as cost. This trips people up, but a kWh
    delivered in year 20 really is worth less than one delivered today, and
    omitting it flatters the number by roughly a third.
    """
    discounted_cost = capex
    discounted_energy = 0.0
    for year in range(1, assumptions.project_life_years + 1):
        discount = (1 + assumptions.discount_rate) ** year
        energy = annual_energy_kwh * (1 - assumptions.degradation_rate) ** (year - 1)
        discounted_cost += annual_opex / discount
        discounted_energy += energy / discount
    return discounted_cost / discounted_energy


def project_cashflows(dc_capacity_kw: float, annual_energy_kwh: float,
                      annual_crop_margin_inr: float,
                      assumptions: FinanceAssumptions) -> list[float]:
    """Nominal project cashflows, year 0 through end of life.

    Year 0 is construction: capex out, nothing in. The crop margin may be
    negative, and is deliberately allowed to be -- a scenario where the farming
    loses money while the electricity carries the project is a real outcome and
    the model should be able to say so.
    """
    capex = dc_capacity_kw * 1000 * assumptions.capex_inr_per_wp
    flows = [-capex]

    for year in range(1, assumptions.project_life_years + 1):
        energy = annual_energy_kwh * (1 - assumptions.degradation_rate) ** (year - 1)
        tariff = assumptions.tariff_inr_per_kwh * (1 + assumptions.tariff_escalation) ** (year - 1)
        crop = annual_crop_margin_inr * (1 + assumptions.crop_price_escalation) ** (year - 1)
        opex = dc_capacity_kw * assumptions.opex_inr_per_kw_year
        flows.append(energy * tariff + crop - opex)

    return flows


def crop_margin(yield_t_ha: float, area_ha: float, price_inr_per_tonne: float,
                cost_inr_per_ha: float) -> float:
    """Gross margin from the crop in a season, in INR.

    Cultivation cost is charged on the cropped area whether or not the crop
    succeeds, because it is spent before the outcome is known.
    """
    return yield_t_ha * area_ha * price_inr_per_tonne - cost_inr_per_ha * area_ha


def breakeven_tariff(dc_capacity_kw: float, annual_energy_kwh: float,
                     annual_crop_margin_inr: float,
                     assumptions: FinanceAssumptions) -> float:
    """The tariff at which the project exactly clears its discount rate, INR/kWh.

    Arguably the single most useful number the model produces. NPV is linear in
    the tariff, so this is solved directly rather than searched: everything that
    is not the energy revenue is discounted to a present cost, and divided by
    discounted lifetime energy.

    Comparing this against what MSKVY actually pays turns a project-level
    result into a policy-level one -- it says how large the gap is, in paise,
    between what agrivoltaics costs and what the state currently offers for it.
    """
    capex = dc_capacity_kw * 1000 * assumptions.capex_inr_per_wp
    annual_opex = dc_capacity_kw * assumptions.opex_inr_per_kw_year

    present_cost = capex
    discounted_energy = 0.0
    for year in range(1, assumptions.project_life_years + 1):
        discount = (1 + assumptions.discount_rate) ** year
        energy = annual_energy_kwh * (1 - assumptions.degradation_rate) ** (year - 1)
        crop = annual_crop_margin_inr * (1 + assumptions.crop_price_escalation) ** (year - 1)
        present_cost += (annual_opex - crop) / discount
        discounted_energy += energy / discount

    return present_cost / discounted_energy


def sensitivity(dc_capacity_kw: float, annual_energy_kwh: float,
                annual_crop_margin_inr: float, assumptions: FinanceAssumptions,
                capex_range: tuple[float, ...] = (38.0, 45.0, 52.0),
                tariff_range: tuple[float, ...] = (2.24, 2.825, 2.90)) -> list[dict]:
    """IRR across the capex and tariff bounds that actually matter.

    The tariff defaults span the range MERC discovered across the 257 MSKVY 2.0
    substations, so these are not invented bounds -- they are the spread of
    prices the scheme is really paying.
    """
    from dataclasses import replace

    grid = []
    for capex in capex_range:
        for tariff in tariff_range:
            case = replace(assumptions, capex_inr_per_wp=capex, tariff_inr_per_kwh=tariff)
            flows = project_cashflows(
                dc_capacity_kw, annual_energy_kwh, annual_crop_margin_inr, case
            )
            irr = internal_rate_of_return(flows)
            grid.append({
                "capex_inr_per_wp": capex,
                "tariff_inr_per_kwh": tariff,
                "irr_percent": round(irr * 100, 2) if irr is not None else None,
                "npv_inr_crore": round(
                    net_present_value(flows, case.discount_rate) / CRORE, 3
                ),
                "clears_hurdle": (
                    irr is not None and irr >= assumptions.discount_rate
                ),
            })
    return grid


def summarise(dc_capacity_kw: float, annual_energy_kwh: float,
              annual_crop_margin_inr: float,
              assumptions: FinanceAssumptions) -> dict:
    """The financial block of a scenario result."""
    capex = dc_capacity_kw * 1000 * assumptions.capex_inr_per_wp
    annual_opex = dc_capacity_kw * assumptions.opex_inr_per_kw_year
    flows = project_cashflows(
        dc_capacity_kw, annual_energy_kwh, annual_crop_margin_inr, assumptions
    )
    irr = internal_rate_of_return(flows)

    cumulative = 0.0
    payback_year = None
    for year, flow in enumerate(flows):
        cumulative += flow
        if cumulative >= 0 and year > 0:
            payback_year = year
            break

    return {
        "capex_inr_crore": round(capex / CRORE, 3),
        "annual_opex_inr_lakh": round(annual_opex / LAKH, 2),
        "year_one_energy_revenue_inr_lakh": round(
            annual_energy_kwh * assumptions.tariff_inr_per_kwh / LAKH, 2
        ),
        "year_one_crop_margin_inr_lakh": round(annual_crop_margin_inr / LAKH, 2),
        "lcoe_inr_per_kwh": round(
            levelised_cost(capex, annual_opex, annual_energy_kwh, assumptions), 3
        ),
        "npv_inr_crore": round(
            net_present_value(flows, assumptions.discount_rate) / CRORE, 3
        ),
        "irr_percent": round(irr * 100, 2) if irr is not None else None,
        "simple_payback_years": payback_year,
        "hurdle_rate_percent": round(assumptions.discount_rate * 100, 2),
        "breakeven_tariff_inr_per_kwh": round(
            breakeven_tariff(
                dc_capacity_kw, annual_energy_kwh, annual_crop_margin_inr, assumptions
            ),
            3,
        ),
        "tariff_gap_inr_per_kwh": round(
            breakeven_tariff(
                dc_capacity_kw, annual_energy_kwh, annual_crop_margin_inr, assumptions
            )
            - assumptions.tariff_inr_per_kwh,
            3,
        ),
        "sensitivity": sensitivity(
            dc_capacity_kw, annual_energy_kwh, annual_crop_margin_inr, assumptions
        ),
    }
