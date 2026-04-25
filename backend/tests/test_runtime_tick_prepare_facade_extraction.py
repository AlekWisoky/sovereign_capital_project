from __future__ import annotations

import pytest

import victor_ai_bot.runtime_services.runtime_tick_prepare_facade as tick_prepare_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_tick_prepare_facade import RuntimeTickPrepareFacade

EXTRACTED_METHODS = {
    '_prepare_tick_iteration',
}


class _SleepRecorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds: float):
        self.calls.append(float(seconds))


class _Anomaly:
    def __init__(self, storm: bool = False):
        self.storm = bool(storm)
        self.calls = []

    def observe_rpc_error(self, **kwargs):
        self.calls.append(dict(kwargs))
        if kwargs.get('ok') is False:
            return self.storm
        return False


class _Cache:
    def __init__(self):
        self.calls = []

    def reset_if_new_block(self, chain_id: int, block: int):
        self.calls.append((chain_id, block))


class _Audit:
    def __init__(self):
        self.entries = []

    def append(self, kind: str, payload, **kwargs):
        self.entries.append((kind, payload, kwargs))


class _CC:
    def __init__(self):
        self.controls = type('Controls', (), {
            'chaos_breakers_enabled': True,
            'paused': False,
            'defensive_mode': False,
            'reduce_exposure_half': False,
        })()
        self.audit = _Audit()
        self.persisted = 0

    def persist_controls(self):
        self.persisted += 1


class _Runtime(RuntimeTickPrepareFacade):
    def __init__(self, *, last_block: int = 0, storm: bool = False):
        self.metrics = type('Metrics', (), {'last_error': '', 'failed_ticks': 0, 'last_block': last_block})()
        self._anomaly = _Anomaly(storm=storm)
        self._cc = _CC()
        self._auto_trading = True
        self.cache = _Cache()
        self.cfg = type('Cfg', (), {'chain': type('Chain', (), {'chain_id': 8453})()})()
        self._runtime_control_service = type('Control', (), {'apply_brain_mode_override': lambda _, runtime: setattr(runtime, '_brain_override_applied', True)})()
        self._brain_override_applied = False


class _Rpc:
    def __init__(self, value):
        self.value = value

    async def block_number(self):
        return self.value


class _ExplodingRuntime(_Runtime):
    def __init__(self):
        super().__init__()
        self._runtime_control_service = type('Control', (), {'apply_brain_mode_override': lambda *_a, **_k: (_ for _ in ()).throw(ZeroDivisionError('unexpected prepare bug'))})()


@pytest.mark.asyncio
async def test_runtime_bundle_inherits_tick_prepare_facade():
    assert issubclass(RuntimeBundle, RuntimeTickPrepareFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_prepare_tick_iteration_handles_missing_block_and_rpc_storm(monkeypatch):
    runtime = _Runtime(storm=True)
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(tick_prepare_mod.asyncio, 'sleep', sleep_recorder)

    result = await runtime._prepare_tick_iteration(rpc=_Rpc(None))

    assert result is None
    assert runtime.metrics.last_error == 'block_number failed'
    assert runtime.metrics.failed_ticks == 1
    assert runtime._auto_trading is False
    assert runtime._cc.controls.paused is True
    assert runtime._cc.controls.defensive_mode is True
    assert runtime._cc.controls.reduce_exposure_half is True
    assert runtime._cc.persisted == 1
    assert runtime._cc.audit.entries[0][0] == 'breaker_trip'
    assert sleep_recorder.calls == [1.0]


@pytest.mark.asyncio
async def test_prepare_tick_iteration_skips_repeated_block_after_resetting_rpc_streak(monkeypatch):
    runtime = _Runtime(last_block=10)
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(tick_prepare_mod.asyncio, 'sleep', sleep_recorder)

    result = await runtime._prepare_tick_iteration(rpc=_Rpc(10))

    assert result is None
    assert runtime._anomaly.calls == [{'ok': True}]
    assert runtime.cache.calls == []
    assert sleep_recorder.calls == [0.4]


@pytest.mark.asyncio
async def test_prepare_tick_iteration_resets_cache_and_applies_brain_override(monkeypatch):
    runtime = _Runtime(last_block=9)
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(tick_prepare_mod.asyncio, 'sleep', sleep_recorder)

    result = await runtime._prepare_tick_iteration(rpc=_Rpc(12))

    assert result == 12
    assert runtime.metrics.last_block == 12
    assert runtime.cache.calls == [(8453, 12)]
    assert runtime._brain_override_applied is True
    assert sleep_recorder.calls == []


@pytest.mark.asyncio
async def test_prepare_tick_iteration_does_not_swallow_unexpected_bug(monkeypatch):
    runtime = _ExplodingRuntime()
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(tick_prepare_mod.asyncio, 'sleep', sleep_recorder)

    with pytest.raises(ZeroDivisionError, match='unexpected prepare bug'):
        await runtime._prepare_tick_iteration(rpc=_Rpc(13))
