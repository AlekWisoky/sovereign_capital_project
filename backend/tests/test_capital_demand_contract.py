from datetime import datetime, timedelta, timezone

import pytest

from victor_ai_bot.capital_demand import CapitalDemand, CapitalDemandError, ConversionEvidence, DemandStatus, Money


def demand(**overrides):
    base = dict(
        correlation_id="trade-1", strategy_family="flash_arb", capital_source="flashloan",
        execution_notional=Money(1_000, "USDC", 6, "USDC"), execution_asset="USDC", execution_decimals=6,
        treasury_denomination="USDC", treasury_decimals=6,
        internal_capital_commitment=Money(0, "USDC", 6, "USDC"), gas_reserve=Money(5, "USDC", 6, "USDC"),
        fee_reserve=Money(2, "USDC", 6, "USDC"), provider_capacity_requirement=Money(1_000, "USDC", 6, "USDC"),
        worst_case_exposure=Money(7, "USDC", 6, "USDC"), strategy_budget_consumption=Money(7, "USDC", 6, "USDC"),
        conversion=None, provenance="test:authoritative", source_identity="treasury:main",
    )
    base.update(overrides)
    return CapitalDemand(**base)


def test_contract_keeps_borrowed_notional_and_treasury_exposure_separate():
    value = demand()
    assert value.execution_notional.amount == 1_000
    assert value.internal_capital_commitment.amount == 0
    assert value.provider_capacity_requirement.amount == 1_000
    assert value.worst_case_exposure.amount > 0
    assert value.strategy_budget_consumption.amount > 0


def test_unknown_identity_or_mixed_treasury_denominations_fail_closed():
    with pytest.raises(CapitalDemandError):
        demand(correlation_id="")
    with pytest.raises(CapitalDemandError):
        demand(gas_reserve=Money(1, "ETH", 18, "ETH"))


def test_conversion_evidence_requires_source_and_positive_ratio():
    now = datetime.now(timezone.utc)
    with pytest.raises(CapitalDemandError):
        ConversionEvidence("", now, 60, "ETH", "USDC", 1, 1)
    with pytest.raises(CapitalDemandError):
        ConversionEvidence("oracle", now, 60, "ETH", "USDC", 0, 1)


def test_stale_conversion_is_not_valid():
    old = datetime.now(timezone.utc) - timedelta(seconds=61)
    evidence = ConversionEvidence("oracle:v1", old, 60, "ETH", "USDC", 2_000, 1)
    with pytest.raises(CapitalDemandError):
        demand(conversion=evidence)


def test_flashloan_zero_internal_commitment_is_not_zero_demand():
    assert demand().validate() is DemandStatus.VALID
    assert demand(strategy_budget_consumption=Money(0, "USDC", 6, "USDC")).validate() is DemandStatus.INVALID
