import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, Money, project_strategy_budget, require_same_treasury_denomination, selector_scalar
from tests.test_capital_demand_contract import NOW, demand


def test_projection_is_only_strategy_budget_consumption():
    value = demand(strategy_budget_consumption=Money(17, "USD", 2, "USD"), execution_notional=Money(99_999_999, "USDC", 6, "USDC"))
    assert project_strategy_budget(value, now=NOW).amount == 17
    assert selector_scalar(value, now=NOW) == 17


def test_projection_rejects_unknown_stale_conflicting_or_zero_demand():
    with pytest.raises(CapitalDemandError):
        selector_scalar(demand(status="unknown"), now=NOW)
    with pytest.raises(CapitalDemandError):
        selector_scalar(demand(demand_expires_at=NOW - __import__("datetime").timedelta(seconds=1)), now=NOW)
    with pytest.raises(CapitalDemandError):
        selector_scalar(demand(strategy_budget_consumption=Money(0, "USD", 2, "USD")), now=NOW)


def test_budget_comparison_requires_same_denomination_and_decimals():
    value = demand()
    require_same_treasury_denomination(Money(100, "USD", 2, "USD"), value)
    with pytest.raises(CapitalDemandError):
        require_same_treasury_denomination(Money(100, "USDC", 6, "USDC"), value)