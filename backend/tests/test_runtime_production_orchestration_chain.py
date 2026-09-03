from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle


class _RpcManager:
    def best_send(self):
        return "send://production"

    def best_private(self):
        return "private://production"

    def best_read(self):
        return "read://production"


class _ExecutionServiceSpy:
    def __init__(self, events):
        self.events = events

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        del runtime, decision, force_dry_run
        self.events.append("admission")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def handle_superstructure_pre_execute(self, runtime, opp, decision, *, force_dry_run):
        del runtime, decision, force_dry_run
        self.events.append("superstructure")
        return SimpleNamespace(
            opportunity=opp,
            super_enabled=False,
            old_gas_mode="standard",
            old_send_mode="public",
            blocked_result=None,
        )

    def apply_operator_overrides(self, runtime, opp, *, force_dry_run):
        del runtime, force_dry_run
        self.events.append("operator_overrides")
        return opp, False, "standard", "public"

    def handle_governance_pre_execute(
        self, runtime, opp, bn, decision, *, force_dry_run
    ):
        del runtime, bn, decision, force_dry_run
        self.events.append("governance")
        return SimpleNamespace(opportunity=opp, blocked_result=None)


@pytest.mark.asyncio
async def test_runtime_bundle_executes_real_entry_and_dispatch_orchestration_in_order():
    events = []
    runtime = object.__new__(RuntimeBundle)
    runtime._cc = None
    runtime._execution_service = _ExecutionServiceSpy(events)
    runtime.rpc_manager = _RpcManager()
    runtime.cfg = SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="standard",
            send_mode="public",
        )
    )
    runtime.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")

    async def stop_at_execution_boundary(**kwargs):
        del kwargs
        events.append("execution_boundary")

    runtime._run_prepared_auto_execution = stop_at_execution_boundary

    opportunity = SimpleNamespace(id="opp-production", route_id="route-production")
    decision = SimpleNamespace(action="EXECUTE", gas_mode="fast")

    await RuntimeBundle._execute_auto(runtime, opportunity, 321, decision)

    assert events == [
        "admission",
        "superstructure",
        "operator_overrides",
        "governance",
        "execution_boundary",
    ]
    assert runtime.cfg.execution.gas_mode == "fast"


@pytest.mark.asyncio
async def test_runtime_bundle_governance_block_is_recorded_and_execution_boundary_is_not_reached():
    events = []
    runtime = object.__new__(RuntimeBundle)
    runtime._cc = None
    runtime.rpc_manager = _RpcManager()
    runtime.cfg = SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="standard",
            send_mode="public",
        )
    )
    runtime.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")

    service = _ExecutionServiceSpy(events)

    def governance_block(runtime, opp, bn, decision, *, force_dry_run):
        del runtime, opp, bn, decision, force_dry_run
        events.append("governance")
        return SimpleNamespace(
            opportunity=SimpleNamespace(id="blocked"),
            blocked_result=SimpleNamespace(reason="governance_hold"),
        )

    service.handle_governance_pre_execute = governance_block
    runtime._execution_service = service

    async def record_exec(result, opp, *, latency_ms, mode):
        del opp, latency_ms, mode
        events.append(f"record:{result.reason}")

    async def must_not_execute(**kwargs):
        del kwargs
        raise AssertionError("execution boundary reached after governance block")

    runtime._record_exec = record_exec
    runtime._run_prepared_auto_execution = must_not_execute

    await RuntimeBundle._execute_auto(
        runtime,
        SimpleNamespace(id="opp-blocked"),
        654,
        SimpleNamespace(action="EXECUTE", gas_mode="standard"),
    )

    assert events == [
        "admission",
        "superstructure",
        "operator_overrides",
        "governance",
        "record:governance_hold",
    ]
