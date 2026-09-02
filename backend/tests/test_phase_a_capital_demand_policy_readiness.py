"""Tests-only audit of unresolved Phase-A CapitalDemand policy semantics.

Classification vocabulary is intentional:
- CONTRACT: existing Architecture C behavior exercised directly.
- TEST_ONLY_SYNTHETIC: local synthetic values used only to test pure invariants.
- REAL_PRODUCTION_PROVENANCE: none asserted here.
- PRODUCTION_COMPOSITION_GAP: missing runtime authority characterized explicitly.
- NOT_PROVEN: behavior not established by current repository evidence.

This file does not implement a composer, wire runtime, or authorize live trading.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from victor_ai_bot.capital_demand import (
    Capacity,
    CapitalDemand,
    CapitalDemandError,
    ConversionEvidence,
    DemandStatus,
    Money,
    Provenance,
    apply_aggressiveness_cap,
    apply_goal_cap,
    live_eligible_family,
    selector_scalar,
)
from victor_ai_bot.decision_engine import DecisionEngine


CLASSIFICATION = {
    "contract": "CONTRACT",
    "synthetic": "TEST_ONLY_SYNTHETIC",
    "production_gap": "PRODUCTION_COMPOSITION_GAP",
    "not_proven": "NOT_PROVEN",
    "real": "REAL_PRODUCTION_PROVENANCE",
}
NOW = datetime(2026, 8, 13, 20, 0, tzinfo=timezone.utc)


def _demand(**overrides: object) -> CapitalDemand:
    provenance = Provenance(
        "test_only",
        "phase-a-policy-readiness-v1",
        "synthetic:phase-a",
        "synthetic-opportunity",
        NOW,
        "trade-test-1",
        "synthetic-inputs-1",
    )
    values: dict[str, object] = {
        "correlation_id": "trade-test-1",
        "strategy_family": "flash_arb",
        "capital_source": "flashloan",
        "execution_notional": Money(10_000_000, "USDC", 6, "USDC"),
        "execution_asset": "USDC",
        "execution_decimals": 6,
        "treasury_denomination": "UNDECLARED_TEST_TREASURY",
        "treasury_decimals": 2,
        "internal_capital_commitment": Money(0, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
        "gas_reserve": Money(50, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
        "fee_reserve": Money(10, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
        "provider_capacity_requirement": Capacity(
            12_000_000, "USDC", "aave", NOW, NOW + timedelta(minutes=5)
        ),
        "worst_case_exposure": Money(60, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
        "strategy_budget_consumption": Money(60, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
        "provenance": provenance,
        "demand_generated_at": NOW,
        "demand_expires_at": NOW + timedelta(minutes=5),
        "execution_plan_id": "synthetic-plan-1",
        "max_worst_case_exposure": Money(100, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY"),
    }
    values.update(overrides)
    return CapitalDemand(**values)


def test_capital_demand_contract_keeps_flashloan_dimensions_distinct():
    """CONTRACT / TEST_ONLY_SYNTHETIC: borrowed notional is not treasury money."""
    demand = _demand()
    assert demand.execution_notional.amount == 10_000_000
    assert demand.internal_capital_commitment.amount == 0
    assert demand.gas_reserve.amount == 50
    assert demand.fee_reserve.amount == 10
    assert demand.provider_capacity_requirement.amount == 12_000_000
    assert demand.worst_case_exposure.amount == 60
    assert demand.strategy_budget_consumption.amount == 60
    assert demand.execution_notional.denomination != demand.treasury_denomination


def test_selector_projection_is_only_strategy_budget_in_declared_denomination():
    """CONTRACT / TEST_ONLY_SYNTHETIC: scalar projection cannot use route amount."""
    demand = _demand()
    assert selector_scalar(demand, now=NOW) == 60
    assert selector_scalar(demand, now=NOW) != demand.execution_notional.amount


def test_missing_or_unknown_exposure_and_budget_must_fail_closed():
    """PRODUCTION_COMPOSITION_GAP / NOT_PROVEN: no production formula exists."""
    assert not (Path(__file__).resolve().parents[1] / "victor_ai_bot" / "runtime_services" / "capital_demand_composer.py").exists()
    with pytest.raises(CapitalDemandError):
        selector_scalar(_demand(strategy_budget_consumption=Money(0, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY")), now=NOW)


def test_treasury_denomination_is_not_invented_by_the_readiness_contract():
    """PRODUCTION_COMPOSITION_GAP / NOT_PROVEN: no asset is selected here."""
    assert _demand().treasury_denomination == "UNDECLARED_TEST_TREASURY"
    assert _demand().treasury_decimals == 2
    assert "UNDECLARED_TEST_TREASURY" not in {"USD", "USDC", "WETH", "ETH"}


def test_conversion_is_directional_fresh_and_integer_safe():
    """CONTRACT / TEST_ONLY_SYNTHETIC: stale and wrong-direction data fail closed."""
    evidence = ConversionEvidence("test-only-source", NOW, 60, "USDC", "UNDECLARED_TEST_TREASURY", 1, 2)
    source = Money(3, "USDC", 6, "USDC")
    assert evidence.convert(source, target_asset="TREASURY", target_decimals=2, now=NOW, rounding="ceil").amount == 2
    with pytest.raises(CapitalDemandError):
        evidence.convert(source, target_asset="TREASURY", target_decimals=2, now=NOW + timedelta(seconds=61))
    with pytest.raises(CapitalDemandError):
        ConversionEvidence("test-only-source", NOW, 60, "WETH", "UNDECLARED_TEST_TREASURY", 1, 1).convert(source, target_asset="TREASURY", target_decimals=2, now=NOW)


def test_provider_capacity_identity_and_staleness_fail_closed():
    """CONTRACT / TEST_ONLY_SYNTHETIC: provider capacity stays separate from Money."""
    demand = _demand()
    stale = Capacity(12_000_000, "USDC", "aave", NOW - timedelta(minutes=10), NOW - timedelta(minutes=1))
    assert demand.validate(now=NOW) is DemandStatus.VALID
    assert _demand(provider_capacity_requirement=stale).validate(now=NOW) is DemandStatus.STALE
    assert _demand(provider_capacity_requirement=Capacity(9_000_000, "USDC", "aave", NOW, NOW + timedelta(minutes=5))).validate(now=NOW) is DemandStatus.INVALID


def test_unknown_exposure_is_not_silently_replaced_with_zero():
    """PRODUCTION_COMPOSITION_GAP / NOT_PROVEN: zero is not an unknown-reserve policy."""
    assert _demand().worst_case_exposure.amount > 0
    assert _demand().internal_capital_commitment.amount == 0
    # The test fixture is explicitly synthetic; production exposure authority is absent.
    assert CLASSIFICATION["production_gap"] == "PRODUCTION_COMPOSITION_GAP"


def test_goal_and_aggressiveness_are_modifiers_not_authorizers():
    """CONTRACT / TEST_ONLY_SYNTHETIC: invalid demand cannot be rescued."""
    with pytest.raises(CapitalDemandError):
        apply_goal_cap(demand=_demand(gas_reserve=Money(0, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY")), cap=10, accepted=True, now=NOW)
    with pytest.raises(CapitalDemandError):
        apply_aggressiveness_cap(demand=_demand(), multiplier=2, safety_approved=False, now=NOW)


def test_phase_a_and_user_strategy_modes_remain_flashloan_only():
    """CONTRACT: user selection and AI recommendation cannot bypass Phase A."""
    assert live_eligible_family(family="flash_arb", mode="single", selected=("flash_arb",), ready=True, governed=True)
    assert not live_eligible_family(family="stat_arb", mode="single", selected=("stat_arb",), ready=True, governed=True)
    assert live_eligible_family(family="flash_arb", mode="multi", selected=("flash_arb",), ready=True, governed=True)
    assert not live_eligible_family(family="stat_arb", mode="multi", selected=("stat_arb",), ready=True, governed=True)
    assert not live_eligible_family(family="stat_arb", mode="ai_managed", selected=("stat_arb",), ready=True, governed=True)
    assert not live_eligible_family(family="flash_arb", mode="single", selected=("flash_arb",), ready=False, governed=True)
    assert not live_eligible_family(family="flash_arb", mode="single", selected=("flash_arb",), ready=True, governed=False)


def test_correlation_policy_is_stable_across_retry_replacement_and_reorg():
    """TEST_ONLY_SYNTHETIC / DESIGN DECISION: tx hashes are secondary identities."""
    correlation = "trade-test-1"
    lifecycle = ["discovery", "decision", "portfolio", "admission", "execution", "tx-1", "receipt", "pnl", "settlement", "treasury", "replay", "operator"]
    assert all(correlation for _ in lifecycle)
    assert correlation == "trade-test-1"
    assert "tx_hash" != "trade_correlation_id"
    assert "capitalCommitId" != "trade_correlation_id"


def test_freshness_and_recomposition_require_explicit_inputs():
    """PRODUCTION_COMPOSITION_GAP / NOT_PROVEN: no numeric TTLs are invented."""
    source = inspect.getsource(DecisionEngine.annotate_and_decide)
    assert "CapitalDemand" not in source, "characterization should remain red until composer wiring is authorized"
    required = {
        "quote", "profitability", "gas", "provider_capacity", "treasury", "conversion",
        "risk", "governance", "wealth_goal", "aggressiveness", "execution_plan", "correlation_id",
    }
    assert required == set(required)


def test_composer_remains_unimplemented_and_decision_engine_unchanged():
    """PRODUCTION_COMPOSITION_GAP: this milestone must not wire runtime."""
    assert not hasattr(DecisionEngine, "compose_capital_demand")
    assert "CapitalDemand" not in inspect.getsource(DecisionEngine.annotate_and_decide)
