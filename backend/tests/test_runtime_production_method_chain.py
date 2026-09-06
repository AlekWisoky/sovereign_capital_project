from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.decision_identity import lineage_from_opportunity
from victor_ai_bot.omar.canonical_execution import CanonicalExecutionInvariantError
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
from victor_ai_bot.runtime_legacy import RuntimeBundle


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


def _runtime():
    runtime = object.__new__(RuntimeBundle)
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="standard",
            send_mode="public",
            brain_mode="off",
        ),
    )
    runtime.metrics = SimpleNamespace(
        gas_mode="standard",
        send_mode="public",
        last_submitted_block=0,
    )
    runtime.rpc_manager = _RpcManager()
    runtime.cache = object()
    runtime._mev_guard = None
    runtime._cc = None
    runtime._execution_service = None
    runtime._last_submitted_block = 17
    runtime._pending = {}
    runtime._opps = []
    runtime._auto_queue = []
    runtime._auto_trading = True
    runtime._exec_task = None
    runtime._cb = SimpleNamespace(allow_auto_trading=lambda: True)
    runtime._omar = None
    return runtime


def _decision(opp_id: str = "opp-1"):
    return SimpleNamespace(
        action="trade",
        opp_id=opp_id,
        route_id="route-1",
        size_mult=1.0,
        borrow_mult=1.0,
        gas_mode="standard",
        p_success=0.9,
        ev_wei=10,
        portfolio=[opp_id],
        metadata={},
    )


@pytest.mark.asyncio
async def test_runtime_bundle_auto_trade_walks_actual_production_method_chain(monkeypatch):
    runtime = _runtime()
    events = []
    execution_result = SimpleNamespace(ok=True, dry_run=False, submitted=True)

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _Rpc)

    async def fake_execute(rpc_r, rpc_s, cfg, opp, bn, last_submitted_block, **kwargs):
        events.append(
            (
                "execution",
                rpc_r.url,
                rpc_s.url,
                opp,
                bn,
                last_submitted_block,
                kwargs.get("decision"),
            )
        )
        return execution_result

    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", fake_execute)

    async def record_exec(result, opp, *, latency_ms, mode):
        events.append(("record", result, opp, latency_ms, mode))

    runtime._record_exec = record_exec

    opp = SimpleNamespace(
        id="opp-1",
        route_id="route-1",
        can_execute=True,
        meta={
            "safety": {"exec_ready": True, "profit_after_costs_wei": "10"},
            "brain": {},
        },
    )
    runtime._opps = [opp]
    decision = _decision()

    dispatched = runtime._maybe_dispatch_auto_trade(current_block=123, decision=decision)
    assert dispatched is True
    await runtime._exec_task

    assert events[0][0] == "execution"
    assert events[0][1:3] == ("read-rpc", "send-rpc")
    assert events[0][3] is opp
    assert events[0][4:6] == (123, 17)
    assert events[0][6] is decision
    assert events[1][0] == "record"
    assert events[1][1] is execution_result
    assert events[1][2] is opp
    assert events[1][4] == "auto"
    assert runtime._last_submitted_block == 123
    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"] == decision.metadata["canonical_decision_id"]
    assert lineage["correlation_id"] == decision.metadata["correlation_id"]


def test_brain_mode_off_cannot_fall_back_to_legacy_best_candidate():
    runtime = _runtime()
    opp = SimpleNamespace(
        id="opp-legacy",
        route_id="route-legacy",
        can_execute=True,
        meta={"safety": {"exec_ready": True}, "brain": {}},
    )
    runtime._opps = [opp]

    assert runtime._maybe_dispatch_auto_trade(current_block=99, decision=None) is False
    assert runtime._exec_task is None


def test_non_trade_decision_cannot_reach_execution():
    runtime = _runtime()
    opp = SimpleNamespace(
        id="opp-wait",
        route_id="route-wait",
        can_execute=True,
        meta={"safety": {"exec_ready": True}, "brain": {}},
    )
    runtime._opps = [opp]
    decision = _decision("opp-wait")
    decision.action = "skip"

    assert runtime._maybe_dispatch_auto_trade(current_block=100, decision=decision) is False
    assert runtime._exec_task is None


def test_canonical_execution_invariant_rejects_missing_identity_metadata():
    from victor_ai_bot.omar.canonical_execution import require_canonical_execution_context

    runtime = _runtime()
    opp = SimpleNamespace(
        id="opp-invariant",
        route_id="route-invariant",
        meta={},
    )
    decision = _decision("opp-invariant")

    decision.metadata = {"canonical_decision_id": "wrong", "correlation_id": "wrong"}
    with pytest.raises(CanonicalExecutionInvariantError):
        require_canonical_execution_context(runtime, opp, decision, current_block=101)


def test_production_lineage_bridge_is_installed_on_runtime_decision_boundary():
    install_production_lineage_bridge()
    runtime = object.__new__(RuntimeBundle)
    runtime.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
    runtime._omar = None
    opp = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision = SimpleNamespace(metadata={})

    chosen, returned = runtime._apply_omar_to_candidate(opp, decision, current_block=456)

    assert chosen is opp
    assert returned is decision
    lineage = lineage_from_opportunity(opp)
    assert lineage["decision_id"] == decision.metadata["canonical_decision_id"]
    assert lineage["correlation_id"] == decision.metadata["correlation_id"]
