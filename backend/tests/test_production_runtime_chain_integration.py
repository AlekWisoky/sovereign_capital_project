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
    def __init__(self, url: str, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def block_number(self):
        return 123


@pytest.mark.asyncio
async def test_production_runtime_chain_reaches_execution_with_one_identity(monkeypatch, tmp_path):
    """Walk the real decision-finalize -> execution chain with controlled I/O."""
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
            "safety": {"exec_ready": True, "profit_after_costs_wei": "100"},
            "profitability": {
                "valid": True,
                "stale": False,
                "revalidated": True,
                "profitAfterCostsWeiInt": 100,
                "reason": "ok",
            },
        },
    )

    async def postdecision_analytics(*args, **kwargs):
        return None

    runtime._run_postdecision_analytics_state = postdecision_analytics
    runtime._run_post_tick_tails = lambda *args, **kwargs: None
    runtime._run_loop_iteration_tail = lambda *args, **kwargs: None
    runtime._apply_treasury_borrow_overlay = lambda **kwargs: kwargs["decision"]

    from victor_ai_bot.decision_engine import TradeDecision

    decision = TradeDecision(
        action="trade",
        opp_id=opp.id,
        route_id=opp.route_id,
        p_success=0.99,
        ev_wei=100,
        portfolio=[opp.id],
    )

    def decide(*args, **kwargs):
        return decision

    # This is the external decision-engine boundary; the canonical finalizer,
    # identity attachment, queue refresh, and execution chain remain real.
    runtime._safe_decide_opportunities = decide
    runtime._opps = [opp]
    runtime._auto_trading = True
    runtime._pending = {}
    runtime._exec_task = None
    runtime._last_submitted_block = 0

    execution_calls = []

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

    monkeypatch.setattr(runtime_execute_wrapper_facade, "JsonRpcClient", _RpcContext)
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

    # Enter through the real production decision finalizer instead of replacing
    # the outer loop and then synchronously assert the real execution chain.
    finalized = await runtime._run_decision_finalize(
        opps=[opp],
        rpc=_RpcContext("read://test"),
        regime_label="balanced",
        treasury_state={},
        current_block=123,
        loop_started_at=1.0,
    )
    identity = identity_from(finalized)
    assert identity is not None
    assert identity.decision_id
    assert identity.correlation_id

    await runtime._execute_auto(opp, 123, decision=finalized)

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

    async def fake_execute(*args, **kwargs):
        calls.append(1)
        return ExecResult(ok=True, dry_run=True, reason="integration_test", plan={})

    monkeypatch.setattr(runtime_execute_wrapper_facade, "JsonRpcClient", _RpcContext)
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
