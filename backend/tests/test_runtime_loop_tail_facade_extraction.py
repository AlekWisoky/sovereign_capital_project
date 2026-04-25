from __future__ import annotations

import asyncio
from types import SimpleNamespace

import victor_ai_bot.runtime_services.runtime_loop_tail_facade as tail_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_loop_tail_facade import RuntimeLoopTailFacade

EXTRACTED_METHODS = {
    '_record_loop_latency_tail',
    '_record_pnl_store_tail_metrics',
    '_run_loop_iteration_tail',
}


class _Control:
    def __init__(self):
        self.calls = []

    def record_loop_latency(self, runtime, loop_ms):
        self.calls.append((runtime, loop_ms))


class _Pnl:
    def __init__(self, payload):
        self.payload = payload

    def stats(self):
        return dict(self.payload)


class _Runtime(RuntimeLoopTailFacade):
    def __init__(self):
        self.metrics = SimpleNamespace(
            last_tick_ms=0,
            db_latency_ms=0.0,
            db_latency_ema_ms=0.0,
            db_errors=0,
            pnl_summary_cache_hits=0,
            pnl_summary_cache_misses=0,
            pnl_income_cache_hits=0,
            pnl_income_cache_misses=0,
        )
        self._runtime_control_service = None
        self._pnl = None
        self.broadcasts = 0

    async def _broadcast(self):
        self.broadcasts += 1


def test_runtime_bundle_inherits_loop_tail_facade():
    assert issubclass(RuntimeBundle, RuntimeLoopTailFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_record_loop_latency_tail_prefers_control_service(monkeypatch):
    runtime = _Runtime()
    control = _Control()
    runtime._runtime_control_service = control
    monkeypatch.setattr(tail_mod.time, 'perf_counter', lambda: 12.5)

    runtime._record_loop_latency_tail(loop_started_at=10.0)

    assert runtime.metrics.last_tick_ms == 0
    assert control.calls == [(runtime, 2500.0)]


def test_record_loop_latency_tail_falls_back_to_metrics(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(tail_mod.time, 'perf_counter', lambda: 10.123)

    runtime._record_loop_latency_tail(loop_started_at=10.0)

    assert runtime.metrics.last_tick_ms == 122


def test_record_pnl_store_tail_metrics_updates_metrics():
    runtime = _Runtime()
    runtime._pnl = _Pnl(
        {
            'last_db_ms': 4.5,
            'ema_db_ms': 3.25,
            'db_errors': 2,
            'summary_cache_hits': 9,
            'summary_cache_misses': 1,
            'income_cache_hits': 7,
            'income_cache_misses': 3,
        }
    )

    payload = runtime._record_pnl_store_tail_metrics()

    assert payload['last_db_ms'] == 4.5
    assert runtime.metrics.db_latency_ms == 4.5
    assert runtime.metrics.db_latency_ema_ms == 3.25
    assert runtime.metrics.db_errors == 2
    assert runtime.metrics.pnl_summary_cache_hits == 9
    assert runtime.metrics.pnl_summary_cache_misses == 1
    assert runtime.metrics.pnl_income_cache_hits == 7
    assert runtime.metrics.pnl_income_cache_misses == 3


def test_run_loop_iteration_tail_broadcasts_records_and_sleeps(monkeypatch):
    runtime = _Runtime()
    runtime._pnl = _Pnl({'last_db_ms': 1.5})
    sleeps = []
    monkeypatch.setattr(tail_mod.time, 'perf_counter', lambda: 6.0)

    async def _sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(tail_mod.asyncio, 'sleep', _sleep)

    asyncio.run(runtime._run_loop_iteration_tail(loop_started_at=5.0))

    assert runtime.broadcasts == 1
    assert runtime.metrics.last_tick_ms == 1000
    assert runtime.metrics.db_latency_ms == 1.5
    assert sleeps == [0.1]
