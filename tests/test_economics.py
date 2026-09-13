"""Financial functions are checked against hand-computable cases."""

import pytest

from agrivolt import economics


def test_npv_of_a_flat_series():
    assert economics.net_present_value([-100, 110], 0.10) == pytest.approx(0.0)


def test_irr_of_a_known_cashflow():
    """-100 then 60, 60 solves to 13.066% by quadratic formula."""
    irr = economics.internal_rate_of_return([-100, 60, 60])
    assert irr == pytest.approx(0.13066, abs=1e-4)


def test_a_value_destroying_project_returns_a_deeply_negative_irr():
    """Losing money is a negative return, not an absent one."""
    irr = economics.internal_rate_of_return([-100, 1, 1, 1])
    assert irr is not None and irr < -0.5


def test_irr_is_none_when_the_cashflow_never_turns_positive():
    """No sign change means no root, and None is the honest answer."""
    assert economics.internal_rate_of_return([-100, -10, -10]) is None


def test_npv_is_zero_at_the_irr():
    flows = [-1000, 200, 300, 400, 500]
    irr = economics.internal_rate_of_return(flows)
    assert economics.net_present_value(flows, irr) == pytest.approx(0.0, abs=1e-4)


@pytest.fixture
def assumptions():
    return economics.FinanceAssumptions.load()


def test_assumptions_load_from_config(assumptions):
    assert assumptions.project_life_years == 25
    assert 0 < assumptions.tariff_inr_per_kwh < 20
    assert 0 < assumptions.discount_rate < 1


def test_breakeven_tariff_really_does_break_even(assumptions):
    """Setting the tariff to the breakeven value must drive NPV to zero.

    This is the test that makes the headline number trustworthy: the algebra in
    `breakeven_tariff` and the loop in `project_cashflows` are independent
    implementations of the same model, and they have to agree.
    """
    from dataclasses import replace

    capacity, energy, margin = 2769.0, 4_650_000.0, 54_000.0
    tariff = economics.breakeven_tariff(capacity, energy, margin, assumptions)
    at_breakeven = replace(assumptions, tariff_inr_per_kwh=tariff)
    flows = economics.project_cashflows(capacity, energy, margin, at_breakeven)

    npv = economics.net_present_value(flows, assumptions.discount_rate)
    assert npv == pytest.approx(0.0, abs=1.0)


def test_lcoe_exceeds_the_undiscounted_average_cost(assumptions):
    """Discounting energy as well as cost must raise LCOE, not lower it."""
    capex, opex, energy = 1e8, 1e6, 4e6
    lcoe = economics.levelised_cost(capex, opex, energy, assumptions)
    naive = (capex + opex * assumptions.project_life_years) / (
        energy * assumptions.project_life_years
    )
    assert lcoe > naive
