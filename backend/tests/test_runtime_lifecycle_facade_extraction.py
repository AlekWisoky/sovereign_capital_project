from __future__ import annotations

import asyncio

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_lifecycle_facade import RuntimeLifecycleFacade


EXTRACTED_METHODS = {
    'start',
    'stop',
}


class _RpcManager:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    async def stop(self) -> None:
        self.stopped += 1


class _OptionalRuntime:
    def __init__(self, fail_start: bool = False, fail_stop: bool = False):
        self.started = 0
        self.stopped = 0
        self.fail_start = fail_start
        self.fail_stop = fail_stop

    def start(self, *_args) -> None:
        self.started += 1
        if self.fail_start:
            raise RuntimeError('boom')

    async def stop(self) -> None:
        self.stopped += 1
        if self.fail_stop:
            raise RuntimeError('boom')


class _Runtime(RuntimeLifecycleFacade):
    def __init__(self):
        self._task = None
        self._receipt_task = None
        self._stop = asyncio.Event()
        self.rpc_manager = _RpcManager()
        self._arbitrage = _OptionalRuntime()
        self._mev = _OptionalRuntime()
        self._meta = _OptionalRuntime()
        self._super = _OptionalRuntime()
        self._fioa = _OptionalRuntime()
        self._inl = _OptionalRuntime()
        self.receipt_cancelled = False

    async def _receipt_loop(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.receipt_cancelled = True
            raise

    async def _loop(self) -> None:
        await self._stop.wait()


class _RuntimeWithStartFailure(_Runtime):
    def __init__(self):
        super().__init__()
        self._meta = _OptionalRuntime(fail_start=True)


class _RuntimeWithStopFailure(_Runtime):
    def __init__(self):
        super().__init__()
        self._super = _OptionalRuntime(fail_stop=True)


async def _exercise_start_stop(runtime: _Runtime) -> _Runtime:
    runtime.start()
    await asyncio.sleep(0)
    await runtime.stop()
    await asyncio.sleep(0)
    return runtime


def test_runtime_bundle_inherits_extracted_lifecycle_facade():
    assert issubclass(RuntimeBundle, RuntimeLifecycleFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_lifecycle_facade_preserves_start_stop_behavior():
    runtime = asyncio.run(_exercise_start_stop(_Runtime()))

    assert runtime.rpc_manager.started == 1
    assert runtime.rpc_manager.stopped == 1
    assert runtime._arbitrage.started == 1
    assert runtime._mev.started == 1
    assert runtime._meta.started == 1
    assert runtime._super.started == 1
    assert runtime._fioa.started == 1
    assert runtime._inl.started == 1
    assert runtime._arbitrage.stopped == 1
    assert runtime._mev.stopped == 1
    assert runtime._meta.stopped == 1
    assert runtime._super.stopped == 1
    assert runtime._fioa.stopped == 1
    assert runtime._inl.stopped == 1
    assert runtime.receipt_cancelled is True
    assert runtime._task.done() is True


def test_runtime_lifecycle_facade_contains_expected_optional_runtime_failures():
    start_runtime = asyncio.run(_exercise_start_stop(_RuntimeWithStartFailure()))
    assert start_runtime.rpc_manager.started == 1
    assert start_runtime.rpc_manager.stopped == 1
    assert start_runtime._meta.started == 1

    stop_runtime = asyncio.run(_exercise_start_stop(_RuntimeWithStopFailure()))
    assert stop_runtime.rpc_manager.started == 1
    assert stop_runtime.rpc_manager.stopped == 1
    assert stop_runtime._super.stopped == 1
