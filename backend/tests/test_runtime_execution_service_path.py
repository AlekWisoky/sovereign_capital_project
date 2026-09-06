from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.omar.production_lineage_bridge import install_production_lineage_bridge
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


class _ExecutionService:
    def __init__(self):
        self.events = []

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        self.events.append(("fioa", runtime, opp, decision))
        return await core()

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        self.events.append(("bookkeeping", runtime, opp, result, bn, latency_ms, mode))

    def restore_operator_overrides(self, runtime, *, old_gas_mode, old_send_mode):
        self.events.append(("restore", old_gas_mode, old_send_mode))


class _Runtime(RuntimeExecuteWrapperFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(gas_mode="standard", send_mode="public")
        )
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
        self._last_submitted_block = 17
        self.cache = object()
        self._mev_guard = None
        self._execution_service = _ExecutionService()


@pytest.mark.asyncio
async def test_prepared_auto_execution_uses_execution_service_lifecycle(monkeypatch):
    runtime = _Runtime()
    opp = SimpleNamespace(id="opp-service", meta={})
    decision = SimpleNamespace(metadata={})
    result = SimpleNamespace(ok=True, dry_run=False, submitted=True, plan={})

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _Rpc)

    async def fake_execute(*args, **kwargs):
        assert args[0].url == "read-rpc"
        assert args[1].url == "send-rpc"
        assert kwargs["decision"] is decision
        return result

    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", fake_execute)

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

    assert runtime._execution_service.events[0][0] == "fioa"
    assert runtime._execution_service.events[0][2] is opp
    assert runtime._execution_service.events[0][3] is decision
    assert runtime._execution_service.events[1][0] == "bookkeeping"
    assert runtime._execution_service.events[1][2] is opp
    assert runtime._execution_service.events[1][3] is result
    assert runtime._execution_service.events[1][4] == 123
    assert runtime._execution_service.events[1][6] == "auto"
    assert runtime._execution_service.events[2] == ("restore", "standard", "public")
    assert runtime._last_submitted_block == 17


def test_production_lineage_bridge_remains_compatible_with_execution_service_path():
    install_production_lineage_bridge()
    assert callable(getattr(RuntimeExecuteWrapperFacade, "_run_prepared_auto_execution"))
