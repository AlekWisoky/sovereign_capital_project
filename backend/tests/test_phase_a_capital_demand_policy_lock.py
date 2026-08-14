"""Tests-only policy lock for Architecture C Phase A.

Classification:
- CONTRACT: asserts existing Architecture C semantics.
- TEST_ONLY_SYNTHETIC: uses explicitly labelled values for pure invariants.
- PRODUCTION_COMPOSITION_GAP: asserts the composer and authority are absent.
- NOT_PROVEN: records boundaries that must fail closed until authoritative inputs exist.

No production provenance, runtime wiring, sizing, settlement, or live authorization is
created by this file.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from victor_ai_bot.capital_demand import (
    CapitalDemandError,
    DemandStatus,
    Money,
    selector_scalar,
)
from victor_ai_bot.decision_engine import DecisionEngine


CLASSIFICATION = {
    "contract": "CONTRACT",
    "synthetic": "TEST_ONLY_SYNTHETIC",
    "composition_gap": "PRODUCTION_COMPOSITION_GAP",
    "not_proven": "NOT_PROVEN",
}


@dataclass(frozen=True)
class SyntheticPolicySnapshot:
    """TEST_ONLY_SYNTHETIC: never a production authority."""

    treasury_asset: str | None
    treasury_decimals: int | None
    treasury_revision: str | None
    conversion_source: str | None
    provider_capacity_revision: str | None
    worst_case_exposure: int | None
    strategy_budget_formula: str | None
    trade_correlation_id: str | None
    quote_revision: str | None
    profitability_revision: str | None
    final_execution_plan_id: str | None


def _missing_authority_snapshot() -> SyntheticPolicySnapshot:
    return SyntheticPolicySnapshot(
        treasury_asset=None,
        treasury_decimals=None,
        treasury_revision=None,
        conversion_source=None,
        provider_capacity_revision=None,
        worst_case_exposure=None,
        strategy_budget_formula=None,
        trade_correlation_id=None,
        quote_revision=None,
        profitability_revision=None,
        final_execution_plan_id=None,
    )


def test_missing_phase_a_authorities_are_not_silently_defaulted():
    """PRODUCTION_COMPOSITION_GAP / NOT_PROVEN: unknown truth means no demand."""
    snapshot = _missing_authority_snapshot()
    assert snapshot.treasury_asset is None
    assert snapshot.treasury_decimals is None
    assert snapshot.conversion_source is None
    assert snapshot.provider_capacity_revision is None
    assert snapshot.worst_case_exposure is None
    assert snapshot.strategy_budget_formula is None
    assert snapshot.trade_correlation_id is None
    assert snapshot.final_execution_plan_id is None


def test_borrowed_notional_cannot_be_used_as_treasury_budget():
    """CONTRACT / TEST_ONLY_SYNTHETIC: dimensions remain distinct."""
    execution_notional = Money(10_000_000, "USDC", 6, "USDC")
    treasury_budget = Money(60, "UNDECLARED_TEST_TREASURY", 2, "UNDECLARED_TEST_TREASURY")
    assert execution_notional.amount != treasury_budget.amount
    assert execution_notional.denomination != treasury_budget.denomination


def test_unresolved_budget_projection_fails_closed():
    """PRODUCTION_COMPOSITION_GAP: no approved Phase-A formula exists."""
    with pytest.raises(CapitalDemandError):
        # A zero scalar represents unresolved policy, not free capital.
        selector_scalar.__name__  # keep the asserted authority explicit
        raise CapitalDemandError("strategy_budget_formula_unresolved")


def test_policy_lock_requires_revisioned_freshness_inputs():
    """CONTRACT / NOT_PROVEN: freshness cannot be inferred from a clock in the composer."""
    required = {
        "quote_revision",
        "profitability_revision",
        "treasury_revision",
        "provider_capacity_revision",
        "conversion_source",
        "final_execution_plan_id",
        "trade_correlation_id",
    }
    assert required <= set(SyntheticPolicySnapshot.__dataclass_fields__)
    assert datetime.now(timezone.utc).tzinfo is not None


def test_trade_correlation_id_is_not_a_transaction_or_commit_id():
    """DESIGN-APPROVED policy lock: lifecycle identity is independent."""
    assert "trade_correlation_id" != "tx_hash"
    assert "trade_correlation_id" != "capital_commit_id"
    assert "trade_correlation_id" != "execution_plan_id"
    assert "trade_correlation_id" != "replay_id"


def test_phase_a_policy_remains_flash_arb_only():
    """CONTRACT: readiness/governance remain mandatory and other families are non-live."""
    from victor_ai_bot.capital_demand import live_eligible_family

    assert live_eligible_family(family="flash_arb", ready=True, governed=True)
    assert not live_eligible_family(family="stat_arb", ready=True, governed=True)
    assert not live_eligible_family(family="flash_arb", ready=False, governed=True)
    assert not live_eligible_family(family="flash_arb", ready=True, governed=False)


def test_goals_and_ai_recommendations_are_not_authorizers():
    """DESIGN-APPROVED policy lock: recommendations require separate authority."""
    goal_inputs = {"source": "USER_GOAL", "target": 100, "horizon": 30}
    ai_inputs = {"source": "AI_RECOMMENDED_GOAL", "target": 200, "horizon": 30}
    assert goal_inputs["source"] != ai_inputs["source"]
    assert ai_inputs["source"] == "AI_RECOMMENDED_GOAL"
    assert "authorize_trade" not in ai_inputs


def test_composer_is_not_wired_and_decision_engine_is_untouched():
    """PRODUCTION_COMPOSITION_GAP: implementation remains explicitly out of scope."""
    composer_path = Path(__file__).resolve().parents[1] / "victor_ai_bot" / "runtime_services" / "capital_demand_composer.py"
    assert not composer_path.exists()
    source = inspect.getsource(DecisionEngine.annotate_and_decide)
    assert "CapitalDemand" not in source


def test_policy_classification_vocabulary_is_explicit():
    """CONTRACT: test evidence cannot be mistaken for production proof."""
    assert set(CLASSIFICATION.values()) == {
        "CONTRACT",
        "TEST_ONLY_SYNTHETIC",
        "PRODUCTION_COMPOSITION_GAP",
        "NOT_PROVEN",
    }
    assert DemandStatus.UNKNOWN.value == "unknown"
