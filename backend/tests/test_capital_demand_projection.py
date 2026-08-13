import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, Money, project_strategy_budget, selector_scalar
from test_capital_demand_contract import demand


def test_projection_is_strategy_budget_consumption_not_universal_capital():
    value = demand(strategy_budget_consumption=Money(17, "USDC", 6, "USDC"))
    assert project_strategy_budget(value).amount == 17
    assert selector_scalar(value) == 17


def test_projection_rejects_unknown_or_invalid_demand():
    value = demand(status="invalid")
    with pytest.raises(CapitalDemandError):
        selector_scalar(value)


def test_budget_comparison_requires_same_denomination_and_decimals():
    from victor_ai_bot.capital_demand import require_same_treasury_denomination
    value = demand()
    require_same_treasury_denomination(Money(100, "USDC", 6, "USDC"), value)
    with pytest.raises(CapitalDemandError):
        require_same_treasury_denomination(Money(100, "USD", 2, "USD"), value)


def test_projection_preserves_zero_as_unknown_for_selector_authority():
    value = demand(strategy_budget_consumption=Money(0, "USDC", 6, "USDC"))
    with pytest.raises(CapitalDemandError):
        selector_scalar(value)
