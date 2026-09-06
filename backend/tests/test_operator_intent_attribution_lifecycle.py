from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.omar.operator_intent import snapshot_operator_intent


class _Controls:
    def __init__(self, aggression_mode: str, risk_multiplier: float):
        self.aggression_mode = aggression_mode
        self.risk_multiplier = risk_multiplier


class _GoalService:
    def __init__(self, target_amount: str, timeframe_days: float, revision: int):
        self.target_amount = target_amount
        self.timeframe_days = timeframe_days
        self.revision = revision

    def state(self, runtime):
        return {
            "goal": {"target_amount": self.target_amount, "timeframe_days": self.timeframe_days},
            "meta": {"active_goal_id": "goal-1", "goal_revision": self.revision},
        }


def test_operator_intent_is_immutable_per_decision_and_changes_only_future_decisions():
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _cc=SimpleNamespace(controls=_Controls("conservative", 0.40)),
        _wealth_goal_service=_GoalService("100000", 365, 1),
        _ai_recommendation={
            "action": "WAIT",
            "posture": "defensive",
            "confidence": 0.80,
            "source": "test-ai",
        },
    )

    opp1 = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision1 = SimpleNamespace(metadata={})
    intent1, fp1 = snapshot_operator_intent(runtime, opp1, decision1)
    ensure_decision_identity(
        opp1,
        decision1,
        chain_name="ethereum",
        current_block=100,
        operator_intent=intent1,
        intent_fingerprint=fp1,
    )
    frozen1 = dict(opp1.meta["canonical_lineage"]["operator_intent"])

    runtime._cc.controls.aggression_mode = "aggressive"
    runtime._cc.controls.risk_multiplier = 0.90
    runtime._wealth_goal_service.target_amount = "250000"
    runtime._wealth_goal_service.timeframe_days = 90
    runtime._wealth_goal_service.revision = 2
    runtime._ai_recommendation = {
        "action": "EXECUTE",
        "posture": "risk-on",
        "confidence": 0.95,
        "source": "test-ai-v2",
    }

    # Re-resolving the same decision must preserve its original snapshot.
    ensure_decision_identity(opp1, decision1, chain_name="ethereum", current_block=101)
    assert opp1.meta["canonical_lineage"]["operator_intent"] == frozen1
    assert opp1.meta["canonical_lineage"]["intent_fingerprint"] == fp1

    # A new decision receives the new human/AI context.
    opp2 = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision2 = SimpleNamespace(metadata={})
    intent2, fp2 = snapshot_operator_intent(runtime, opp2, decision2)
    ensure_decision_identity(
        opp2,
        decision2,
        chain_name="ethereum",
        current_block=102,
        operator_intent=intent2,
        intent_fingerprint=fp2,
    )
    frozen2 = opp2.meta["canonical_lineage"]["operator_intent"]

    assert frozen2["aggression_mode"] == "aggressive"
    assert frozen2["risk_multiplier"] == 0.90
    assert frozen2["goal"]["target_amount"] == "250000"
    assert frozen2["goal"]["timeframe_days"] == 90
    assert frozen2["ai_recommendation"]["action"] == "EXECUTE"
    assert fp2 != fp1
    assert frozen1["aggression_mode"] == "conservative"
    assert frozen1["goal"]["target_amount"] == "100000"
    assert frozen1["ai_recommendation"]["action"] == "WAIT"
    assert lineage_from_opportunity(opp1)["decision_id"] != lineage_from_opportunity(opp2)["decision_id"]
