import pytest

from victor_ai_bot.capital_demand import CapitalDemandError, ConversionEvidence, Money, selector_scalar
from test_capital_demand_contract import demand


def test_no_implicit_usd_times_10_power_18_conversion():
    value = demand(treasury_denomination="USDC", treasury_decimals=6)
    with pytest.raises(CapitalDemandError):
        selector_scalar(value) if value.strategy_budget_consumption.denomination != "USDC" else None
    assert value.strategy_budget_consumption.amount == 7


def test_invalid_numeric_values_fail_closed():
    with pytest.raises(CapitalDemandError):
        Money(-1, "USDC", 6, "USDC")
    with pytest.raises(CapitalDemandError):
        Money(1, "USDC", 256, "USDC")


def test_rounding_is_explicit():
    from victor_ai_bot.capital_demand import ceil_ratio
    assert ceil_ratio(10, 1, 3) == 4
    with pytest.raises(CapitalDemandError):
        ceil_ratio(10, 1, 0)


def test_conversion_required_for_cross_denomination_projection():
    evidence = ConversionEvidence("oracle:v1", __import__("datetime").datetime.now(__import__("datetime").timezone.utc), 60, "ETH", "USDC", 2_000, 1)
    value = demand(conversion=evidence)
    assert selector_scalar(value) == 7


def test_phase_a_rollout_policy_is_contract_only():
    assert demand(strategy_family="flash_arb").strategy_family == "flash_arb"
    assert demand(strategy_family="stat_arb", capital_source="bankroll").strategy_family == "stat_arb"
