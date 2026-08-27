from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.omar.lifecycle_bridge import install_omar_lifecycle_hooks
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.runtime_services import execution_service
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


@pytest.mark.asyncio
async def test_production_settlement_reaches_omar_with_frozen_intent(monkeypatch):
    """The settled ledger drives learning; later controls cannot rewrite history."""
    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()

    async def fake_bookkeeping(self, runtime, opp, result, *, bn, latency_ms, mode):
        return result

    monkeypatch.setattr(
        execution_service.ExecutionService,
        "handle_post_execute_bookkeeping",
        fake_bookkeeping,
    )
    install_omar_lifecycle_hooks()

    omar = OmarRuntime(OmarConfig(enabled=True, self_play_enabled=False), chain_name="ethereum")
    captured = []

    def capture_observe(*, state_key, action, reward, outcome):
        captured.append(
            {
                "state_key": state_key,
                "action": action,
                "reward": reward,
                "outcome": outcome,
            }
        )
        return {"ok": True, "observations": 1}

    assert omar._real_learner is not None
    monkeypatch.setattr(omar._real_learner, "observe", capture_observe)

    runtime = object.__new__(RuntimeReceiptFacade)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = omar
    runtime._ledger_repo = SimpleNamespace(
        all_transactions=lambda chain: [
            {
                "transaction_id": "settlement-1",
                "tx_type": "receipt_settlement",
                "receipt_id": "0xtx-1",
                "ts_ms": 100,
                "metadata": {
                    "canonical_lineage": {
                        "decision_id": "decision-1",
                        "correlation_id": "corr-1",
                    },
                    "opportunity_id": "opp-1",
                    "route_id": "route-1",
                    "expected_net_usd": 4.0,
                    "realized_net_usd": 7.0,
                    "amount_in_wei": 100,
                    "gas_cost_usd": 0.2,
                    "slippage_bps": 3.0,
                    "latency_ms": 80,
                    "truth_verified": True,
                },
            }
        ]
    )

    intent = {
        "aggression_mode": "balanced",
        "risk_multiplier": 0.7,
        "goal": {
            "target_amount": "10000",
            "timeframe_days": 30,
            "goal_revision": 1,
        },
        "ai_recommendation": {"action": "hold", "confidence": 0.8},
    }
    omar.observe_decision(
        decision_id="decision-1",
        opportunity_id="opp-1",
        route_id="route-1",
        action="EXECUTE",
        state_key="state-balanced-goal-30d",
        context={"operator_intent": intent},
        metadata={"canonical_lineage": {"decision_id": "decision-1", "correlation_id": "corr-1"}},
    )

    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        meta={
            "brain": {
                "canonical_decision_id": "decision-1",
                "correlation_id": "corr-1",
                "operator_intent": intent.copy(),
            },
            "canonical_lineage": {
                "decision_id": "decision-1",
                "correlation_id": "corr-1",
                "operator_intent": intent.copy(),
            },
        },
    )
    result = SimpleNamespace(tx_hash="0xtx-1", plan={})

    intent["aggression_mode"] = "aggressive"
    intent["goal"]["target_amount"] = "50000"
    opp.meta["brain"]["operator_intent"] = {
        "aggression_mode": "aggressive",
        "risk_multiplier": 1.0,
        "goal": {"target_amount": "50000", "timeframe_days": 7, "goal_revision": 2},
        "ai_recommendation": {"action": "buy", "confidence": 0.95},
    }

    settled = runtime.canonical_settled_outcome(
        tx_hash="0xtx-1",
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
    assert settled is not None
    assert settled["status"] == "settled"
    assert settled["decision_id"] == "decision-1"
    assert settled["correlation_id"] == "corr-1"

    await execution_service.ExecutionService.handle_post_execute_bookkeeping(
        runtime=runtime,
        opp=opp,
        result=result,
        bn=123,
        latency_ms=12,
        mode="auto",
    )

    assert len(captured) == 1
    learning = captured[0]
    assert learning["state_key"] == "state-balanced-goal-30d"
    assert learning["action"] == "EXECUTE"
    assert learning["outcome"]["decision_id"] == "decision-1"
    assert learning["outcome"]["tx_hash"] == "0xtx-1"
    assert learning["outcome"]["metadata"]["canonical_lineage"] == {
        "decision_id": "decision-1",
        "correlation_id": "corr-1",
    }
    assert learning["outcome"]["metadata"]["operator_intent"]["aggression_mode"] == "balanced"
    assert learning["outcome"]["metadata"]["operator_intent"]["goal"]["target_amount"] == "10000"
    assert learning["outcome"]["metadata"]["operator_intent"]["goal"]["timeframe_days"] == 30
    assert opp.meta["brain"]["operator_intent"]["aggression_mode"] == "aggressive"
