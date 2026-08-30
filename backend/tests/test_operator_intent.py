from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.operator_intent import intent_fingerprint, resolve_operator_intent


class _GoalService:
    def __init__(self, state):
        self._state = state

    def state(self, runtime):
        return self._state


def test_operator_intent_captures_human_controls_goal_and_ai_recommendation():
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(
            controls=SimpleNamespace(aggression_mode="aggressive", risk_multiplier=0.75)
        ),
        _wealth_goal_service=_GoalService(
            {
                "state": {
                    "goal": {
                        "target_amount": "100000",
                        "target_return_percentage": 25,
                        "timeframe_days": 90,
                    },
                    "meta": {"active_goal_id": "goal-1", "goal_revision": 3},
                    "currentReturnPct": 7.5,
                    "drawdownPct": 2.25,
                }
            }
        ),
        _ai_recommendation={
            "action": "WAIT",
            "posture": "protect_capital",
            "confidence": 0.91,
            "source": "advisor",
        },
    )

    intent = resolve_operator_intent(runtime)

    assert intent["aggression_mode"] == "aggressive"
    assert intent["risk_multiplier"] == 0.75
    assert intent["goal"]["target_amount"] == "100000"
    assert intent["goal"]["target_return_pct"] == 25.0
    assert intent["goal"]["timeframe_days"] == 90.0
    assert intent["goal"]["goal_id"] == "goal-1"
    assert intent["goal"]["goal_revision"] == 3
    assert intent["goal"]["current_return_pct"] == 7.5
    assert intent["goal"]["drawdown_pct"] == 2.25
    assert intent["ai_recommendation"]["action"] == "WAIT"
    assert intent["ai_recommendation"]["confidence"] == 0.91
    assert intent["authority"] == "operator_intent_only"


def test_operator_intent_normalizes_invalid_aggression_and_caps_risk():
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(
            controls=SimpleNamespace(aggression_mode="unsafe", risk_multiplier=9)
        )
    )

    intent = resolve_operator_intent(runtime)

    assert intent["aggression_mode"] == "balanced"
    assert intent["risk_multiplier"] == 1.0


def test_operator_intent_fingerprint_is_stable():
    intent = {"aggression_mode": "balanced", "goal": {"timeframe_days": 30}}
    assert intent_fingerprint(intent) == intent_fingerprint(dict(intent))
    assert len(intent_fingerprint(intent)) == 24


def test_operator_intent_is_persisted_in_canonical_decision_lineage():
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})
    intent = {"aggression_mode": "conservative", "goal": {"target_amount": "50000"}}
    fingerprint = intent_fingerprint(intent)

    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=intent,
        intent_fingerprint=fingerprint,
    )

    assert identity.decision_id
    assert identity.correlation_id
    assert opp.meta["canonical_lineage"]["operator_intent"] == intent
    assert opp.meta["canonical_lineage"]["intent_fingerprint"] == fingerprint
    assert decision.metadata["operator_intent"] == intent
    assert decision.metadata["intent_fingerprint"] == fingerprint
