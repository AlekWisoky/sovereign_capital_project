from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import AutoExecutionDispatchContext
from victor_ai_bot.runtime_services.runtime_execute_wrapper_facade import RuntimeExecuteWrapperFacade
import victor_ai_bot.runtime_services.runtime_execute_wrapper_facade as facade_module
import victor_ai_bot.runtime_legacy as runtime_legacy_module


EXTRACTED_METHODS = {
    '_run_prepared_auto_execution',
}


class _FakeRpcClient:
    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _ExecutionService:
    def __init__(self):
        self.fioa_calls = []
        self.bookkeeping_calls = []
        self.restore_calls = []

    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        self.fioa_calls.append({'opp': opp, 'decision': decision})
        return await core()

    async def handle_post_execute_bookkeeping(self, runtime, opp, result, *, bn: int, latency_ms: int, mode: str):
        self.bookkeeping_calls.append(
            {
                'opp': opp,
                'result': result,
                'bn': bn,
                'latency_ms': latency_ms,
                'mode': mode,
            }
        )

    def restore_operator_overrides(self, runtime, *, old_gas_mode: str, old_send_mode: str):
        self.restore_calls.append({'old_gas_mode': old_gas_mode, 'old_send_mode': old_send_mode})
        runtime.cfg.execution.gas_mode = old_gas_mode
        runtime.metrics.gas_mode = old_gas_mode
        runtime.cfg.execution.send_mode = old_send_mode
        runtime.metrics.send_mode = old_send_mode


class _Runtime(RuntimeExecuteWrapperFacade):
    def __init__(self):
        self.cfg = SimpleNamespace(execution=SimpleNamespace(gas_mode='fast', send_mode='private'))
        self.metrics = SimpleNamespace(gas_mode='fast', send_mode='private', last_submitted_block=0)
        self.cache = object()
        self._mev_guard = object()
        self._last_submitted_block = 11
        self._execution_service = _ExecutionService()
        self.exec_records = []

    async def _record_exec(self, result, opp, *, latency_ms, mode):
        self.exec_records.append({'result': result, 'opp': opp, 'latency_ms': latency_ms, 'mode': mode})


@pytest.fixture(autouse=True)
def _patch_rpc_client(monkeypatch):
    monkeypatch.setattr(facade_module, 'JsonRpcClient', _FakeRpcClient)


def test_runtime_bundle_inherits_execute_wrapper_facade():
    assert issubclass(RuntimeBundle, RuntimeExecuteWrapperFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_run_prepared_auto_execution_preserves_wrapper_and_bookkeeping(monkeypatch):
    runtime = _Runtime()
    opp = SimpleNamespace(route_id='r1')
    decision = SimpleNamespace()
    prep = AutoExecutionDispatchContext(
        opportunity=opp,
        force_dry=False,
        old_gas_mode='standard',
        old_send_mode='public',
        read_url='read-url',
        send_url='send-url',
    )
    core_calls = []

    async def _fake_try_execute(rpc_r, rpc_s, cfg, got_opp, bn, last_submitted_block, **kwargs):
        core_calls.append(
            {
                'read_url': rpc_r.url,
                'send_url': rpc_s.url,
                'opp': got_opp,
                'bn': bn,
                'last_submitted_block': last_submitted_block,
                'force_dry_run': kwargs.get('force_dry_run'),
                'decision': kwargs.get('decision'),
            }
        )
        return SimpleNamespace(ok=True, dry_run=False, submitted=True)

    monkeypatch.setattr(facade_module, 'try_execute_opportunity', _fake_try_execute)

    await runtime._run_prepared_auto_execution(
        opp=opp,
        bn=123,
        decision=decision,
        prep=prep,
    )

    assert core_calls[0]['read_url'] == 'read-url'
    assert core_calls[0]['send_url'] == 'send-url'
    assert core_calls[0]['bn'] == 123
    assert core_calls[0]['last_submitted_block'] == 11
    assert core_calls[0]['decision'] is decision
    assert runtime._execution_service.fioa_calls[0]['opp'] is opp
    assert runtime._execution_service.bookkeeping_calls[0]['bn'] == 123
    assert runtime._execution_service.bookkeeping_calls[0]['mode'] == 'auto'
    assert runtime._execution_service.restore_calls[0] == {'old_gas_mode': 'standard', 'old_send_mode': 'public'}
    assert runtime.cfg.execution.gas_mode == 'standard'
    assert runtime.cfg.execution.send_mode == 'public'


@pytest.mark.asyncio
async def test_run_prepared_auto_execution_without_service_records_exec_and_updates_submitted_block(monkeypatch):
    runtime = _Runtime()
    runtime._execution_service = None
    opp = SimpleNamespace(route_id='r2')
    prep = AutoExecutionDispatchContext(
        opportunity=opp,
        force_dry=True,
        old_gas_mode='standard',
        old_send_mode='public',
        read_url='read-url',
        send_url='send-url',
    )

    async def _fake_try_execute(*args, **kwargs):
        return SimpleNamespace(ok=True, dry_run=False, submitted=True)

    monkeypatch.setattr(facade_module, 'try_execute_opportunity', _fake_try_execute)

    await runtime._run_prepared_auto_execution(
        opp=opp,
        bn=321,
        decision=None,
        prep=prep,
    )

    assert runtime.exec_records[0]['mode'] == 'auto'
    assert runtime._last_submitted_block == 321
    assert runtime.metrics.last_submitted_block == 321
    assert runtime.cfg.execution.gas_mode == 'standard'
    assert runtime.cfg.execution.send_mode == 'public'


@pytest.mark.asyncio
async def test_run_prepared_auto_execution_respects_runtime_legacy_compat_patch_seam(monkeypatch):
    runtime = _Runtime()
    runtime._execution_service = None
    opp = SimpleNamespace(route_id='compat')
    prep = AutoExecutionDispatchContext(
        opportunity=opp,
        force_dry=False,
        old_gas_mode='standard',
        old_send_mode='public',
        read_url='legacy-read',
        send_url='legacy-send',
    )
    calls = []

    class _LegacyRpcClient(_FakeRpcClient):
        pass

    async def _fake_try_execute(*args, **kwargs):
        calls.append({'rpc_type': type(args[0]).__name__, 'opp': args[3]})
        return SimpleNamespace(ok=True, dry_run=False, submitted=False)

    monkeypatch.setattr(runtime_legacy_module, 'JsonRpcClient', _LegacyRpcClient)
    monkeypatch.setattr(runtime_legacy_module, 'try_execute_opportunity', _fake_try_execute)

    await runtime._run_prepared_auto_execution(opp=opp, bn=44, decision=None, prep=prep)

    assert calls == [{'rpc_type': '_LegacyRpcClient', 'opp': opp}]
    assert runtime.exec_records[0]['opp'] is opp
