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
    assert demand().validate(now=NOW) == demand().status
    low_capacity = Capacity(9_000_000, "USDC", "aave", NOW, NOW + timedelta(minutes=5))
    assert demand(provider_capacity_requirement=low_capacity).validate(now=NOW).value == "invalid"
    expired_capacity = Capacity(12_000_000, "USDC", "aave", NOW - timedelta(minutes=10), NOW - timedelta(minutes=1))
    assert demand(provider_capacity_requirement=expired_capacity).validate(now=NOW).value == "stale"
    assert demand(demand_expires_at=NOW - timedelta(seconds=1)).validate(now=NOW).value == "stale"


def test_goal_and_aggressiveness_are_modifiers_not_authorizers():
    with pytest.raises(CapitalDemandError):
        apply_goal_cap(demand=demand(), cap=1, accepted=False, now=NOW)
    reduced = apply_goal_cap(demand=demand(), cap=20, accepted=True, now=NOW)
    assert reduced.strategy_budget_consumption.amount == 20
    with pytest.raises(CapitalDemandError):
        apply_aggressiveness_cap(demand=demand(gas_reserve=Money(0, "USD", 2, "USD")), multiplier=2, safety_approved=True, now=NOW)


def test_phase_a_rollout_policy_is_contract_only():
    assert live_eligible_family(family="flash_arb", ready=True, governed=True)
    assert not live_eligible_family(family="stat_arb", ready=True, governed=True)
    assert not live_eligible_family(family="flash_arb", ready=False, governed=True)
    assert not live_eligible_family(family="flash_arb", ready=True, governed=False)
    assert not live_eligible_family(family="stat_arb", mode="ai_managed", selected=("stat_arb",), ready=True, governed=True)