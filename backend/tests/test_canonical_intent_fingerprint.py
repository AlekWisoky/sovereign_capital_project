from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.omar.operator_intent import (
    OperatorIntentSnapshot,
    operator_intent_fingerprint,
)


def test_intent_fingerprint_is_stable_and_context_sensitive():
    intent = OperatorIntentSnapshot(
        control_mode="auto",
        aggression_mode="aggressive",
        brain_mode="auto",
        risk_multiplier=0.75,
        desired_wealth_goal={"target_amount": "100000", "timeframe_days": 180},
        ai_recommendation={"action": "execute", "confidence": 0.92},
    )

    first = operator_intent_fingerprint(intent)
    second = operator_intent_fingerprint(intent.to_dict())
    changed = operator_intent_fingerprint(
        OperatorIntentSnapshot(
            control_mode="auto",
            aggression_mode="balanced",
            brain_mode="auto",
            risk_multiplier=0.75,
            desired_wealth_goal={"target_amount": "100000", "timeframe_days": 180},
            ai_recommendation={"action": "execute", "confidence": 0.92},
        )
    )

    assert first == second
    assert first != changed


def test_decision_identity_carries_intent_snapshot_and_fingerprint():
    opportunity = SimpleNamespace(meta={})
    decision = SimpleNamespace(metadata={})
    intent = OperatorIntentSnapshot(
        control_mode="auto",
        aggression_mode="aggressive",
        brain_mode="auto",
        risk_multiplier=0.75,
        desired_wealth_goal={"target_amount": "100000", "timeframe_days": 180},
        ai_recommendation={"action": "execute", "confidence": 0.92},
    )
    fingerprint = operator_intent_fingerprint(intent)

    identity = ensure_decision_identity(
        opportunity,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=intent,
        intent_fingerprint=fingerprint,
    )

    assert decision.decision_id == identity.decision_id
    assert decision.correlation_id == identity.correlation_id
    assert decision.metadata["intent_fingerprint"] == fingerprint
    assert decision.metadata["operator_intent_snapshot"] == intent.to_dict()
    assert decision.metadata["canonical_lineage"]["intent_fingerprint"] == fingerprint
    assert opportunity.meta["canonical_lineage"]["intent_fingerprint"] == fingerprint


def test_intent_changes_do_not_rewrite_an_existing_fingerprint():
    opportunity = SimpleNamespace(meta={})
    decision = SimpleNamespace(metadata={})
    first = OperatorIntentSnapshot(aggression_mode="balanced")
    second = OperatorIntentSnapshot(aggression_mode="aggressive")
    first_fp = operator_intent_fingerprint(first)
    second_fp = operator_intent_fingerprint(second)

    ensure_decision_identity(
        opportunity,
        decision,
        operator_intent=first,
        intent_fingerprint=first_fp,
    )
    ensure_decision_identity(
        opportunity,
        decision,
        operator_intent=second,
        intent_fingerprint=second_fp,
    )

    # A decision identity is write-once for attribution: later operator-control
    # changes belong to future decisions, not historical attribution.
    assert decision.metadata["intent_fingerprint"] == first_fp
    assert decision.metadata["operator_intent_snapshot"] == first.to_dict()
