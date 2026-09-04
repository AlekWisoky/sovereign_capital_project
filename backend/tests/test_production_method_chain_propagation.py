from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_constructor_facade
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade
from victor_ai_bot.runtime_services import runtime_institutional_init
from victor_ai_bot.runtime_services.execution_service import (
    ExecutionGateResult,
    ExecutionService,
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


class _LedgerRepo:
    def __init__(self, *args, **kwargs):
        del args, kwargs
        self.rows = []

    def all_transactions(self, *, chain):
        del chain
        return list(self.rows)


class _AllowingExecutionService(ExecutionService):
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
    def __init__(self):
        self.events = []

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("admission")
        return super().handle_auto_trade_admission(
            runtime, opp, decision, force_dry_run=force_dry_run
        )

    def handle_superstructure_pre_execute(
        self, runtime, opp, decision, *, force_dry_run
    ):
        self.events.append("superstructure")
        return super().handle_superstructure_pre_execute(
            runtime, opp, decision, force_dry_run=force_dry_run
        )

    def handle_governance_pre_execute(
        self, runtime, opp, bn, decision, *, force_dry_run
    ):
        self.events.append("governance")
        return super().handle_governance_pre_execute(
            runtime, opp, bn, decision, force_dry_run=force_dry_run
        )

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core_coro):
        self.events.append("fioa")
        return await super().handle_fioa_execution_wrapper(
            runtime, opp, decision, core_coro
        )

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        self.events.append("bookkeeping")
        return await super().handle_post_execute_bookkeeping(
            runtime, opp, result, bn=bn, latency_ms=latency_ms, mode=mode
        )


class _Omar:
    enabled = True

    def __init__(self):
        self.calls = []

    def observe_outcome(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, "learning_id": "learn-1"}


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
            daily_gas_budget_wei="1000000",
        ),
        safety=SimpleNamespace(slippage_bps=50, require_simulation=False),
        superstructure=SimpleNamespace(omar=None),
    )


def _patch_constructor(monkeypatch):
    for name, value in {
        "RpcManager": _RpcManager,
        "PersistenceDB": lambda *args, **kwargs: None,
        "SecurityAuditStore": lambda *args, **kwargs: None,
        "DecisionEngine": lambda **kwargs: SimpleNamespace(),
        "DiscoveryManager": lambda **kwargs: SimpleNamespace(),
        "CircuitBreaker": type(
            "_CircuitBreaker",
            (),
            {
                "from_env": classmethod(lambda cls: cls()),
                "allow_auto_trading": lambda self: True,
            },
        ),
        "AnomalyBreaker": lambda **kwargs: SimpleNamespace(),
        "PerBlockCache": lambda **kwargs: SimpleNamespace(),
        "Metrics": lambda **kwargs: SimpleNamespace(
            gas_mode="standard",
            send_mode="public",
            last_submitted_block=0,
            exec_e2e_p50_ms=0.0,
            exec_e2e_p90_ms=0.0,
            exec_e2e_p99_ms=0.0,
        ),
        "LatencyProfiler": lambda **kwargs: SimpleNamespace(
            add=lambda *args: None,
            get=lambda *args: {"p50": 0.0, "p90": 0.0, "p99": 0.0},
        ),
    }.items():
        monkeypatch.setattr(runtime_constructor_facade, name, value)

    for name in (
        "initialize_execution_capture_stack",
        "initialize_runtime_institutional_stack",
        "initialize_optional_overlay_runtimes",
        "initialize_execution_support_stack",
        "initialize_optional_family_runtimes",
    ):
        monkeypatch.setattr(runtime_legacy, name, lambda *args, **kwargs: None)

    monkeypatch.setattr(
        runtime_institutional_init,
        "LedgerRepository",
        _LedgerRepo,
    )

    monkeypatch.setattr(
        runtime_execute_wrapper_facade,
        "_compat_execution_wrapper_symbols",
        lambda: (_Rpc, _fake_execute),
    )


async def _record_exec(runtime, result, opp, *, latency_ms, mode):
    runtime._recorded.append((result, opp, latency_ms, mode))


async def _fake_execute(*args, **kwargs):
    _fake_execute.decision = kwargs.get("decision")
    return SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        tx_hash="0xproduction-chain",
        plan={"latency_stages_ms": {"total": 7.0}},
    )


_fake_execute.decision = None


def _opportunity():
    return SimpleNamespace(
        id="opp-production-chain",
        route_id="route-production-chain",
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
    )


@pytest.mark.asyncio
async def test_actual_runtime_method_chain_propagates_canonical_identity_to_learning(
    monkeypatch,
):
    _patch_constructor(monkeypatch)
    runtime = RuntimeBundle(_cfg())
    runtime._omar = _Omar()
    runtime._execution_service = _RecordingExecutionService()
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
    runtime._ledger_repo = _LedgerRepo()

    opp = _opportunity()
    decision = _decision(opp)
    chosen, selected = runtime._apply_omar_to_candidate(
        opp, decision, current_block=902
    )

    assert chosen is opp
    assert selected is decision
    decision_id = selected.metadata["canonical_decision_id"]
    correlation_id = selected.metadata["correlation_id"]
    assert decision_id and correlation_id

    await runtime._execute_auto(opp, 902, decision=selected)

    assert runtime._execution_service.events == [
        "admission",
        "superstructure",
        "governance",
        "fioa",
        "bookkeeping",
    ]
    result = runtime._recorded[-1][0]
    assert result.plan["canonical_decision_id"] == decision_id
    assert result.plan["correlation_id"] == correlation_id
    assert result.plan["canonical_lineage"]["decision_id"] == decision_id
    assert result.plan["canonical_lineage"]["correlation_id"] == correlation_id
    assert _fake_execute.decision is selected

    runtime._ledger_repo.rows = [
        {
            "transaction_id": "settlement-production-chain",
            "tx_type": "receipt_settlement",
            "receipt_id": "0xproduction-chain",
            "ts_ms": 2000,
            "metadata": {
                "canonical_lineage": {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                },
                "canonical_decision_id": decision_id,
                "correlation_id": correlation_id,
                "opportunity_id": opp.id,
                "route_id": opp.route_id,
                "action": "trade",
                "expected_net_usd": 5.0,
                "realized_net_usd": 4.0,
                "gas_cost_usd": 0.2,
                "slippage_bps": 2.0,
                "latency_ms": 7,
                "truth_verified": True,
            },
        }
    ]

    settled = runtime.canonical_settled_outcome(
        tx_hash="0xproduction-chain",
        decision_id=decision_id,
        correlation_id=correlation_id,
        opportunity_id=opp.id,
    )
    assert settled is not None
    assert settled["decision_id"] == decision_id
    assert settled["correlation_id"] == correlation_id
    assert settled["opportunity_id"] == opp.id
    assert settled["source"] == "phase2_canonical_outcome_ledger"

    await runtime._execution_service.handle_post_execute_bookkeeping(
        runtime,
        opp,
        result,
        bn=902,
        latency_ms=7,
        mode="auto",
    )

    assert runtime._omar.calls
    learned = runtime._omar.calls[-1]
    assert learned["decision_id"] == decision_id
    assert learned["correlation_id"] == correlation_id
    assert learned["action"] == "trade"
    assert learned["route_id"] == opp.route_id
    assert learned["tx_hash"] == "0xproduction-chain"
    assert learned["metadata"]["source"] == "phase2_canonical_outcome_ledger"
