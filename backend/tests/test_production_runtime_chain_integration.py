from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.config import load_config
from victor_ai_bot.execution import ExecResult
from victor_ai_bot.identity import identity_from
from victor_ai_bot.models import Opportunity, Route, RouteLeg
from victor_ai_bot.runtime import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade


class _RpcContext:
    def __init__(self, url: str):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def block_number(self):
        return 123


@pytest.mark.asyncio
async def test_production_runtime_chain_reaches_execution_with_one_identity(monkeypatch, tmp_path):
    """Walk the real RuntimeBundle/facade chain to the execution boundary.

    External boundaries are deterministic: RPC transport, market scan, and the
    actual wallet/chain execution call are replaced. The orchestration and
    execution-service facades remain real, so this catches identity/ordering
    gaps that unit extraction tests cannot see.
    """
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    cfg = load_config("config/ethereum.yaml")
    cfg.execution.brain_mode = "auto"
    cfg.execution.auto_trading = True
    cfg.execution.dry_run = True

    runtime = RuntimeBundle(cfg)
    runtime.rpc_manager.best_read = lambda: "read://test"
    runtime.rpc_manager.best_send = lambda: "send://test"
    runtime.rpc_manager.best_private = lambda: ""
    runtime._cb = SimpleNamespace(allow_auto_trading=lambda: True, remaining_cooldown_s=lambda: 0)

    route = Route(
        legs=[
            RouteLeg(
                dex="univ3",
                venue="test",
                token_in="0x0000000000000000000000000000000000000001",
                token_out="0x0000000000000000000000000000000000000002",
                amount_in="1000",
                min_out="1100",
            )
        ]
    )
    opp = Opportunity(
        id="opp-production-chain",
        chain="ethereum",
        strategy="flash_arb",
        expected_profit_raw="100",
        expected_profit_usd="1",
        route=route,
        min_outs=["1100"],
        route_id="route-production-chain",
        can_execute=True,
        meta={
            "safety": {
                "exec_ready": True,
                "profit_after_costs_wei": "100",
            },
            "profitability": {
                "valid": True,
                "stale": False,
                "revalidated": True,
                "profitAfterCostsWeiInt": 100,
                "reason": "ok",
            },
        },
    )

    # External market/quote boundary: deterministic candidate enters the real
    # runtime scan -> decision -> dispatch orchestration.
    async def scan_primary(*args, **kwargs):
        return [opp]

    async def annotate(*args, **kwargs):
        return None

    async def postdecision_analytics(*args, **kwargs):
        return None

    async def post_tick_tails(*args, **kwargs):
        return None

    async def loop_iteration_tail(*args, **kwargs):
        return None

    runtime._scan_primary_opportunities = scan_primary
    runtime._safe_annotate_can_execute = annotate
    runtime._gas_signal_snapshot = lambda rpc: {
        "basefee_gwei": 20.0,
        "priority_gwei": 1.0,
    }
    runtime._market_signal_snapshot = lambda opps: {
        "mev_risk": 0.0,
        "pending_rate": 0.0,
        "avg_margin_ratio": 1.0,
        "volatility_proxy": 0.01,
    }
    runtime._behave_regime_state = lambda **kwargs: {"regime_label": "balanced"}
    runtime._resolve_market_regime = lambda **kwargs: {"regime_label": "balanced"}
    runtime._apply_treasury_guidance = lambda **kwargs: {
        "treasury_state": {},
        "behave_state": {"regime_label": "balanced"},
    }
    runtime._run_predecision_additive_state = lambda **kwargs: {"mev_snap": {}}
    runtime._run_postdecision_analytics_state = postdecision_analytics
    runtime._run_post_tick_tails = post_tick_tails
    runtime._run_loop_iteration_tail = loop_iteration_tail

    from victor_ai_bot.decision_engine import TradeDecision

    identity = None
    decision = TradeDecision(
        action="trade",
        opp_id=opp.id,
        route_id=opp.route_id,
        p_success=0.99,
        ev_wei=100,
        portfolio=[opp.id],
    )

    def decide(*args, **kwargs):
        from victor_ai_bot.identity import attach_identity, new_decision_identity

        nonlocal identity
        identity = new_decision_identity()
        return attach_identity(decision, identity)

    runtime._safe_decide_opportunities = decide

    execution_calls = []

    class FakeRpc(_RpcContext):
        pass

    async def fake_execute(*args, **kwargs):
        execution_calls.append(kwargs)
        return ExecResult(
            ok=True,
            dry_run=True,
            reason="integration_test",
            tx_hash="0xtest",
            plan={},
            attempted=True,
            submitted=False,
        )

    monkeypatch.setattr(runtime_execute_wrapper_facade, "JsonRpcClient", FakeRpc)
    monkeypatch.setattr(runtime_execute_wrapper_facade, "try_execute_opportunity", fake_execute)

    recorded = []

    async def record_exec(result, opportunity, *, latency_ms, mode):
        recorded.append(
            {
                "result": result,
                "opportunity": opportunity,
                "latency_ms": latency_ms,
                "mode": mode,
            }
        )

    runtime._record_exec = record_exec

    # Start at the real production loop entry. Only external I/O boundaries
    # above are controlled.
    await runtime._run_loop_entry_iteration(loop_started_at=1.0)

    assert identity is not None
    assert len(execution_calls) == 1
    assert len(recorded) == 1
    result = recorded[0]["result"]

    result_identity = identity_from(result)
    assert result_identity is not None
    assert result_identity.decision_id == identity.decision_id
    assert result_identity.correlation_id == identity.correlation_id
    assert result_identity.execution_id
    assert result_identity.settlement_id == ""
    assert result.plan["identity"]["decision_id"] == identity.decision_id
    assert result.plan["lineage"]["correlation_id"] == identity.correlation_id
    assert recorded[0]["opportunity"].id == opp.id
    assert recorded[0]["mode"] == "auto"


@pytest.mark.asyncio
async def test_production_runtime_chain_keeps_execution_identity_per_attempt(monkeypatch, tmp_path):
    """A second execution attempt gets a new execution_id under one decision."""
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))
    cfg = load_config("config/ethereum.yaml")
    cfg.execution.brain_mode = "auto"
    cfg.execution.dry_run = True

    runtime = RuntimeBundle(cfg)
    runtime.rpc_manager.best_read = lambda: "read://test"
    runtime.rpc_manager.best_send = lambda: "send://test"
    runtime.rpc_manager.best_private = lambda: ""

    from victor_ai_bot.decision_engine import TradeDecision
    from victor_ai_bot.identity import attach_identity, new_decision_identity

    decision = TradeDecision(action="trade", opp_id="opp", route_id="route")
    decision_identity = new_decision_identity()
    attach_identity(decision, decision_identity)

    calls = []

    class FakeRpc(_RpcContext):
        pass

    async def fake_execute(*args, **kwargs):
        calls.append(1)
        return ExecResult(ok=True, dry_run=True, reason="integration_test", plan={})

    monkeypatch.setattr(runtime_execute_wrapper_facade, "JsonRpcClient", FakeRpc)
    monkeypatch.setattr(runtime_execute_wrapper_facade, "try_execute_opportunity", fake_execute)
    runtime._record_exec = lambda *args, **kwargs: None

    prep = SimpleNamespace(
        opportunity=SimpleNamespace(id="opp", route_id="route"),
        force_dry=False,
        old_gas_mode="standard",
        old_send_mode="public",
        read_url="read://test",
        send_url="send://test",
    )

    await runtime._run_prepared_auto_execution(
        opp=prep.opportunity,
        bn=123,
        decision=decision,
        prep=prep,
    )
    first = identity_from(
        runtime_execute_wrapper_facade._ensure_execution_identity(
            ExecResult(ok=True, dry_run=True, reason="test", plan={}), decision
        )
    )

    second = identity_from(
        runtime_execute_wrapper_facade._ensure_execution_identity(
            ExecResult(ok=True, dry_run=True, reason="test", plan={}), decision
        )
    )

    assert len(calls) == 1
    assert first is not None and second is not None
    assert first.decision_id == second.decision_id == decision_identity.decision_id
    assert first.correlation_id == second.correlation_id == decision_identity.correlation_id
    assert first.execution_id != second.execution_id
