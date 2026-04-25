from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import MultiRuntimeBundle


class _Runtime:
    def __init__(self, auto_trading: bool):
        self.cfg = SimpleNamespace(execution=SimpleNamespace(auto_trading=auto_trading))
        self.settings_calls = []
        self.started = 0
        self.stopped = 0
        self.unsubscribed = 0
        self._queue = None

    def set_settings(self, **kwargs):
        self.settings_calls.append(kwargs.copy())

    def start(self):
        self.started += 1

    async def stop(self):
        self.stopped += 1

    def subscribe(self):
        return self._queue

    def unsubscribe(self, q):
        self.unsubscribed += 1


class _OneShotQueue:
    def __init__(self, stop_event: asyncio.Event, msg: dict):
        self._stop_event = stop_event
        self._msg = msg

    async def get(self):
        self._stop_event.set()
        return self._msg


class _FailingQueue:
    async def get(self):
        raise RuntimeError('fan_in_failed')


async def _exercise_stop(bundle: MultiRuntimeBundle) -> None:
    async def sleeper():
        await asyncio.sleep(10)

    bundle._fan_stop = asyncio.Event()
    bundle._fan_tasks = [asyncio.create_task(sleeper())]
    await bundle.stop()


def test_multiruntime_lifecycle_facade_preserves_chain_switch_and_start_contract() -> None:
    active = _Runtime(auto_trading=True)
    other = _Runtime(auto_trading=True)
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._active_chain = 'active'
    bundle._runtimes = {'active': active, 'other': other}
    bundle.ALLOW_AUTO_ALL = False
    bundle._fan_tasks = []
    bundle._fan_stop = asyncio.Event()
    bundle._ws_clients = []
    bundle._start_fan_in = lambda: setattr(bundle, '_fan_started', True)

    assert bundle.select_chain('other') is True
    assert bundle._active_chain == 'other'
    assert active.settings_calls[-1] == {'auto_trading': False}
    assert other.settings_calls[-1] == {'auto_trading': True}
    assert bundle.select_chain('missing') is False

    bundle.start()
    assert active.started == 1
    assert other.started == 1
    assert getattr(bundle, '_fan_started', False) is True
    assert active.settings_calls[-1] == {'auto_trading': False}
    assert other.settings_calls[-1] == {'auto_trading': True}

    asyncio.run(_exercise_stop(bundle))
    assert bundle._fan_stop.is_set() is True
    assert bundle._fan_tasks == []
    assert active.stopped == 1
    assert other.stopped == 1


def test_multiruntime_lifecycle_facade_preserves_websocket_fan_in_contract() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._fan_stop = asyncio.Event()
    bundle._fan_tasks = []
    bundle._ws_clients = []
    out_q = bundle.subscribe()

    rt = _Runtime(auto_trading=True)
    rt._queue = _OneShotQueue(bundle._fan_stop, {'type': 'tick', 'profit': '7'})

    asyncio.run(bundle._fan_one('base', rt))
    wrapped = out_q.get_nowait()
    assert wrapped == {'chain': 'base', 'type': 'tick', 'profit': '7'}
    assert rt.unsubscribed == 1

    bundle.unsubscribe(out_q)
    bundle.unsubscribe(out_q)
    assert bundle._ws_clients == []


def test_multiruntime_lifecycle_facade_degrades_fan_in_local_runtime_error() -> None:
    bundle = MultiRuntimeBundle.__new__(MultiRuntimeBundle)
    bundle._fan_stop = asyncio.Event()
    bundle._fan_tasks = []
    bundle._ws_clients = []

    rt = _Runtime(auto_trading=True)
    rt._queue = _FailingQueue()

    asyncio.run(bundle._fan_one('base', rt))
    assert rt.unsubscribed == 1
