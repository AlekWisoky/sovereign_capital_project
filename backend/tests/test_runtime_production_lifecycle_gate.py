from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.decision_identity import ensure_decision_identity
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_loop_entry_facade
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import (
    AutoExecutionDispatchContext,
    RuntimeExecuteDispatchFacade,
)
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    RuntimeExecuteWrapperFacade,
)


class _Rpc:
    def __init__(self, url: str, **_kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def block_number(self):
        return 777


class _ExecutionService:
    def __init__(self, events: list[str]):
        self.events = events

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("execution_admission")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def handle_superstructure_pre_execute(
        self, runtime, opp, decision, *, force_dry_run
    ):
        self.events.append("superstructure_pre_execute")
        return SimpleNamespace(
            opportunity=opp,
            super_enabled=False,
            old_gas_mode=runtime.cfg.execution.gas_mode,
            old_send_mode=runtime.cfg.execution.send_mode,
            blocked_result=None,
        )

    def apply_operator_overrides(self, runtime, opp, *, force_dry_run):
        self.events.append("operator_overrides")
        return (
            opp,
            force_dry_run,
            runtime.cfg.execution.gas_mode,
            runtime.cfg.execution.send_mode,
        )

    def handle_governance_pre_execute(
        self, runtime, opp, bn, decision, *, force_dry_run
    ):
        self.events.append("governance_pre_execute")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        self.events.append("fioa_wrapper")
        return await core()

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        self.events.append("post_execute_bookkeeping")
        runtime.execution_result = result
        runtime.execution_latency_ms = latency_ms
        runtime.execution_mode = mode

    def restore_operator_overrides(self, runtime, *, old_gas_mode, old_send_mode):
        self.events.append("restore_operator_overrides")
        runtime.cfg.execution.gas_mode = old_gas_mode
        runtime.cfg.execution.send_mode = old_send_mode


class _Runtime(RuntimeBundle):
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
        self._gas_spent_today_wei = 0
        self.metrics = SimpleNamespace(
            last_block=0,
            last_error="",
            failed_ticks=0,
            gas_mode="standard",
            send_mode="public",
            last_submitted_block=0,
        )
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(chain_id=1, name="ethereum"),
            execution=SimpleNamespace(
                max_pending_txs=1,
                brain_mode="auto",
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
            ),
        )
        self.rpc_manager = SimpleNamespace(
            best_read=lambda: "http://read",
            best_send=lambda: "http://send",
            best_private=lambda: None,
        )
        self._cb = SimpleNamespace(
            allow_auto_trading=lambda: True,
            remaining_cooldown_s=lambda: 0,
        )
        self._anomaly = SimpleNamespace(observe_rpc_error=lambda **kwargs: False)
        self.cache = SimpleNamespace(reset_if_new_block=lambda *args: None)
        self._runtime_control_service = None
        self._execution_service = _ExecutionService(self.events)

        self.opp = SimpleNamespace(
            id="opp-production",
            route_id="route-production",
            can_execute=True,
            meta={
                "safety": {"exec_ready": True, "profit_after_costs_wei": "100"},
                "profit_after_costs": "100",
            },
        )
        self.decision = SimpleNamespace(
            action="trade",
            opp_id="opp-production",
            route_id="route-production",
            size_mult=1.0,
            borrow_mult=1.0,
            gas_mode="standard",
            metadata={},
            portfolio=["opp-production"],
        )
        ensure_decision_identity(
            self.opp,
            self.decision,
            chain_name="ethereum",
            current_block=777,
            operator_intent={
                "aggression_mode": "conservative",
                "risk_multiplier": 0.40,
                "goal": {"target_amount": "100000", "timeframe_days": 365},
                "ai_recommendation": {
                    "action": "EXECUTE",
                    "confidence": 0.90,
                    "source": "test-ai",
                },
            },
            intent_fingerprint="intent-production-1",
        )

    def _resolve_amount_in(self):
        self.events.append("resolve_amount_in")
        return 1

    async def _scan_primary_opportunities(self, rpc, *, current_block, amount_in):
        self.events.append("scan_primary")
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

    def _gas_budget_remaining_wei(self):
        return 10**30

    async def _record_exec(self, result, opp, *, latency_ms, mode):
        self.events.append("record_exec")


@pytest.mark.asyncio
async def test_actual_runtime_method_chain_reaches_canonical_execution_boundary(monkeypatch):
    monkeypatch.setattr(runtime_loop_entry_facade, "JsonRpcClient", lambda *args, **kwargs: _Rpc(*args, **kwargs))

    async def fake_execute_opportunity(*args, **kwargs):
        runtime = kwargs["_runtime"]
        runtime.events.append("real_execution_call")
        return SimpleNamespace(
            ok=True,
            dry_run=False,
            submitted=True,
            plan={
                "identity": dict(
                    runtime.decision.metadata["identity"]
                ),
            },
        )

    def fake_symbols():
        async def execute(*args, **kwargs):
            runtime = kwargs.pop("_runtime")
            return await fake_execute_opportunity(*args, _runtime=runtime, **kwargs)

        return _Rpc, execute

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_execute_wrapper_facade._compat_execution_wrapper_symbols",
        fake_symbols,
    )

    runtime = _Runtime()

    # The production wrapper does not pass runtime to the execution function;
    # inject the trace handle only at this test seam so no production contract
    # is changed.
    original_symbols = fake_symbols

    def seam_symbols():
        async def execute(*args, **kwargs):
            return await fake_execute_opportunity(*args, _runtime=runtime, **kwargs)

        return _Rpc, execute

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_execute_wrapper_facade._compat_execution_wrapper_symbols",
        seam_symbols,
    )

    await runtime._run_loop_entry_iteration(loop_started_at=1.0)
    if runtime._exec_task is not None:
        await runtime._exec_task

    assert runtime.events[:14] == [
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
        "execution_admission",
        "superstructure_pre_execute",
    ]
    assert "operator_overrides" in runtime.events
    assert "governance_pre_execute" in runtime.events
    assert "fioa_wrapper" in runtime.events
    assert "real_execution_call" in runtime.events
    assert "post_execute_bookkeeping" in runtime.events
    assert "restore_operator_overrides" in runtime.events
    assert runtime.execution_result.ok is True
    assert runtime.execution_result.submitted is True
    assert runtime.execution_result.plan["identity"] == runtime.decision.metadata["identity"]
    assert runtime.decision.metadata["identity"]["decision_id"]
    assert runtime.decision.metadata["identity"]["correlation_id"]
    assert runtime.opp.meta["canonical_lineage"]["intent_fingerprint"] == "intent-production-1"
