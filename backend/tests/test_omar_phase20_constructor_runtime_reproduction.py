from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_constructor_facade
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService


class _AllowingExecutionService(ExecutionService):
    """Keep the real admission/orchestration path deterministic for the test."""

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


class _RpcManager:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def best_read(self):
        return "http://read"

    def best_send(self):
        return "http://send"

    def best_private(self):
        return None


class _Cache:
    pass


class _Metrics:
    def __init__(self, **kwargs):
        self.gas_mode = kwargs.get("gas_mode", "standard")
        self.send_mode = kwargs.get("send_mode", "public")
        self.last_submitted_block = 0
        self.exec_e2e_p50_ms = 0.0
        self.exec_e2e_p90_ms = 0.0
        self.exec_e2e_p99_ms = 0.0
        self.last_error = ""
        self.failed_ticks = 0


class _Latency:
    def __init__(self, **kwargs):
        del kwargs
        self.samples = []

    def add(self, name, value):
        self.samples.append((name, value))

    def get(self, name):
        values = [value for key, value in self.samples if key == name]
        value = values[-1] if values else 0.0
        return {"p50": value, "p90": value, "p99": value}


class _DB:
    def __init__(self, *args, **kwargs):
        del args, kwargs


class _Audit:
    def __init__(self, *args, **kwargs):
        del args, kwargs


class _DecisionEngine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _Discovery:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _CircuitBreaker:
    @classmethod
    def from_env(cls):
        return cls()

    def allow_auto_trading(self):
        return True

    def remaining_cooldown_s(self):
        return 0.0


class _Anomaly:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            chain_id=1,
            rpc_read="http://read",
            rpc_send="http://send",
            rpc_private=[],
        ),
        execution=SimpleNamespace(
            dry_run=False,
            auto_trading=True,
            gas_mode="standard",
            send_mode="public",
            brain_mode="off",
            max_pending_txs=1,
            daily_gas_budget_wei="0",
        ),
        safety=SimpleNamespace(slippage_bps=50, require_simulation=False),
        superstructure=SimpleNamespace(omar=None),
    )


def _patch_constructor(monkeypatch):
    """Patch external resources, not the RuntimeBundle constructor itself."""
    for name, value in {
        "RpcManager": _RpcManager,
        "PerBlockCache": _Cache,
        "Metrics": _Metrics,
        "LatencyProfiler": _Latency,
        "PersistenceDB": _DB,
        "SecurityAuditStore": _Audit,
        "DecisionEngine": _DecisionEngine,
        "DiscoveryManager": _Discovery,
        "CircuitBreaker": _CircuitBreaker,
        "AnomalyBreaker": _Anomaly,
    }.items():
        monkeypatch.setattr(runtime_constructor_facade, name, value)

    monkeypatch.setattr(
        runtime_legacy,
        "initialize_execution_capture_stack",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runtime_legacy,
        "initialize_runtime_institutional_stack",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runtime_legacy,
        "initialize_optional_overlay_runtimes",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runtime_legacy,
        "initialize_execution_support_stack",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        runtime_legacy,
        "initialize_optional_family_runtimes",
        lambda *args, **kwargs: None,
    )


def _opportunity():
    return SimpleNamespace(
        id="opp-runtime-20",
        route_id="route-runtime-20",
        can_execute=True,
        expected_profit_raw="100",
        meta={
            "brain": {},
            "safety": {"exec_ready": True, "profit_after_costs_wei": "100"},
            "profit_after_costs": "100",
        },
    )


def _decision(opp):
    return SimpleNamespace(
        action="trade",
        opp_id=opp.id,
        route_id=opp.route_id,
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        metadata={},
        p_success=0.95,
        ev_wei=100,
    )


async def _record_exec(runtime, result, opp, *, latency_ms, mode):
    runtime._recorded.append((result, opp, latency_ms, mode))


@pytest.mark.asyncio
async def test_constructor_backed_runtime_reproduces_production_execution_chain(monkeypatch):
    """The real constructor installs a runtime that reaches the real execution chain."""
    _patch_constructor(monkeypatch)
    monkeypatch.setattr(
        runtime_execute_wrapper_facade,
        "_compat_execution_wrapper_symbols",
        lambda: (_Rpc, _fake_execute),
    )

    runtime = RuntimeBundle(_cfg())
    assert runtime.cfg.execution.auto_trading is True
    assert callable(runtime._execute_auto)
    assert callable(runtime._run_loop_entry_iteration)

    service = _RecordingExecutionService()
    runtime._execution_service = service
    runtime._cc = None
    runtime._gov = None
    runtime._super = None
    runtime._fioa = None
    runtime._mev_guard = None
    runtime._pending = {}
    runtime._recorded = []
    runtime._record_exec = lambda result, opp, *, latency_ms, mode: _record_exec(
        runtime, result, opp, latency_ms=latency_ms, mode=mode
    )

    opp = _opportunity()
    decision = _decision(opp)
    chosen, decision = runtime._apply_omar_to_candidate(opp, decision, current_block=902)

    assert chosen is opp
    assert "canonical_decision_id" in decision.metadata
    assert "correlation_id" in decision.metadata

    await runtime._execute_auto(opp, 902, decision=decision)

    assert service.events == [
        "admission",
        "superstructure",
        "governance",
        "fioa",
        "bookkeeping",
    ]
    assert runtime._recorded
    result = runtime._recorded[-1][0]
    assert result.plan["canonical_decision_id"] == decision.metadata["canonical_decision_id"]
    assert result.plan["correlation_id"] == decision.metadata["correlation_id"]
    assert result.plan["canonical_lineage"]["decision_id"] == decision.metadata[
        "canonical_decision_id"
    ]
    assert result.plan["canonical_lineage"]["correlation_id"] == decision.metadata[
        "correlation_id"
    ]
    assert _fake_execute.decision is decision
    assert runtime._last_submitted_block == 902


def _fake_execute(*args, **kwargs):
    del args
    _fake_execute.decision = kwargs.get("decision")
    return SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        plan={"latency_stages_ms": {"total": 7.0}},
    )


_fake_execute.decision = None
