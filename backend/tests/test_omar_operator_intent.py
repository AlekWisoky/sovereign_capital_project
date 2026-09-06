from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.omar.operator_intent import intent_fingerprint, snapshot_operator_intent


class _GoalService:
    def __init__(self, state):
        self._state = state

    def state(self, runtime):
        return {"state": self._state}


def test_operator_intent_snapshot_captures_human_goal_controls_and_ai_recommendation():
    controls = SimpleNamespace(
        aggression_mode="aggressive",
        brain_mode="suggest",
        defensive_mode=False,
        control_mode="auto",
        risk_multiplier=0.75,
        force_gas_mode="fast",
        force_send_mode="private",
    )
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(controls=controls),
        _wealth_goal_service=_GoalService(
            {
                "targetAmount": "100000",
                "timeframeDays": 180,
                "targetReturnPct": 25.0,
                "currentReturnPct": 8.0,
                "drawdownPct": 2.0,
            }
        ),
    )
    opp = SimpleNamespace(
        meta={
            "brain": {
                "ai_recommendation": {"action": "execute", "confidence": 0.92}
            }
        }
    )

    intent, fingerprint = snapshot_operator_intent(runtime, opp, None)

    assert intent["aggression_mode"] == "aggressive"
    assert intent["risk_multiplier"] == 0.75
    assert intent["goal"]["target_amount"] == "100000"
    assert intent["goal"]["timeframe_days"] == 180
    assert intent["ai_recommendation"]["action"] == "execute"
    assert fingerprint == intent_fingerprint(intent)


def test_decision_identity_persists_write_once_operator_intent():
    controls = SimpleNamespace(aggression_mode="aggressive")
    runtime = SimpleNamespace(_cc=SimpleNamespace(controls=controls))
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    first = {"aggression_mode": "aggressive", "goal": {"target_amount": "100000"}}
    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
        operator_intent=first,
        intent_fingerprint="fp-1",
    )

    controls.aggression_mode = "conservative"
    second, second_fp = snapshot_operator_intent(runtime, opp, decision)
    ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=124,
        operator_intent=second,
        intent_fingerprint=second_fp,
    )

    lineage = opp.meta["canonical_lineage"]
    assert lineage["decision_id"] == identity.decision_id
    assert lineage["operator_intent"] == first
    assert lineage["intent_fingerprint"] == "fp-1"
    assert decision.metadata["operator_intent"] == first
    assert decision.metadata["intent_fingerprint"] == "fp-1"
