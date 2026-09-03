from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_loop_entry_facade import RuntimeLoopEntryFacade
from victor_ai_bot.runtime_services.runtime_tick_iteration_facade import RuntimeTickIterationFacade


class _FakeRpcClient:
    def __init__(self, url: str, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def block_number(self):
        return 123


class _RpcManager:
    def best_read(self):
        return "read-url"


class _Metrics:
    last_block = 0


@pytest.mark.asyncio
async def test_actual_runtime_method_chain_reaches_auto_execution_dispatch(monkeypatch):
    """Walk the real RuntimeBundle orchestration into the auto-execution boundary.

    Production orchestration is intentionally left intact:
    RuntimeLoopEntryFacade -> RuntimeTickPrepareFacade ->
    RuntimeTickIterationFacade -> RuntimeTickScanFacade ->
    RuntimeDecisionFinalizeFacade -> RuntimeAfterTickFacade ->
    RuntimeDecisionFacade._maybe_dispatch_auto_trade.

    Only external market/RPC leaves and the final transaction execution coroutine
    are stubbed, so this test can never broadcast a real transaction.
    """

    events: list[str] = []
    execute_calls: list[dict[str, object]] = []

    runtime = object.__new__(RuntimeBundle)
    runtime.rpc_manager = _RpcManager()
    runtime.metrics = _Metrics()
    runtime._anomaly = SimpleNamespace(observe_rpc_error=lambda **kwargs: None)
    runtime.cache = SimpleNamespace(reset_if_new_block=lambda *args, **kwargs: None)
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(chain_id=1),
        execution=SimpleNamespace(max_pending_txs=1, brain_mode="auto"),
    )
    runtime._runtime_control_service = None
    runtime._auto_trading = True
    runtime._cb = SimpleNamespace(allow_auto_trading=lambda: True)
    runtime._pending = {}
    opp = SimpleNamespace(id="opp-1")
    runtime._opps = [opp]
    runtime._exec_task = None
    runtime._errors = []
    runtime._spread_opps = []
    runtime._spread_last = {}
    runtime._engine_last = {}
    runtime._state_lock = None

    async def fake_scan(**kwargs):
        events.append("scan")
        return [opp]

    async def fake_annotate(*args, **kwargs):
        events.append("annotate")

    async def fake_gas(*args, **kwargs):
        events.append("gas")
        return {"basefee_gwei": 1.0, "priority_gwei": 1.0}

    def fake_market(*args, **kwargs):
        events.append("market")
        return {
            "mev_risk": 0.0,
            "pending_rate": 0.0,
            "avg_margin_ratio": 1.0,
            "volatility_proxy": 0.0,
        }

    def fake_behave(**kwargs):
        events.append("behave")
        return {"regime_label": "balanced"}

    def fake_regime(**kwargs):
        events.append("regime")
        return {"regime_label": "balanced"}

    def fake_treasury(**kwargs):
        events.append("treasury")
        return {"treasury_state": {}, "behave_state": {"regime_label": "balanced"}}

    def fake_predecision(**kwargs):
        events.append("predecision")
        return {"mev_snap": {}}

    async def fake_decision(**kwargs):
        events.append("decision_finalize")
        return SimpleNamespace(action="trade", opp_id="opp-1", portfolio=["opp-1"])

    def fake_ready(candidate):
        return candidate is opp

    async def fake_execute(candidate, bn, decision=None):
        events.append("execute_entry")
        execute_calls.append({"opp": candidate, "bn": bn, "decision": decision})

    def fake_engine(*args, **kwargs):
        events.append("engine")

    async def fake_post_tick(*args, **kwargs):
        events.append("post_tick")

    async def fake_loop_tail(*args, **kwargs):
        events.append("loop_tail")

    # Keep production orchestration and auto-dispatch intact. Patch only leaf I/O
    # and the final transaction coroutine.
    runtime._resolve_amount_in = lambda: 1_000
    runtime._scan_primary_opportunities = fake_scan
    runtime._safe_annotate_can_execute = fake_annotate
    runtime._gas_signal_snapshot = fake_gas
    runtime._market_signal_snapshot = fake_market
    runtime._behave_regime_state = fake_behave
    runtime._resolve_market_regime = fake_regime
    runtime._apply_treasury_guidance = fake_treasury
    runtime._run_predecision_additive_state = fake_predecision
    runtime._run_decision_finalize = fake_decision
    runtime._opp_is_exec_ready = fake_ready
    runtime._execute_auto = fake_execute
    runtime._scan_engine_opportunities = fake_engine
    runtime._run_post_tick_tails = fake_post_tick
    runtime._run_loop_iteration_tail = fake_loop_tail

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient",
        _FakeRpcClient,
    )

    await RuntimeLoopEntryFacade._run_loop_entry_iteration(runtime, loop_started_at=1.0)
    await asyncio.sleep(0)

    assert events == [
        "scan",
        "annotate",
        "gas",
        "market",
        "behave",
        "regime",
        "treasury",
        "predecision",
        "decision_finalize",
        "execute_entry",
        "engine",
        "post_tick",
        "loop_tail",
    ]
    assert runtime.metrics.last_block == 123
    assert len(execute_calls) == 1
    assert execute_calls[0]["opp"] is opp
    assert execute_calls[0]["bn"] == 123
    assert execute_calls[0]["decision"].opp_id == "opp-1"


def test_runtime_bundle_uses_production_loop_and_tick_facades():
    assert issubclass(RuntimeBundle, RuntimeLoopEntryFacade)
    assert issubclass(RuntimeBundle, RuntimeTickIterationFacade)
    assert "_run_loop_entry_iteration" not in RuntimeBundle.__dict__
    assert "_run_contained_tick_iteration" not in RuntimeBundle.__dict__
