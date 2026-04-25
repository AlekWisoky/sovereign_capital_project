from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import (
    RuntimeExecuteDispatchFacade,
)

EXTRACTED_METHODS = {
    "_prepare_auto_execution_dispatch",
}


class _ExecutionService:
    def __init__(self):
        self.admission_calls = []
        self.super_calls = []
        self.gov_calls = []
        self.override_calls = []

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.admission_calls.append(
            {"opp": opp, "decision": decision, "force_dry_run": force_dry_run}
        )
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def handle_superstructure_pre_execute(self, runtime, opp, decision, *, force_dry_run):
        self.super_calls.append({"opp": opp, "decision": decision, "force_dry_run": force_dry_run})
        return SimpleNamespace(
            opportunity=opp,
            blocked_result=None,
            super_enabled=False,
            old_gas_mode="standard",
            old_send_mode="public",
        )

    def handle_governance_pre_execute(self, runtime, opp, bn, decision, *, force_dry_run):
        self.gov_calls.append(
            {"opp": opp, "bn": bn, "decision": decision, "force_dry_run": force_dry_run}
        )
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def apply_operator_overrides(self, runtime, opp, *, force_dry_run=False):
        self.override_calls.append({"opp": opp, "force_dry_run": force_dry_run})
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is not None:
            force_send_mode = str(getattr(controls, "force_send_mode", "") or "")
            force_gas_mode = str(getattr(controls, "force_gas_mode", "") or "")
            if force_send_mode in {"public", "private", "protected_rpc"}:
                runtime.cfg.execution.send_mode = force_send_mode
                runtime.metrics.send_mode = force_send_mode
            if force_gas_mode in {"standard", "fast", "instant"}:
                runtime.cfg.execution.gas_mode = force_gas_mode
                runtime.metrics.gas_mode = force_gas_mode
        return opp, force_dry_run, runtime.cfg.execution.gas_mode, runtime.cfg.execution.send_mode


class _RpcManager:
    def __init__(self, *, read="read-url", send="send-url", private="private-url"):
        self._read = read
        self._send = send
        self._private = private

    def best_read(self):
        return self._read

    def best_send(self):
        return self._send

    def best_private(self):
        return self._private


class _Runtime(RuntimeExecuteDispatchFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(dry_run=False, gas_mode="standard", send_mode="public")
        )
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
        self.rpc_manager = _RpcManager()
        self._execution_service = _ExecutionService()
        self._cc = None
        self.records = []

    async def _record_exec(self, result, opp, *, latency_ms, mode):
        self.records.append({"result": result, "opp": opp, "latency_ms": latency_ms, "mode": mode})


def test_runtime_bundle_inherits_execute_dispatch_facade():
    assert issubclass(RuntimeBundle, RuntimeExecuteDispatchFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_prepare_auto_execution_dispatch_preserves_preflight_order():
    runtime = _Runtime()
    opp = SimpleNamespace(route_id="r1")
    decision = SimpleNamespace(gas_mode="fast", size_mult=1.2, borrow_mult=1.4)

    prep = await runtime._prepare_auto_execution_dispatch(opp=opp, bn=123, decision=decision)

    assert prep is not None
    assert prep.opportunity is opp
    assert prep.force_dry is False
    assert prep.read_url == "read-url"
    assert prep.send_url == "send-url"
    assert runtime._execution_service.admission_calls[0]["force_dry_run"] is False
    assert runtime._execution_service.super_calls[0]["force_dry_run"] is False
    assert runtime._execution_service.gov_calls[0]["bn"] == 123
    assert runtime.cfg.execution.gas_mode == "fast"
    assert runtime.metrics.gas_mode == "fast"


@pytest.mark.asyncio
async def test_prepare_auto_execution_dispatch_respects_cc_pause():
    runtime = _Runtime()
    runtime._cc = SimpleNamespace(
        controls=SimpleNamespace(
            paused=True, sandbox_only=False, defensive_mode=False, reduce_exposure_half=False
        )
    )
    opp = SimpleNamespace(route_id="r2")

    prep = await runtime._prepare_auto_execution_dispatch(opp=opp, bn=9, decision=None)

    assert prep is None
    assert len(runtime.records) == 1
    assert runtime.records[0]["mode"] == "auto"
    assert runtime._execution_service.admission_calls == []


@pytest.mark.asyncio
async def test_prepare_auto_execution_dispatch_clamps_decision_and_uses_private_rpc():
    runtime = _Runtime()
    runtime.cfg.execution.send_mode = "private"
    runtime._cc = SimpleNamespace(
        controls=SimpleNamespace(
            paused=False, sandbox_only=True, defensive_mode=True, reduce_exposure_half=False
        )
    )
    opp = SimpleNamespace(route_id="r3")
    decision = SimpleNamespace(gas_mode="instant", size_mult=2.0, borrow_mult=2.0)

    prep = await runtime._prepare_auto_execution_dispatch(opp=opp, bn=7, decision=decision)

    assert prep is not None
    assert prep.force_dry is True
    assert prep.send_url == "private-url"
    assert decision.size_mult == 0.5
    assert decision.borrow_mult == 1.0
    assert runtime._execution_service.admission_calls[0]["force_dry_run"] is True


@pytest.mark.asyncio
async def test_prepare_auto_execution_dispatch_returns_none_without_urls():
    runtime = _Runtime()
    runtime.rpc_manager = _RpcManager(read=None, send=None)

    prep = await runtime._prepare_auto_execution_dispatch(
        opp=SimpleNamespace(route_id="r4"), bn=1, decision=None
    )

    assert prep is None


@pytest.mark.asyncio
async def test_prepare_auto_execution_dispatch_applies_operator_force_modes_before_rpc_selection():
    runtime = _Runtime()
    runtime._cc = SimpleNamespace(
        controls=SimpleNamespace(
            paused=False,
            sandbox_only=False,
            defensive_mode=False,
            reduce_exposure_half=False,
            force_send_mode="private",
            force_gas_mode="instant",
        )
    )

    prep = await runtime._prepare_auto_execution_dispatch(
        opp=SimpleNamespace(route_id="r5"),
        bn=11,
        decision=SimpleNamespace(gas_mode="standard"),
    )

    assert prep is not None
    assert prep.send_url == "private-url"
    assert runtime.cfg.execution.send_mode == "private"
    assert runtime.metrics.send_mode == "private"
    assert runtime.cfg.execution.gas_mode == "instant"
    assert runtime.metrics.gas_mode == "instant"
    assert runtime._execution_service.override_calls[0]["force_dry_run"] is False
