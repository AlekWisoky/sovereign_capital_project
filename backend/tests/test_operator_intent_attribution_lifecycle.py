from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.operator_intent import intent_fingerprint, resolve_operator_intent
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
from victor_ai_bot.runtime_services.execution_service import ExecutionService


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
            "goal": {
                "target_amount": self.target_amount,
                "timeframe_days": self.timeframe_days,
            },
            "meta": {"active_goal_id": "goal-1", "goal_revision": self.revision},
        }


@pytest.mark.asyncio
async def test_operator_intent_snapshot_survives_execution_after_inputs_change():
    """A decision owns its intent snapshot; later changes affect only later decisions."""
    install_production_lineage_bridge()

    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _cc=SimpleNamespace(controls=_Controls("conservative", 0.40)),
        _wealth_goal_service=_GoalService("100000", 365, 1),
        _ai_recommendation={
            "action": "WAIT",
            "posture": "defensive",
            "confidence": 0.80,
            "source": "ai-v1",
        },
        metrics=SimpleNamespace(),
        _lat=None,
        _last_submitted_block=0,
    )

    async def record(*args, **kwargs):
        return None

    runtime._record_exec = record

    opp1 = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision1 = SimpleNamespace(metadata={})
    runtime._apply_omar_to_candidate(opp1, decision1, current_block=100)
    intent1 = dict(opp1.meta["canonical_lineage"]["operator_intent"])
    fp1 = opp1.meta["canonical_lineage"]["intent_fingerprint"]

    runtime._cc.controls.aggression_mode = "aggressive"
    runtime._cc.controls.risk_multiplier = 0.90
    runtime._wealth_goal_service.target_amount = "250000"
    runtime._wealth_goal_service.timeframe_days = 90
    runtime._wealth_goal_service.revision = 2
    runtime._ai_recommendation = {
        "action": "EXECUTE",
        "posture": "risk-on",
        "confidence": 0.95,
        "source": "ai-v2",
    }

    result = SimpleNamespace(ok=True, dry_run=False, submitted=True, plan={})
    await ExecutionService.handle_post_execute_bookkeeping(
        runtime, opp1, result, bn=101, latency_ms=5, mode="auto"
    )

    assert opp1.meta["canonical_lineage"]["operator_intent"] == intent1
    assert opp1.meta["canonical_lineage"]["intent_fingerprint"] == fp1
    assert result.plan["operator_intent"] == intent1
    assert result.plan["intent_fingerprint"] == fp1
    assert result.plan["canonical_lineage"]["decision_id"] == decision1.metadata[
        "canonical_decision_id"
    ]

    opp2 = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision2 = SimpleNamespace(metadata={})
    runtime._apply_omar_to_candidate(opp2, decision2, current_block=102)
    intent2 = opp2.meta["canonical_lineage"]["operator_intent"]
    fp2 = opp2.meta["canonical_lineage"]["intent_fingerprint"]

    assert intent2["aggression_mode"] == "aggressive"
    assert intent2["risk_multiplier"] == 0.90
    assert intent2["goal"]["target_amount"] == "250000"
    assert intent2["goal"]["timeframe_days"] == 90.0
    assert intent2["ai_recommendation"]["action"] == "EXECUTE"
    assert fp2 == intent_fingerprint(intent2)
    assert fp2 != fp1
    assert lineage_from_opportunity(opp1)["decision_id"] != lineage_from_opportunity(opp2)["decision_id"]


def test_operator_intent_remains_context_not_execution_authority():
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(controls=_Controls("aggressive", 1.0)),
        _wealth_goal_service=_GoalService("999999", 30, 7),
        _ai_recommendation={"action": "EXECUTE", "confidence": 0.99},
    )
    intent = resolve_operator_intent(runtime)
    assert intent["authority"] == "operator_intent_only"
    assert "signer" not in intent
    assert "approval" not in intent
    assert "capital_authority" not in intent
