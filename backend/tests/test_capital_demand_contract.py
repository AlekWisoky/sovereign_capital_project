from datetime import datetime, timedelta, timezone

import pytest

from victor_ai_bot.capital_demand import Capacity, CapitalDemand, CapitalDemandError, DemandSource, DemandStatus, Money, Provenance

NOW = datetime(2026, 8, 13, 18, 0, tzinfo=timezone.utc)


def demand(**overrides):
    provenance = Provenance("test", "capital-demand-v2", "treasury:main", "opp-1", NOW, "trade-1", "inputs-1")
    base = dict(
        correlation_id="trade-1", strategy_family="flash_arb", capital_source="flashloan",
        execution_notional=Money(10_000_000, "USDC", 6, "USDC"), execution_asset="USDC", execution_decimals=6,
        treasury_denomination="USD", treasury_decimals=2,
        internal_capital_commitment=Money(0, "USD", 2, "USD"), gas_reserve=Money(50, "USD", 2, "USD"),
        fee_reserve=Money(10, "USD", 2, "USD"), provider_capacity_requirement=Capacity(12_000_000, "USDC", "aave", NOW, NOW + timedelta(minutes=5)),
        worst_case_exposure=Money(60, "USD", 2, "USD"), strategy_budget_consumption=Money(60, "USD", 2, "USD"),
        provenance=provenance, demand_generated_at=NOW, demand_expires_at=NOW + timedelta(minutes=5),
        max_worst_case_exposure=Money(100, "USD", 2, "USD"),
    )
    base.update(overrides)
    return CapitalDemand(**base)


def test_seven_exposure_dimensions_remain_distinct():
    value = demand()
    assert value.execution_notional.amount == 10_000_000
    assert value.internal_capital_commitment.amount == 0
    assert value.gas_reserve.amount == 50
    assert value.fee_reserve.amount == 10
    assert value.provider_capacity_requirement.amount == 12_000_000
    assert value.worst_case_exposure.amount == 60
    assert value.strategy_budget_consumption.amount == 60


def test_flashloan_zero_principal_is_valid_only_with_other_constraints():
    assert demand().validate(now=NOW) is DemandStatus.VALID
    assert demand(gas_reserve=Money(0, "USD", 2, "USD")).validate(now=NOW) is DemandStatus.INVALID


def test_money_identity_and_provenance_are_explicit():
    with pytest.raises(CapitalDemandError):
        Money(1, "", 6, "USDC")
    with pytest.raises(CapitalDemandError):
        demand(provenance=Provenance("test", "v1", "source", "event", NOW, "other-trade", "inputs"))


def test_conflicting_authoritative_sources_fail_closed():
    source = DemandSource("other-source", Money(61, "USD", 2, "USD"))
    assert demand(corroborating_sources=(source,)).validate(now=NOW) is DemandStatus.CONFLICTING


def test_identical_corroborating_source_is_acceptable():
    source = DemandSource("other-source", Money(60, "USD", 2, "USD"))
    assert demand(corroborating_sources=(source,)).validate(now=NOW) is DemandStatus.VALID


def test_execution_redundant_identity_cannot_disagree():
    with pytest.raises(CapitalDemandError):
        demand(execution_decimals=18)
