from datetime import timedelta

import pytest

from victor_ai_bot.capital_demand import Capacity, CapitalDemandError, ConversionEvidence, Money, apply_aggressiveness_cap, apply_goal_cap, live_eligible_family
from tests.test_capital_demand_contract import NOW, demand


def test_conversion_exact_fractional_rounding_and_direction():
    evidence = ConversionEvidence("oracle:v1", NOW, 60, "ETH", "USD", 2, 3)
    source = Money(2, "ETH", 18, "ETH")
    assert evidence.convert(source, target_asset="USD", target_decimals=2, now=NOW, rounding="floor").amount == 1
    assert evidence.convert(source, target_asset="USD", target_decimals=2, now=NOW, rounding="ceil").amount == 2
    with pytest.raises(CapitalDemandError):
        evidence.convert(Money(1, "USDC", 6, "USDC"), target_asset="USD", target_decimals=2, now=NOW)
    with pytest.raises(CapitalDemandError):
        evidence.convert(source, target_asset="USD", target_decimals=2, now=NOW, rounding="bad")


def test_conversion_stale_invalid_ratio_and_zero_denominator_fail_closed():
    stale = ConversionEvidence("oracle:v1", NOW - timedelta(seconds=61), 60, "ETH", "USD", 1, 1)
    with pytest.raises(CapitalDemandError):
        stale.convert(Money(1, "ETH", 18, "ETH"), target_asset="USD", target_decimals=2, now=NOW)
    with pytest.raises(CapitalDemandError):
        ConversionEvidence("oracle:v1", NOW, 60, "ETH", "USD", 1, 0)
    with pytest.raises(CapitalDemandError):
        ConversionEvidence("oracle:v1", NOW, 60, "ETH", "USD", -1, 1)


def test_demand_freshness_and_provider_capacity_are_independent_constraints():
    value = demand()
    assert value.validate(now=NOW).value == "valid"
    assert value.provider_capacity_requirement.amount > 0
    assert value.demand_expires_at > NOW


def test_aggressiveness_and_goal_caps_reduce_strategy_budget_only():
    value = demand()
    aggressive = apply_aggressiveness_cap(value, 0.5, now=NOW)
    goal = apply_goal_cap(value, 0.5, now=NOW)
    assert aggressive.strategy_budget_consumption.amount <= value.strategy_budget_consumption.amount
    assert goal.strategy_budget_consumption.amount <= value.strategy_budget_consumption.amount


def test_live_family_requires_valid_demand():
    value = demand()
    assert live_eligible_family(value, now=NOW) is True
    assert live_eligible_family(demand(status="unknown"), now=NOW) is False
