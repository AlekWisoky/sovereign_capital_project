from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_core import RuntimeBundle
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.runtime_loop_entry_facade import RuntimeLoopEntryFacade
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _Rpc:
    def __init__(self, url: str, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _RpcManager:
    def best_read(self):
        return "read-rpc"

    def best_send(self):
        return "send-rpc"

    def best_private(self):
        return "private-rpc"


def test_phase17_production_hooks_and_runtime_surface_are_installed():
    # Importing the production OMAR package installs the canonical settlement,
    # lineage, lifecycle, and learning-quality bridges. This test makes that
    # implicit import side effect an explicit production verification gate.
    import victor_ai_bot.omar  # noqa: F401

    assert callable(getattr(RuntimeBundle, "_loop"))
    assert callable(getattr(RuntimeBundle, "_execute_auto"))
    assert callable(getattr(RuntimeBundle, "_run_loop_entry_iteration"))
    assert callable(getattr(RuntimeBundle, "_run_contained_tick_iteration"))
    assert callable(getattr(RuntimeBundle, "_run_tick_scan_pipeline"))
    assert callable(getattr(RuntimeBundle, "_run_decision_finalize"))
    assert callable(getattr(RuntimeBundle, "_maybe_dispatch_auto_trade"))
    assert callable(getattr(RuntimeBundle, "_apply_omar_to_candidate"))

    decision_hook = getattr(RuntimeBundle, "_apply_omar_to_candidate")
    execution_hook = getattr(ExecutionService, "handle_post_execute_bookkeeping")
    settlement_hook = getattr(RuntimeReceiptFacade, "canonical_settled_outcome")
    learning_hook = getattr(OmarRuntime, "observe_decision")

    assert getattr(decision_hook, "_omar_lineage_patched", False)
    assert getattr(execution_hook, "_omar_settlement_patched", False)
    assert getattr(settlement_hook, "_phase2_canonical_interface", False)
    assert getattr(learning_hook, "_durable_identity_patched", False)


@pytest.mark.asyncio
async def test_phase17_actual_runtime_loop_entry_delegates_to_contained_tick(monkeypatch):
    runtime = object.__new__(RuntimeBundle)
    runtime.rpc_manager = _RpcManager()
    calls = []

    async def prepare_tick(*, rpc):
        calls.append(("prepare", rpc.url))
        return 123

    async def contained_tick(*, rpc, current_block, loop_started_at):
        calls.append(("contained", rpc.url, current_block, loop_started_at))

    runtime._prepare_tick_iteration = prepare_tick
    runtime._run_contained_tick_iteration = contained_tick

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient",
        _Rpc,
    )

    await RuntimeLoopEntryFacade._run_loop_entry_iteration(runtime, loop_started_at=9.5)

    assert calls == [
        ("prepare", "read-rpc"),
        ("contained", "read-rpc", 123, 9.5),
    ]


def _runtime_for_execution_gate():
    runtime = object.__new__(RuntimeBundle)
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(gas_mode="standard", send_mode="public"),
    )
    runtime.metrics = SimpleNamespace(
        gas_mode="standard",
        send_mode="public",
        last_submitted_block=0,
        exec_e2e_p50_ms=0.0,
        exec_e2e_p90_ms=0.0,
        exec_e2e_p99_ms=0.0,
    )
    runtime._cc = None
    runtime._lat = None
    runtime._last_submitted_block = 17
    runtime._pending = {}
    runtime._ledger_repo = None
    return runtime


@pytest.mark.asyncio
async def test_phase17_execution_to_canonical_settlement_to_learning_lineage(tmp_path):
    import victor_ai_bot.omar  # noqa: F401

    runtime = _runtime_for_execution_gate()

    async def record_exec(*args, **kwargs):
        return None

    runtime._record_exec = record_exec

    from victor_ai_bot.omar.real_learning import OmarRealLearner

    learner_runtime = OmarRuntime(
        cfg=SimpleNamespace(
            enabled=True,
            real_learning_enabled=True,
            live_influence_enabled=True,
            performance_promotion_enabled=False,
            real_learning_alpha=0.12,
            live_exploration_epsilon=0.0,
            real_learning_min_observations=1,
        ),
        chain_name="ethereum",
    )
    learner_runtime.data_dir = str(tmp_path)
    learner_runtime._real_learner = OmarRealLearner(
        path=str(tmp_path / "policy.json"),
        min_observations=1,
    )
    runtime._omar = learner_runtime

    opp = SimpleNamespace(
        id="opp-17",
        route_id="route-17",
        meta={
            "brain": {
                "canonical_decision_id": "decision-phase17",
                "correlation_id": "corr-phase17",
                "omar_action": "EXECUTE",
                "omar_state_key": "state-phase17",
            },
            "canonical_lineage": {
                "decision_id": "decision-phase17",
                "correlation_id": "corr-phase17",
            },
        },
    )

    learner_runtime.observe_decision(
        decision_id="decision-phase17",
        opportunity_id="opp-17",
        route_id="route-17",
        action="EXECUTE",
        state_key="state-phase17",
        context={},
        metadata={"correlation_id": "corr-phase17"},
    )

    settled = {
        "status": "settled",
        "decision_id": "decision-phase17",
        "correlation_id": "corr-phase17",
        "opportunity_id": "opp-17",
        "route_id": "route-17",
        "ok": True,
        "expected_net_usd": 8.0,
        "realized_net_usd": 11.0,
        "amount_in_wei": 1_000_000,
        "gas_cost_usd": 0.25,
        "slippage_bps": 1.5,
        "latency_ms": 42,
        "truth_verified": True,
        "tx_hash": "0x-phase17-fill",
    }
    runtime.canonical_settled_outcome = lambda **kwargs: dict(settled)

    result = SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        tx_hash="0x-phase17-fill",
        plan={},
    )

    service = object.__new__(ExecutionService)
    await service.handle_post_execute_bookkeeping(
        runtime,
        opp,
        result,
        bn=123,
        latency_ms=42,
        mode="auto",
    )

    assert learner_runtime.last_outcome["canonical_decision_id"] == "decision-phase17"
    assert learner_runtime.last_outcome["decision_id"] == "decision-phase17"
    assert learner_runtime.last_outcome["action"] == "EXECUTE"
    assert learner_runtime._real_learner.total_observations == 1

    # Promotion/influence remains fail-closed until its independent OOS gate is
    # satisfied; a single settled outcome must not authorize live influence.
    learner_runtime.cfg.performance_promotion_enabled = True
    rec = learner_runtime.recommend({})
    assert rec.action == "UNTRAINED"
    assert "learning_quality_gate" in rec.reason or "performance_promotion_gate" in rec.reason
