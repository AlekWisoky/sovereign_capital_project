from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.operator_intent import intent_fingerprint, resolve_operator_intent
from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity


def test_operator_intent_captures_human_goal_and_ai_context_without_authority():
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(
            controls=SimpleNamespace(aggression_mode="aggressive", risk_multiplier=0.8)
        ),
        _wealth_goal_service=SimpleNamespace(
            state=lambda _runtime: {
                "state": {
                    "goal": {
                        "target_wealth_usd": "25000",
                        "target_return_pct": 40,
                        "timeframe_days": 90,
                    },
                    "meta": {"active_goal_id": "goal-1", "goal_revision": 3},
                    "currentReturnPct": 12.5,
                    "drawdownPct": 2.0,
                }
            }
        ),
        _ai_recommendation={
            "action": "reduce_exposure",
            "posture": "defensive",
            "confidence": 0.91,
            "source": "risk-model",
        },
    )

    intent = resolve_operator_intent(runtime)

    assert intent["aggression_mode"] == "aggressive"
    assert intent["risk_multiplier"] == 0.8
    assert intent["goal"]["target_amount"] == "25000"
    assert intent["goal"]["timeframe_days"] == 90.0
    assert intent["ai_recommendation"]["action"] == "reduce_exposure"
    assert intent["authority"] == "operator_intent_only"

    fingerprint = intent_fingerprint(intent)
    assert len(fingerprint) == 24


def test_operator_intent_fingerprint_is_attached_to_canonical_identity():
    intent = {
        "aggression_mode": "conservative",
        "risk_multiplier": 0.6,
        "goal": {"goal_id": "goal-1", "goal_revision": 1},
        "ai_recommendation": {"present": False},
        "authority": "operator_intent_only",
    }
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=intent,
    )

    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"] == identity.decision_id
    assert lineage["correlation_id"] == identity.correlation_id
    assert lineage["operator_intent_fingerprint"] == intent_fingerprint(intent)
    assert decision.metadata["operator_intent"] == intent
    assert decision.metadata["operator_intent_fingerprint"] == intent_fingerprint(intent)


def test_intent_fingerprint_is_not_part_of_decision_or_correlation_identity():
    opp_a = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    opp_b = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision_a = SimpleNamespace(metadata={})
    decision_b = SimpleNamespace(metadata={})

    first = ensure_decision_identity(
        opp_a,
        decision_a,
        chain_name="ethereum",
        current_block=123,
        operator_intent={"aggression_mode": "conservative"},
    )
    second = ensure_decision_identity(
        opp_b,
        decision_b,
        chain_name="ethereum",
        current_block=123,
        operator_intent={"aggression_mode": "aggressive"},
    )

    assert first.decision_id == second.decision_id
    assert first.correlation_id == second.correlation_id
    assert lineage_from_opportunity(opp_a)["operator_intent_fingerprint"] != lineage_from_opportunity(opp_b)["operator_intent_fingerprint"]
