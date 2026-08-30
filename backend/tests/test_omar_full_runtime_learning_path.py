from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_constructor_facade
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade
from victor_ai_bot.runtime_services import runtime_institutional_init
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService


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


class _Latency:
    def __init__(self, **kwargs):
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


class _Anomaly:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


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

    monkeypatch.setattr(runtime_execute_wrapper_facade, "_compat_execution_wrapper_symbols", lambda: (_Rpc, _fake_execute))


def _opportunity():
    return SimpleNamespace(
        id="opp-runtime-learning",
        route_id="route-runtime-learning",
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


async def _fake_execute(*args, **kwargs):
    _fake_execute.decision = kwargs.get("decision")
    return SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        tx_hash="0xruntime-learning",
        plan={"latency_stages_ms": {"total": 7.0}},
    )


_fake_execute.decision = None


@pytest.mark.asyncio
async def test_constructor_backed_runtime_traces_decision_execution_settlement_learning(
    monkeypatch, tmp_path
):
    _patch_constructor(monkeypatch)
    monkeypatch.setattr(runtime_institutional_init, "LedgerRepository", _LedgerRepo)

    runtime = RuntimeBundle(_cfg())
    runtime._omar = OmarRuntime(
        OmarConfig(enabled=True, real_learning_min_observations=1),
        chain_name="runtime-learning",
    )
    runtime._omar.learning_path = str(tmp_path / "real_policy.json")
    runtime._omar._real_learner.path = runtime._omar.learning_path
    runtime._omar._real_learner._load()

    runtime.capital_engine_state = lambda: {
        "capital_engine": {
            "available_bankroll_wei": 100000,
            "deployable_bankroll_wei": 90000,
            "family_allocations_wei": {"ARBITRAGE": 90000},
            "status": "authorized",
            "freshness_class": "fresh",
            "authority_id": "authority-test",
            "internal_prime_available": True,
            "prime_capacity_ratio": 0.8,
            "prime_cost_bps": 5.0,
        }
    }
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

    ledger = _LedgerRepo()
    runtime._ledger_repo = ledger

    opp = _opportunity()
    decision = _decision(opp)
    chosen, selected = runtime._apply_omar_to_candidate(opp, decision, current_block=902)

    assert chosen is opp
    assert selected is decision
    canonical_decision_id = selected.metadata["canonical_decision_id"]
    correlation_id = selected.metadata["correlation_id"]
    assert canonical_decision_id
    assert correlation_id
    assert runtime._omar._pending_decisions[canonical_decision_id]["action"] in {
        "WAIT",
        "DEFEND",
        "SEEK_OPP",
        "INCREASE_RISK",
        "DECREASE_RISK",
        "EXECUTE",
    }

    await runtime._execute_auto(opp, 902, decision=selected)

    assert runtime._execution_service.events == [
        "admission",
        "superstructure",
        "governance",
        "fioa",
        "bookkeeping",
    ]
    assert runtime._recorded
    result = runtime._recorded[-1][0]
    assert result.plan["canonical_decision_id"] == canonical_decision_id
    assert result.plan["correlation_id"] == correlation_id
    assert result.plan["canonical_lineage"]["decision_id"] == canonical_decision_id
    assert result.plan["canonical_lineage"]["correlation_id"] == correlation_id
    assert _fake_execute.decision is selected

    lineage = dict(result.plan["canonical_lineage"])
    ledger.rows = [
        {
            "transaction_id": "settlement-runtime-learning",
            "tx_type": "receipt_settlement",
            "receipt_id": "0xruntime-learning",
            "ts_ms": 2000,
            "metadata": {
                "canonical_lineage": {
                    "decision_id": canonical_decision_id,
                    "correlation_id": correlation_id,
                    "sizing_id": lineage.get("sizing_id", ""),
                },
                "canonical_decision_id": canonical_decision_id,
                "correlation_id": correlation_id,
                "opportunity_id": opp.id,
                "route_id": opp.route_id,
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
        tx_hash="0xruntime-learning",
        decision_id=canonical_decision_id,
        correlation_id=correlation_id,
        opportunity_id=opp.id,
    )
    assert settled is not None
    assert settled["decision_id"] == canonical_decision_id
    assert settled["correlation_id"] == correlation_id
    assert settled["opportunity_id"] == opp.id
    assert settled["source"] == "phase2_canonical_outcome_ledger"

    # Re-run the real bookkeeping boundary after settlement exists; the
    # lifecycle bridge must consume the canonical settled record and update
    # the exact decision's pending action, not a tx-hash-derived identity.
    await runtime._execution_service.handle_post_execute_bookkeeping(
        runtime,
        opp,
        result,
        bn=902,
        latency_ms=7,
        mode="auto",
    )

    assert runtime._omar.last_outcome["decision_id"] == canonical_decision_id
    assert runtime._omar.last_outcome["action"] == runtime._omar.last_outcome.get("action")
    assert runtime._omar._real_learner.total_observations == 1
