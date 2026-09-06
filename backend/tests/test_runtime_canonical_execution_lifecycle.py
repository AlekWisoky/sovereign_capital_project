from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.omar.canonical_execution import require_canonical_execution_context
from victor_ai_bot.omar.native_hooks import execution_hook, settlement_hook
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)


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


class _CapitalLedger:
    def __init__(self):
        self.rows = []

    def all_transactions(self, *, chain):
        return list(self.rows)


class _ExecutionService:
    def __init__(self, events):
        self.events = events

    def handle_auto_trade_admission(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("capital_admission")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def handle_superstructure_pre_execute(self, runtime, opp, decision, *, force_dry_run):
        self.events.append("superstructure")
        return SimpleNamespace(
            opportunity=opp,
            blocked_result=None,
            super_enabled=False,
            old_gas_mode="standard",
            old_send_mode="public",
        )

    def handle_governance_pre_execute(self, runtime, opp, bn, decision, *, force_dry_run):
        self.events.append("governance")
        return SimpleNamespace(opportunity=opp, blocked_result=None)

    def apply_operator_overrides(self, runtime, opp, *, force_dry_run=False):
        return opp, force_dry_run, runtime.cfg.execution.gas_mode, runtime.cfg.execution.send_mode

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        self.events.append("execution_wrapper")
        return await core()

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        self.events.append("execution_record")
        execution_hook(
            runtime,
            opp,
            getattr(result, "decision", None),
            result,
            bn=int(bn),
            latency_ms=int(latency_ms),
            mode=str(mode),
        )
        runtime._last_submitted_block = int(bn)
        runtime.metrics.last_submitted_block = int(bn)

    def restore_operator_overrides(self, runtime, *, old_gas_mode, old_send_mode):
        runtime.cfg.execution.gas_mode = old_gas_mode
        runtime.cfg.execution.send_mode = old_send_mode


class _Omar:
    enabled = True

    def __init__(self, events):
        self.events = events
        self.outcomes = []

    def recommend(self, context):
        return SimpleNamespace(
            action="EXECUTE",
            state_key="state-key",
            confidence=1.0,
            trained=True,
            observations=10,
            reason="test",
            veto=False,
            size_mult=1.0,
            gas_mode="standard",
            to_dict=lambda: {"action": "EXECUTE"},
        )

    def observe_decision(self, **kwargs):
        self.events.append("omar_decision")

    def observe_outcome(self, **kwargs):
        self.events.append("omar_learning")
        self.outcomes.append(kwargs)


def _runtime(events):
    runtime = object.__new__(RuntimeBundle)
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="standard",
            send_mode="public",
            brain_mode="off",
            max_pending_txs=1,
        ),
    )
    runtime.metrics = SimpleNamespace(
        gas_mode="standard",
        send_mode="public",
        last_submitted_block=0,
        last_error="",
        failed_ticks=0,
    )
    runtime.rpc_manager = _RpcManager()
    runtime.cache = object()
    runtime._mev_guard = None
    runtime._cc = None
    runtime._execution_service = _ExecutionService(events)
    runtime._last_submitted_block = 17
    runtime._pending = {}
    runtime._opps = []
    runtime._auto_queue = []
    runtime._auto_queue_block = 0
    runtime._auto_trading = True
    runtime._exec_task = None
    runtime._cb = SimpleNamespace(allow_auto_trading=lambda: True)
    runtime._omar = _Omar(events)
    runtime._errors = []
    runtime._state_lock = None
    runtime._spread_opps = []
    runtime._spread_last = {}
    runtime._engine_last = {}
    runtime._ledger_repo = _CapitalLedger()
    runtime._last_settlement_sync = {}
    return runtime


@pytest.mark.asyncio
async def test_production_tick_to_execution_to_settlement_to_omar_lineage(monkeypatch):
    events = ["tick"]
    runtime = _runtime(events)

    opp = SimpleNamespace(
        id="opp-production",
        route_id="route-production",
        can_execute=True,
        meta={
            "safety": {"exec_ready": True, "profit_after_costs_wei": "100"},
            "brain": {"p_success": 0.9, "ev_wei": 100},
        },
    )
    decision = SimpleNamespace(
        action="trade",
        opp_id=opp.id,
        route_id=opp.route_id,
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        p_success=0.9,
        ev_wei=100,
        portfolio=[opp.id],
        metadata={},
    )

    async def scan_primary(*_args, **_kwargs):
        events.append("scan")
        return [opp]

    async def noop_annotate(*_args, **_kwargs):
        return None

    async def gas(*_args, **_kwargs):
        return {"basefee_gwei": 20.0, "priority_gwei": 1.0}

    async def postdecision(*_args, **_kwargs):
        return None

    async def posttick(*_args, **_kwargs):
        return None

    async def looptail(*_args, **_kwargs):
        return None

    runtime._resolve_amount_in = lambda: 1
    runtime._scan_primary_opportunities = scan_primary
    runtime._safe_annotate_can_execute = noop_annotate
    runtime._gas_signal_snapshot = gas
    runtime._market_signal_snapshot = lambda _opps: {
        "mev_risk": 0.1,
        "pending_rate": 0.1,
        "avg_margin_ratio": 2.0,
        "volatility_proxy": 0.1,
    }
    runtime._behave_regime_state = lambda **_kwargs: {"regime_label": "balanced"}
    runtime._resolve_market_regime = lambda **_kwargs: {"regime_label": "balanced"}
    runtime._apply_treasury_guidance = lambda **_kwargs: {
        "treasury_state": {},
        "behave_state": {"regime_label": "balanced"},
    }
    runtime._run_predecision_additive_state = lambda **_kwargs: {"mev_snap": {}}
    runtime._safe_decide_opportunities = lambda *_args, **_kwargs: decision
    runtime._run_postdecision_analytics_state = postdecision
    runtime._scan_engine_opportunities = lambda **_kwargs: None
    runtime._run_post_tick_tails = posttick
    runtime._run_loop_iteration_tail = looptail

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _Rpc)

    async def fake_execute(rpc_r, rpc_s, cfg, opp_arg, bn, last_submitted_block, **kwargs):
        events.append("execution")
        assert rpc_r.url == "read-rpc"
        assert rpc_s.url == "send-rpc"
        assert opp_arg is opp
        assert bn == 123
        assert last_submitted_block == 17
        assert kwargs["decision"] is decision
        return SimpleNamespace(
            ok=True,
            dry_run=False,
            submitted=True,
            tx_hash="0xtx-production",
            plan={"decision_id": decision.metadata["canonical_decision_id"]},
            decision=decision,
        )

    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", fake_execute)

    await runtime._run_contained_tick_iteration(
        rpc=object(), current_block=123, loop_started_at=0.0
    )
    assert runtime._exec_task is not None
    await runtime._exec_task

    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"] == decision.metadata["canonical_decision_id"]
    assert lineage["correlation_id"] == decision.metadata["correlation_id"]

    # The canonical Phase 2 ledger is the only settlement authority consumed
    # by the lifecycle bridge; no receipt/PnL inference is accepted here.
    runtime._ledger_repo.rows.append(
        {
            "tx_type": "receipt_settlement",
            "transaction_id": "settlement-1",
            "receipt_id": "0xtx-production",
            "ts_ms": 123456,
            "metadata": {
                "tx_hash": "0xtx-production",
                "canonical_lineage": dict(lineage),
                "opportunity_id": opp.id,
                "route_id": opp.route_id,
                "ok": True,
                "realized_net_usd": 1.25,
                "expected_net_usd": 1.10,
                "amount_in_wei": 100,
                "gas_cost_usd": 0.05,
                "slippage_bps": 2.0,
                "latency_ms": 31,
                "truth_verified": True,
            },
        }
    )

    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    settled = runtime.canonical_settled_outcome(tx_hash="0xtx-production")
    assert settled is not None
    assert settled["decision_id"] == lineage["decision_id"]
    assert settled["correlation_id"] == lineage["correlation_id"]
    assert settled["opportunity_id"] == opp.id

    settlement_hook(runtime, opp, settled)
    assert runtime._omar.outcomes
    assert runtime._omar.outcomes[-1]["decision_id"] == lineage["decision_id"]
    assert runtime._omar.outcomes[-1]["tx_hash"] == "0xtx-production"

    assert events.index("scan") < events.index("omar_decision")
    assert events.index("capital_admission") < events.index("governance")
    assert events.index("governance") < events.index("execution_wrapper")
    assert events.index("execution_wrapper") < events.index("execution")
    assert events.index("execution") < events.index("execution_record")
