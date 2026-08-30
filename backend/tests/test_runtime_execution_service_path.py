from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.omar.production_lineage_bridge import (
    install_production_lineage_bridge,
)
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import (
    AutoExecutionDispatchContext,
    RuntimeExecuteWrapperFacade,
)


class _Rpc:
    def __init__(self, url: str, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Runtime(RuntimeExecuteWrapperFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(gas_mode="standard", send_mode="public"),
        )
        self.metrics = SimpleNamespace(
            gas_mode="standard",
            send_mode="public",
            last_submitted_block=17,
        )
        self._last_submitted_block = 17
        self.cache = object()
        self._mev_guard = None
        self._fioa = None
        self._lat = None
        self._cc = None
        # Use the actual production service rather than a fake lifecycle object.
        self._execution_service = ExecutionService()


@pytest.mark.asyncio
async def test_prepared_auto_execution_walks_actual_execution_service_lifecycle(monkeypatch):
    runtime = _Runtime()
    opp = SimpleNamespace(id="opp-service", route_id="route-service", meta={})
    decision = SimpleNamespace(metadata={})
    result = SimpleNamespace(ok=True, dry_run=False, submitted=True, plan={})
    events = []

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _Rpc)

    async def fake_execute(*args, **kwargs):
        assert args[0].url == "read-rpc"
        assert args[1].url == "send-rpc"
        assert kwargs["decision"] is decision
        events.append(("core", kwargs["decision"]))
        return result

    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", fake_execute)

    async def record_exec(recorded_result, recorded_opp, *, latency_ms, mode):
        events.append(("record", recorded_result, recorded_opp, latency_ms, mode))

    runtime._record_exec = record_exec

    install_production_lineage_bridge()
    prep = AutoExecutionDispatchContext(
        force_dry=False,
        old_gas_mode="standard",
        old_send_mode="public",
        read_url="read-rpc",
        send_url="send-rpc",
    )

    await runtime._run_prepared_auto_execution(
        opp=opp,
        bn=123,
        decision=decision,
        prep=prep,
    )

    assert events[0][0] == "core"
    assert events[0][1] is decision
    assert events[1][0] == "record"
    assert events[1][1] is result
    assert events[1][2] is opp
    assert events[1][4] == "auto"
    assert runtime._last_submitted_block == 123
    assert result.plan["canonical_decision_id"]
    assert result.plan["correlation_id"]
    assert result.plan["canonical_lineage"]["decision_id"] == result.plan["canonical_decision_id"]
    assert result.plan["canonical_lineage"]["correlation_id"] == result.plan["correlation_id"]


def test_production_lineage_bridge_remains_compatible_with_execution_service_path():
    install_production_lineage_bridge()
    assert callable(
        getattr(RuntimeExecuteWrapperFacade, "_run_prepared_auto_execution")
    )
