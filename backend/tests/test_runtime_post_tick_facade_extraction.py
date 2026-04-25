from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_post_tick_facade as post_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_post_tick_facade import RuntimePostTickFacade

EXTRACTED_METHODS = {
    '_post_tick_meta_tail',
    '_quicksight_tick_state',
    '_post_tick_quicksight_tail',
    '_run_post_tick_tails',
}


class _Meta:
    def __init__(self):
        self.calls = []

    async def tick(self, runtime):
        self.calls.append(runtime)


class _MetaValueError(_Meta):
    async def tick(self, runtime):
        raise ValueError('bad meta state')


class _QuickSight:
    def __init__(self):
        self.calls = []

    async def tick(self, state):
        self.calls.append(state)


class _QuickSightRuntimeError(_QuickSight):
    async def tick(self, state):
        raise RuntimeError('unexpected quicksight bug')


class _Snapshot:
    def __init__(self, payload):
        self.payload = payload

    def snapshot(self):
        return dict(self.payload)


class _Runtime(RuntimePostTickFacade):
    def __init__(self, *, meta=None, quicksight=None, gov=None):
        self._meta = meta
        self._quicksight = quicksight
        self._gov = gov
        self._cb = _Snapshot({'cooldown': 0})
        self._agent_perf = _Snapshot({'score': 0.9})


def test_runtime_bundle_inherits_post_tick_facade():
    assert issubclass(RuntimeBundle, RuntimePostTickFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_run_post_tick_tails_skips_after_contained_tick_failure(monkeypatch):
    monkeypatch.setattr(post_mod, 'BUS', SimpleNamespace(get=lambda _name: {}))
    runtime = _Runtime(meta=_Meta(), quicksight=_QuickSight(), gov=_Snapshot({'mode': 'live'}))

    ok = asyncio.run(runtime._run_post_tick_tails(tick_failed=True))

    assert ok is False
    assert runtime._meta.calls == []
    assert runtime._quicksight.calls == []


def test_run_post_tick_tails_coordinates_meta_and_quicksight(monkeypatch):
    monkeypatch.setattr(post_mod, 'BUS', SimpleNamespace(get=lambda name: {
        'market': {'spread': 0.02},
        'treasury': {'deployable': 5},
        'behaveagent': {'state': 'ready'},
    }.get(name)))
    monkeypatch.setattr(post_mod.time, 'time', lambda: 1234567890)

    meta = _Meta()
    quicksight = _QuickSight()
    runtime = _Runtime(meta=meta, quicksight=quicksight, gov=_Snapshot({'mode': 'live'}))

    ok = asyncio.run(runtime._run_post_tick_tails(tick_failed=False))

    assert ok is True
    assert meta.calls == [runtime]
    assert quicksight.calls == [
        {
            'ts': 1234567890,
            'market': {'spread': 0.02},
            'treasury': {'deployable': 5},
            'behaveagent': {'state': 'ready'},
            'governance': {'mode': 'live'},
            'pnl': {},
            'circuit_breaker': {'cooldown': 0},
            'agent_perf': {'score': 0.9},
        }
    ]


def test_post_tick_meta_tail_swallows_expected_local_failure():
    runtime = _Runtime(meta=_MetaValueError(), quicksight=None, gov=None)

    ok = asyncio.run(runtime._post_tick_meta_tail())

    assert ok is False


def test_post_tick_quicksight_tail_does_not_swallow_unexpected_bug(monkeypatch):
    monkeypatch.setattr(post_mod, 'BUS', SimpleNamespace(get=lambda _name: {}))
    monkeypatch.setattr(post_mod.time, 'time', lambda: 1234567890)

    runtime = _Runtime(
        meta=None,
        quicksight=_QuickSightRuntimeError(),
        gov=_Snapshot({'mode': 'live'}),
    )

    with pytest.raises(RuntimeError, match='unexpected quicksight bug'):
        asyncio.run(runtime._post_tick_quicksight_tail())
