from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.omar.production_lineage_bridge import (
    install_production_lineage_bridge,
)


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
            "meta": {
                "active_goal_id": "goal-1",
                "goal_revision": self.revision,
            },
        }


@pytest.mark.asyncio
async def test_operator_intent_is_immutable_per_decision_through_execution_boundary():
    """Changing operator inputs between decisions must not rewrite prior attribution."""
    from victor_ai_bot.runtime_services.execution_service import ExecutionService

    install_production_lineage_bridge()

    runtime = object.__new__(SimpleNamespace)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._cc = SimpleNamespace(
        controls=_Controls("conservative", 0.40),
    )
    runtime._wealth_goal_service = _GoalService("100000", 365, 1)
    runtime._ai_recommendation = {
        "action": "WAIT",
        "posture": "defensive",
        "confidence": 0.80,
        "source": "test-ai",
    }

    original = ExecutionService.handle_post_execute_bookkeeping
    runtime._record_exec = lambda *args, **kwargs: None
    runtime.metrics = SimpleNamespace()
    runtime._lat = None
    runtime._last_submitted_block = 0

    async def record(*args, **kwargs):
        return None

    runtime._record_exec = record

    opp1 = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision1 = SimpleNamespace(metadata={})
    runtime._apply_omar_to_candidate(opp1, decision1, current_block=100)
    first = dict(opp1.meta["canonical_lineage"]["operator_intent"])
    first_fp = opp1.meta["canonical_lineage"]["intent_fingerprint"]

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

    result = SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        plan={},
    )
    await original(
        runtime,
        opp1,
        result,
        bn=101,
        latency_ms=5,
        mode="auto",
    )

    assert opp1.meta["canonical_lineage"]["operator_intent"] == first
    assert opp1.meta["canonical_lineage"]["intent_fingerprint"] == first_fp
    assert lineage_from_opportunity(opp1)["decision_id"] == decision1.metadata[
        "canonical_decision_id"
    ]

    opp2 = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision2 = SimpleNamespace(metadata={})
    runtime._apply_omar_to_candidate(opp2, decision2, current_block=102)
    second = opp2.meta["canonical_lineage"]["operator_intent"]
    second_fp = opp2.meta["canonical_lineage"]["intent_fingerprint"]

    assert second["aggression_mode"] == "aggressive"
    assert second["risk_multiplier"] == 0.90
    assert second["goal"]["target_amount"] == "250000"
    assert second["goal"]["timeframe_days"] == 90.0
    assert second["ai_recommendation"]["action"] == "EXECUTE"
    assert second_fp != first_fp
    assert first["aggression_mode"] == "conservative"
    assert first["goal"]["target_amount"] == "100000"
    assert first["ai_recommendation"]["action"] == "WAIT"
