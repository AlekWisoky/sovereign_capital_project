from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services import runtime_loop_entry_facade
from victor_ai_bot.runtime_services.runtime_after_tick_facade import RuntimeAfterTickFacade
from victor_ai_bot.runtime_services.runtime_auto_queue_facade import RuntimeAutoQueueFacade
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import (
    RuntimeDecisionFinalizeFacade,
)
from victor_ai_bot.runtime_services.runtime_tick_iteration_facade import (
    RuntimeTickIterationFacade,
)
from victor_ai_bot.runtime_services.runtime_tick_scan_facade import RuntimeTickScanFacade


class _Rpc:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def block_number(self):
        return 777


class _Runtime(
    RuntimeLoopEntryFacade,
    RuntimeTickIterationFacade,
    RuntimeTickScanFacade,
    RuntimeDecisionFinalizeFacade,
    RuntimeAutoQueueFacade,
    RuntimeAfterTickFacade,
    RuntimeDecisionFacade,
):
    def __init__(self):
        self.events: list[str] = []
        self._pending = {}
        self._opps = []
        self._auto_queue = []
        self._auto_queue_block = 0
        self._auto_trading = True
        self._exec_task = None
        self._last_submitted_block = 0
        self._errors: list[str] = []
        self.metrics = SimpleNamespace(last_block=0, last_error="", failed_ticks=0)
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(chain_id=1),
            execution=SimpleNamespace(max_pending_txs=1, brain_mode="auto"),
        )
        self.rpc_manager = SimpleNamespace(best_read=lambda: "http://read")
        self._cb = SimpleNamespace(
            allow_auto_trading=lambda: True,
            remaining_cooldown_s=lambda: 0,
        )
        self._anomaly = SimpleNamespace(observe_rpc_error=lambda **kwargs: False)
        self.cache = SimpleNamespace(reset_if_new_block=lambda *args: None)
        self._runtime_control_service = None
        self._execution_service = None

        self.opp = SimpleNamespace(
            id="opp-trace",
            route_id="route-trace",
            can_execute=True,
            meta={
                "safety": {"exec_ready": True, "profit_after_costs_wei": "100"},
                "profit_after_costs": "100",
            },
        )
        self.decision = SimpleNamespace(
            action="trade",
            opp_id="opp-trace",
            route_id="route-trace",
            size_mult=1.0,
            borrow_mult=1.0,
            gas_mode="standard",
            metadata={},
            portfolio=["opp-trace"],
        )

    def _resolve_amount_in(self):
        self.events.append("resolve_amount_in")
        return 1

    async def _scan_primary_opportunities(self, rpc, *, current_block, amount_in):
        self.events.append("scan_primary")
        assert current_block == 777
        assert amount_in == 1
        self._opps = [self.opp]
        return [self.opp]

    async def _annotate_can_execute(self, rpc, opps):
        self.events.append("annotate_can_execute")

    async def _gas_signal_snapshot(self, rpc):
        self.events.append("gas_signals")
        return {"basefee_gwei": 20.0, "priority_gwei": 1.0}

    def _market_signal_snapshot(self, opps):
        self.events.append("market_signals")
        return {
            "mev_risk": 0.1,
            "pending_rate": 0.0,
            "avg_margin_ratio": 1.0,
            "volatility_proxy": 0.1,
        }

    def _behave_regime_state(self, **kwargs):
        self.events.append("behave_regime")
        return {"regime_label": "balanced"}

    def _resolve_market_regime(self, **kwargs):
        self.events.append("market_regime")
        return {"regime_label": "balanced"}

    def _apply_treasury_guidance(self, **kwargs):
        self.events.append("treasury_guidance")
        return {"treasury_state": {}, "behave_state": kwargs["behave_state"]}

    def _run_predecision_additive_state(self, **kwargs):
        self.events.append("predecision_state")
        return {"mev_snap": {"risk": 0.1}}

    def _safe_decide_opportunities(self, *args, **kwargs):
        self.events.append("decision_engine")
        return self.decision

    def _apply_treasury_borrow_overlay(self, *, decision, **kwargs):
        self.events.append("treasury_decision_overlay")
        return decision

    async def _run_postdecision_analytics_state(self, **kwargs):
        self.events.append("postdecision_analytics")

    def _opp_is_exec_ready(self, opp):
        return opp is self.opp

    def _scan_engine_opportunities(self, **kwargs):
        self.events.append("engine_tail")

    async def _run_post_tick_tails(self, *, tick_failed):
        self.events.append("post_tick_tails")

    async def _run_loop_iteration_tail(self, *, loop_started_at):
        self.events.append("loop_tail")

    async def _execute_auto(self, opp, bn, decision=None):
        self.events.append("execute_auto")
        self.executed = (opp, bn, decision)


@pytest.mark.asyncio
async def test_actual_runtime_path_traces_loop_scan_decision_dispatch_and_execution(monkeypatch):
    monkeypatch.setattr(
        runtime_loop_entry_facade,
        "JsonRpcClient",
        lambda *args, **kwargs: _Rpc(),
    )
    runtime = _Runtime()

    await runtime._run_loop_entry_iteration(loop_started_at=1.0)
    if runtime._exec_task is not None:
        await runtime._exec_task

    assert runtime.events == [
        "resolve_amount_in",
        "scan_primary",
        "annotate_can_execute",
        "gas_signals",
        "market_signals",
        "behave_regime",
        "market_regime",
        "treasury_guidance",
        "predecision_state",
        "decision_engine",
        "treasury_decision_overlay",
        "postdecision_analytics",
        "execute_auto",
        "engine_tail",
        "post_tick_tails",
        "loop_tail",
    ]

    opp, block, decision = runtime.executed
    assert opp is runtime.opp
    assert block == 777
    assert decision is runtime.decision
    assert decision.metadata["identity"]["decision_id"]
    assert decision.metadata["identity"]["correlation_id"]
    assert decision.metadata["identity"]["decision_id"] == getattr(
        decision, "decision_id"
    )
    assert decision.metadata["identity"]["correlation_id"] == getattr(
        decision, "correlation_id"
    )
