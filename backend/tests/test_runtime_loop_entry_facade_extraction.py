from __future__ import annotations

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_loop_entry_facade import RuntimeLoopEntryFacade


EXTRACTED_METHODS = {
    '_run_loop_entry_iteration',
}


class _RpcContext:
    def __init__(self, recorder):
        self.recorder = recorder
        self.rpc = object()

    async def __aenter__(self):
        self.recorder.append(('enter_rpc', None))
        return self.rpc

    async def __aexit__(self, exc_type, exc, tb):
        self.recorder.append(('exit_rpc', exc_type.__name__ if exc_type else None))
        return False


class _Runtime(RuntimeLoopEntryFacade):
    def __init__(self):
        self.calls = []
        self.read_url = 'https://read.example'
        self.bn = 123
        self.rpc_manager = type('Mgr', (), {'best_read': lambda s: self.read_url})()

    async def _sleep(self, seconds: float) -> None:
        self.calls.append(('sleep', seconds))

    def _rpc_context(self):
        return _RpcContext(self.calls)

    async def _prepare_tick_iteration(self, *, rpc):
        self.calls.append(('prepare', rpc))
        return self.bn

    async def _run_contained_tick_iteration(self, *, rpc, current_block: int, loop_started_at: float):
        self.calls.append(('contained', {'rpc': rpc, 'current_block': current_block, 'loop_started_at': loop_started_at}))


class _RuntimeNoRead(_Runtime):
    def __init__(self):
        super().__init__()
        self.read_url = ''


class _RuntimeNoBlock(_Runtime):
    def __init__(self):
        super().__init__()
        self.bn = None


class _RuntimeExplodes(_Runtime):
    async def _run_contained_tick_iteration(self, *, rpc, current_block: int, loop_started_at: float):
        raise KeyError('unexpected loop-entry bug')


@pytest.fixture(autouse=True)
def _patch_rpc_client(monkeypatch):
    monkeypatch.setattr('victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient', lambda *a, **k: _RpcContext([]))


def test_runtime_bundle_inherits_loop_entry_facade():
    assert issubclass(RuntimeBundle, RuntimeLoopEntryFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_loop_entry_iteration_preserves_prepare_then_contained_order(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr('victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient', lambda *a, **k: _RpcContext(runtime.calls))

    await runtime._run_loop_entry_iteration(loop_started_at=1.25)

    assert [name for name, _ in runtime.calls] == ['enter_rpc', 'prepare', 'contained', 'exit_rpc']
    assert runtime.calls[2][1]['current_block'] == 123
    assert runtime.calls[2][1]['loop_started_at'] == 1.25


@pytest.mark.asyncio
async def test_loop_entry_iteration_sleeps_when_no_read_url():
    runtime = _RuntimeNoRead()

    await runtime._run_loop_entry_iteration(loop_started_at=0.0)

    assert runtime.calls == [('sleep', 1.0)]


@pytest.mark.asyncio
async def test_loop_entry_iteration_returns_when_block_number_missing(monkeypatch):
    runtime = _RuntimeNoBlock()
    monkeypatch.setattr('victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient', lambda *a, **k: _RpcContext(runtime.calls))

    await runtime._run_loop_entry_iteration(loop_started_at=2.0)

    assert [name for name, _ in runtime.calls] == ['enter_rpc', 'prepare', 'exit_rpc']


@pytest.mark.asyncio
async def test_loop_entry_iteration_does_not_swallow_unexpected_bug(monkeypatch):
    runtime = _RuntimeExplodes()
    monkeypatch.setattr('victor_ai_bot.runtime_services.runtime_loop_entry_facade.JsonRpcClient', lambda *a, **k: _RpcContext(runtime.calls))

    with pytest.raises(KeyError, match='unexpected loop-entry bug'):
        await runtime._run_loop_entry_iteration(loop_started_at=3.0)
