from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.production_lineage_bridge import _attach_operator_intent
from victor_ai_bot.operator_intent import intent_fingerprint, resolve_operator_intent


class _GoalService:
    def state(self, runtime):
        return {
            "state": {
                "goal": {
                    "target_amount": "100000",
                    "target_return_pct": 25,
                    "timeframe_days": 180,
                },
                "meta": {"active_goal_id": "goal-1", "goal_revision": 4},
                "current_return_pct": 8.5,
                "drawdown_pct": 2.0,
            }
        }


def _runtime():
    controls = SimpleNamespace(aggression_mode="aggressive", risk_multiplier=0.8)
    return SimpleNamespace(
        _cc=SimpleNamespace(controls=controls),
        _wealth_goal_service=_GoalService(),
        _ai_recommendation={
            "action": "increase_selectivity",
            "posture": "risk_aware",
            "confidence": 0.91,
            "source": "operator_assistant",
        },
    )


def test_operator_intent_normalizes_human_goal_and_ai_context():
    intent = resolve_operator_intent(_runtime())

    assert intent["aggression_mode"] == "aggressive"
    assert intent["risk_multiplier"] == 0.8
    assert intent["goal"]["target_amount"] == "100000"
    assert intent["goal"]["target_return_pct"] == 25.0
    assert intent["goal"]["timeframe_days"] == 180.0
    assert intent["goal"]["goal_id"] == "goal-1"
    assert intent["goal"]["goal_revision"] == 4
    assert intent["ai_recommendation"]["confidence"] == 0.91
    assert intent["authority"] == "operator_intent_only"


def test_operator_intent_fingerprint_and_attribution_survive_decision_boundary():
    runtime = _runtime()
    opp = SimpleNamespace(id="opp-1", meta={})
    decision = SimpleNamespace(metadata={})

    attribution = _attach_operator_intent(opp, decision, runtime)

    assert attribution["fingerprint"] == intent_fingerprint(attribution["intent"])
    assert opp.meta["operator_intent"] == attribution
    assert decision.metadata["operator_intent"] == attribution
    assert attribution["authority"] == "operator_intent_only"
