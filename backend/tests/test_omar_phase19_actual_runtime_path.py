from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService


class _AllowingExecutionService(ExecutionService):
    """Use the real ExecutionService orchestration with deterministic gates."""

    def auto_trade_hold_gate(self, runtime):
        del runtime
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_family_gate(self, runtime, opp):
        del runtime, opp
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_execution_realism_gate(self, opp, decision, runtime=None):
        del decision, runtime
        return opp, ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        del runtime, opp, decision
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_treasury_gate(self, runtime):
        del runtime
        return ExecutionGateResult(True, "ok", {"blocked": False})


class _RecordingExecutionService(_AllowingExecutionService):
    """Record the real ExecutionService method sequence."""

    def __init__(self):
        self.events: list[str] = []

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("admission")
        return super().handle_auto_trade_admission(
            runtime, opp, decision, force_dry_run=force_dry_run
        )

    def handle_superstructure_pre_execute(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("superstructure")
        return super().handle_superstructure_pre_execute(
            runtime, opp, decision, force_dry_run=force_dry_run
        )

    def handle_governance_pre_execute(self, runtime, opp, bn, decision, *, force_dry_run):
        self.events.append("governance")
        return super().handle_governance_pre_execute(
            runtime, opp, bn, decision, force_dry_run=force_dry_run
        )

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core_coro):
        self.events.append("fioa")
        return await super().handle_fioa_execution_wrapper(runtime, opp, decision, core_coro)

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        self.events.append("bookkeeping")
        return await super().handle_post_execute_bookkeeping(
            runtime, opp, result, bn=bn, latency_ms=latency_ms, mode=mode
        )


class _Rpc:
    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _runtime_stub():
    runtime = RuntimeBundle.__new__(RuntimeBundle)
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="standard",
            send_mode="public",
        ),
    )
    runtime.metrics = SimpleNamespace(
        gas_mode="standard",
        send_mode="public",
        last_submitted_block=0,
        exec_e2e_p50_ms=0.0,
        exec_e2e_p90_ms=0.0,
        exec_e2e_p99_ms=0.0,
    )
    runtime.rpc_manager = SimpleNamespace(
        best_send=lambda: "http://send",
        best_private=lambda: None,
        best_read=lambda: "http://read",
    )
    runtime._execution_service = _RecordingExecutionService()
    runtime._cc = SimpleNamespace(
        controls=SimpleNamespace(aggression_mode="balanced", risk_multiplier=1.0)
    )
    runtime._consensus = None
    runtime._gov = None
    runtime._super = None
    runtime._fioa = None
    runtime._lat = None
    runtime._last_submitted_block = 0
    runtime.cache = None
    runtime._mev_guard = None
    runtime._recorded = []
    runtime._wealth_goal_service = None
    runtime._ai_recommendation = None
    return runtime


def _opportunity_and_decision():
    opp = SimpleNamespace(
        id="opp-runtime-19",
        route_id="route-runtime-19",
        meta={"brain": {}},
    )
    decision = SimpleNamespace(
        action="trade",
        opp_id=opp.id,
        route_id=opp.route_id,
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        metadata={},
    )
    return opp, decision


async def _record_exec(runtime, result, opp, *, latency_ms, mode):
    runtime._recorded.append((result, opp, latency_ms, mode))


async def _fake_execute(*args, **kwargs):
    del args
    _fake_execute.decision = kwargs.get("decision")
    return SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        plan={"latency_stages_ms": {"total": 7.0}},
    )


_fake_execute.decision = None


def _assert_lineage(result, decision):
    lineage = result.plan["canonical_lineage"]
    assert result.plan["canonical_decision_id"] == decision.metadata["canonical_decision_id"]
    assert result.plan["correlation_id"] == decision.metadata["correlation_id"]
    assert lineage["decision_id"] == decision.metadata["canonical_decision_id"]
    assert lineage["correlation_id"] == decision.metadata["correlation_id"]


@pytest.mark.asyncio
async def test_production_runtime_method_chain_preserves_lineage_to_execution_record(monkeypatch):
    """Walk the production execution shell through the real ExecutionService."""
    runtime = _runtime_stub()
    monkeypatch.setattr(
        runtime_execute_wrapper_facade,
        "_compat_execution_wrapper_symbols",
        lambda: (_Rpc, _fake_execute),
    )
    runtime._record_exec = lambda result, opp, *, latency_ms, mode: _record_exec(
        runtime, result, opp, latency_ms=latency_ms, mode=mode
    )

    opp, decision = _opportunity_and_decision()
    chosen, decision = runtime._apply_omar_to_candidate(opp, decision, current_block=901)
    assert chosen is opp

    await runtime._execute_auto(opp, 901, decision=decision)

    assert runtime._execution_service.events == [
        "admission",
        "superstructure",
        "governance",
        "fioa",
        "bookkeeping",
    ]
    assert runtime._recorded
    _assert_lineage(runtime._recorded[-1][0], decision)
    assert _fake_execute.decision is decision
    assert runtime._last_submitted_block == 901


def test_omar_package_does_not_require_numpy_for_lineage_only_imports():
    """Canonical lineage modules must remain importable on constrained runtimes."""
    from victor_ai_bot.omar import lifecycle_bridge, production_lineage_bridge

    assert lifecycle_bridge is not None
    assert production_lineage_bridge is not None
