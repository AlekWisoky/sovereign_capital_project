from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
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
    return runtime


@pytest.mark.asyncio
async def test_runtime_bundle_execute_auto_walks_production_method_chain(monkeypatch):
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
    decision = SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-1",
            "correlation_id": "corr-1",
        }
    )
    ensure_decision_identity(opp, decision, chain_name="ethereum", current_block=99)

    await runtime._execute_auto(opp, 123, decision=decision)

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
    assert lineage_from_opportunity(opp) == {
        "decision_id": decision.metadata["canonical_decision_id"],
        "correlation_id": decision.metadata["correlation_id"],
    }


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
