from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.models import Opportunity, Route, RouteLeg
from victor_ai_bot.runtime_core.bootstrap import build_runtime
import victor_ai_bot.runtime_services.runtime_execute_wrapper_facade as wrapper_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle


class _FakeRpc:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeExecutionService:
    def __init__(self, calls):
        self.calls = calls

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.calls.append("admission")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def handle_superstructure_pre_execute(
        self, runtime, opp, decision, *, force_dry_run
    ):
        self.calls.append("superstructure")
        return SimpleNamespace(
            opportunity=opp,
            super_enabled=False,
            old_gas_mode=runtime.cfg.execution.gas_mode,
            old_send_mode=runtime.cfg.execution.send_mode,
            blocked_result=None,
        )

    def apply_operator_overrides(self, runtime, opp, *, force_dry_run):
        self.calls.append("operator_overrides")
        return (
            opp,
            force_dry_run,
            runtime.cfg.execution.gas_mode,
            runtime.cfg.execution.send_mode,
        )

    def handle_governance_pre_execute(
        self, runtime, opp, bn, decision, *, force_dry_run
    ):
        self.calls.append("governance")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        self.calls.append("fioa")
        return await core()

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, res, *, bn, latency_ms, mode
    ):
        self.calls.append("bookkeeping")
        runtime._captured_result = res

    def restore_operator_overrides(self, runtime, *, old_gas_mode, old_send_mode):
        self.calls.append("restore")
        runtime.cfg.execution.gas_mode = old_gas_mode
        runtime.cfg.execution.send_mode = old_send_mode


def _opportunity() -> Opportunity:
    return Opportunity(
        id="production-path-opp",
        chain="ethereum",
        strategy="test",
        expected_profit_raw="1000000000000000",
        expected_profit_usd="10",
        route=Route(
            legs=[
                RouteLeg(
                    dex="univ3",
                    venue="test",
                    token_in="0x0000000000000000000000000000000000000001",
                    token_out="0x0000000000000000000000000000000000000002",
                    amount_in="1000",
                    min_out="1001",
                )
            ]
        ),
        min_outs=["1001"],
        can_execute=True,
        meta={"safety": {"exec_ready": True}},
    )


@pytest.mark.asyncio
async def test_real_runtimebundle_auto_entry_traverses_canonical_execution_path(
    monkeypatch,
):
    """Exercise the real RuntimeBundle production auto-entry method chain.

    The test constructs the actual RuntimeBundle through build_runtime, invokes
    the real auto-dispatch selector, and only replaces external execution/RPC
    and execution-service side effects. The production method chain must be:

        _maybe_dispatch_auto_trade
        -> RuntimeBundle._execute_auto
        -> _execute_auto_entry
        -> _prepare_auto_execution_dispatch
        -> _run_prepared_auto_execution
        -> external execution boundary
        -> post-execute bookkeeping

    """
    from victor_ai_bot.config import load_config

    cfg = load_config("config/ethereum.yaml")
    cfg.execution.brain_mode = "auto"
    cfg.execution.dry_run = True
    runtime = build_runtime([cfg])
    assert isinstance(runtime, RuntimeBundle)

    calls: list[str] = []
    runtime._execution_service = _FakeExecutionService(calls)
    runtime.rpc_manager = SimpleNamespace(
        best_read=lambda: "http://read.test",
        best_send=lambda: "http://send.test",
        best_private=lambda: "",
    )
    runtime._cb = SimpleNamespace(
        allow_auto_trading=lambda: True,
        remaining_cooldown_s=lambda: 0.0,
    )
    runtime._auto_trading = True
    runtime._opps = [_opportunity()]
    runtime._exec_task = None
    runtime._captured_result = None
    runtime._pending = []
    monkeypatch.setattr(runtime, "_opp_is_exec_ready", lambda _opp: True)

    decision = SimpleNamespace(
        action="trade",
        opp_id="production-path-opp",
        portfolio=["production-path-opp"],
        decision_id="decision-production-001",
        correlation_id="corr-production-001",
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
    )

    async def fake_execute(*args, **kwargs):
        calls.append("execution_boundary")
        return ExecResult(
            ok=True,
            dry_run=True,
            reason="production_path_test",
            attempted=True,
            submitted=False,
        )

    monkeypatch.setattr(
        wrapper_mod,
        "_compat_execution_wrapper_symbols",
        lambda: (_FakeRpc, fake_execute),
    )

    dispatched = runtime._maybe_dispatch_auto_trade(
        current_block=123,
        decision=decision,
    )
    assert dispatched is True

    await runtime._exec_task

    assert calls == [
        "admission",
        "superstructure",
        "operator_overrides",
        "governance",
        "fioa",
        "execution_boundary",
        "bookkeeping",
        "restore",
    ]
    assert runtime._captured_result is not None
    assert runtime._captured_result.ok is True


@pytest.mark.asyncio
async def test_legacy_unbound_execute_auto_falls_back_without_entry_method():
    """Keep the historical unbound RuntimeBundle._execute_auto seam intact."""
    calls: list[str] = []

    class LegacyStub:
        async def _prepare_auto_execution_dispatch(self, **kwargs):
            calls.append("prepare")
            return SimpleNamespace(opportunity=kwargs["opp"])

        async def _run_prepared_auto_execution(self, **kwargs):
            calls.append("wrapper")

    stub = LegacyStub()
    opp = _opportunity()

    await RuntimeBundle._execute_auto(stub, opp, 123, None)

    assert calls == ["prepare", "wrapper"]
