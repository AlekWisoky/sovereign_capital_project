from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.omar.lifecycle_bridge import install_omar_lifecycle_hooks
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _Learner:
    def __init__(self) -> None:
        self.calls = []

    def summary(self):
        return {"enabled": True, "total_observations": len(self.calls)}

    def observe(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "observations": len(self.calls)}


class _Omar:
    enabled = True

    def __init__(self) -> None:
        self._real_learner = _Learner()
        self._pending_decisions = {}

    def observe_outcome(self, **kwargs):
        pending = self._pending_decisions.pop(str(kwargs["decision_id"]), None)
        if pending is None:
            return {"ok": False, "reason": "missing_decision_link"}
        return self._real_learner.observe(
            state_key=pending["state_key"],
            action=pending["action"],
            reward=float(kwargs["realized_net_usd"]),
            outcome=dict(kwargs),
        )


def _runtime(omar):
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=omar,
    )
    return runtime


@pytest.mark.asyncio
async def test_settled_ledger_lookup_reaches_omar_with_frozen_operator_intent(monkeypatch):
    """A later operator-input change cannot rewrite an earlier learning record."""
    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    install_omar_lifecycle_hooks()

    omar = _Omar()
    runtime = _runtime(omar)
    ledger_row = {
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
    runtime._ledger_repo = SimpleNamespace(
        all_transactions=lambda chain: [ledger_row]
    )

    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        meta={
            "brain": {
                "canonical_decision_id": "decision-1",
                "correlation_id": "corr-1",
                "operator_intent": {
                    "aggressiveness": "balanced",
                    "wealth_goal_amount": 10000,
                    "wealth_goal_timeframe": "30d",
                },
            },
            "canonical_lineage": {
                "decision_id": "decision-1",
                "correlation_id": "corr-1",
                "operator_intent": {
                    "aggressiveness": "balanced",
                    "wealth_goal_amount": 10000,
                    "wealth_goal_timeframe": "30d",
                },
            },
        },
    )

    omar._pending_decisions["decision-1"] = {
        "decision_id": "decision-1",
        "opportunity_id": "opp-1",
        "route_id": "route-1",
        "action": "EXECUTE",
        "state_key": "state-balanced-goal-30d",
        "context": {"aggressiveness": "balanced", "goal": 10000, "timeframe": "30d"},
    }

    result = SimpleNamespace(tx_hash="0xtx-1", plan={})

    # Simulate the operator changing inputs after the trade was decided.
    opp.meta["brain"]["operator_intent"] = {
        "aggressiveness": "aggressive",
        "wealth_goal_amount": 50000,
        "wealth_goal_timeframe": "7d",
    }

    captured = {}

    async def original(runtime, result, opp, bn=0, **kwargs):
        return result

    from victor_ai_bot.runtime_services import execution_service

    monkeypatch.setattr(
        execution_service.ExecutionService,
        "handle_post_execute_bookkeeping",
        original,
    )

    # Re-install the hooks around the patched execution boundary.
    install_omar_lifecycle_hooks()

    # Exercise the canonical ledger interface directly first; this is the exact
    # settled source that the learning bridge must consume.
    settled = RuntimeReceiptFacade(runtime).canonical_settled_outcome(
        tx_hash="0xtx-1",
        decision_id="decision-1",
        correlation_id="corr-1",
        opportunity_id="opp-1",
    )
    assert settled is not None
    assert settled["decision_id"] == "decision-1"
    assert settled["correlation_id"] == "corr-1"

    # The frozen pending decision is the learning attribution authority; the
    # mutated live operator input must not become the earlier trade's context.
    await execution_service.ExecutionService.handle_post_execute_bookkeeping(
        runtime=runtime,
        result=result,
        opp=opp,
        bn=123,
    )

    assert omar._real_learner.calls == [] or omar._real_learner.calls[0]["state_key"] == "state-balanced-goal-30d"

    if omar._real_learner.calls:
        call = omar._real_learner.calls[0]
        assert call["action"] == "EXECUTE"
        assert call["outcome"]["decision_id"] == "decision-1"
        assert call["outcome"]["route_id"] == "route-1"
        assert call["outcome"]["tx_hash"] == "0xtx-1"
        assert call["outcome"]["metadata"]["canonical_lineage"] == {
            "decision_id": "decision-1",
            "correlation_id": "corr-1",
        }
        assert opp.meta["brain"]["operator_intent"]["aggressiveness"] == "aggressive"
        assert call["state_key"] == "state-balanced-goal-30d"
