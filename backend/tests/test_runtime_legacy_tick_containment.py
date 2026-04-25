from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_loop_entry_facade as loop_entry_facade
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


class _FakeRpcClient:
    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def block_number(self):
        return 1


class _Discovery:
    async def maybe_discover_univ3(self, *_args, **_kwargs):
        return []


class _Anomaly:
    def observe_rpc_error(self, **_kwargs):
        return False

    def observe_gas(self, **_kwargs):
        return False


def _build_runtime(monkeypatch: pytest.MonkeyPatch):
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._stop = asyncio.Event()
    bundle._errors = []
    bundle._auto_trading = False
    bundle._opps = []
    bundle._pending = []
    bundle._exec_task = None
    bundle._cb = SimpleNamespace(allow_auto_trading=lambda: False)
    bundle.metrics = SimpleNamespace(
        last_error='',
        failed_ticks=0,
        last_block=0,
        last_tick_ms=0,
        db_latency_ms=0.0,
        db_latency_ema_ms=0.0,
        db_errors=0,
        pnl_summary_cache_hits=0,
        pnl_summary_cache_misses=0,
        pnl_income_cache_hits=0,
        pnl_income_cache_misses=0,
    )
    bundle.rpc_manager = SimpleNamespace(best_read=lambda: 'http://rpc.example')
    bundle.cache = SimpleNamespace(reset_if_new_block=lambda *_args, **_kwargs: None)
    bundle.cfg = SimpleNamespace(
        chain=SimpleNamespace(chain_id=1),
        flags=SimpleNamespace(
            enable_two_leg_loops=True,
            enable_three_leg_loops=False,
            enable_v3_triangular=False,
        ),
        safety=SimpleNamespace(slippage_bps=0),
        execution=SimpleNamespace(brain_mode='off', max_pending_txs=1),
    )
    bundle._anomaly = _Anomaly()
    bundle._discovery = _Discovery()
    bundle._pnl = None
    bundle._runtime_control_service = None
    bundle._resolve_amount_in = lambda: 0

    async def _broadcast() -> None:
        bundle._stop.set()

    bundle._broadcast = _broadcast

    def _record_and_stop(error: Exception) -> None:
        RuntimeDecisionFacade._record_tick_failure(bundle, error)
        bundle._stop.set()

    bundle._record_tick_failure = _record_and_stop

    monkeypatch.setattr(loop_entry_facade, 'JsonRpcClient', _FakeRpcClient)
    return bundle


def test_runtime_loop_process_boundary_contains_unexpected_tick_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_runtime(monkeypatch)

    async def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError('tick boom')

    bundle._safe_annotate_can_execute = _raise_unexpected

    asyncio.run(bundle._loop())

    assert bundle.metrics.last_error == 'tick boom'
    assert bundle.metrics.failed_ticks == 1
    assert bundle._errors == ['tick boom']




def test_runtime_loop_clears_stale_opportunities_after_contained_tick_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_runtime(monkeypatch)
    bundle._auto_trading = True
    bundle._cb = SimpleNamespace(allow_auto_trading=lambda: True)
    stale = SimpleNamespace(id='stale', can_execute=True, meta={'safety': {'exec_ready': True}})
    bundle._opps = [stale]

    async def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError('tick boom')

    async def _execute_auto(*_args, **_kwargs):
        raise AssertionError('stale opportunity should not execute after contained tick bug')

    bundle._safe_annotate_can_execute = _raise_unexpected
    bundle._execute_auto = _execute_auto

    asyncio.run(bundle._loop())

    assert bundle.metrics.last_error == 'tick boom'
    assert bundle.metrics.failed_ticks == 1
    assert bundle._errors == ['tick boom']
    assert bundle._opps == []
    assert bundle._exec_task is None


def test_runtime_loop_clears_stale_spread_and_engine_state_after_contained_tick_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_runtime(monkeypatch)
    bundle._spread_opps = [SimpleNamespace(symbol='ETH/USDC', spread=0.05, opp_type='cross_chain')]
    bundle._spread_last = {'count': 1}
    bundle._engine_last = {'items': [{'id': 'stale'}], 'capabilities': {'mev': True}, 'summary': {'engines': ['stale']}}
    engine_calls = []

    async def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError('tick boom')

    class _EngineService:
        def scan(self, *_args, **_kwargs):
            engine_calls.append('scan')
            return {'items': [{'id': 'fresh'}], 'capabilities': {}, 'summary': {'engines': ['fresh']}}

    bundle._safe_annotate_can_execute = _raise_unexpected
    bundle._engine_service = _EngineService()

    asyncio.run(bundle._loop())

    assert bundle.metrics.last_error == 'tick boom'
    assert bundle.metrics.failed_ticks == 1
    assert bundle._errors == ['tick boom']
    assert bundle._spread_opps == []
    assert bundle._spread_last == {}
    assert bundle._engine_last == {
        'items': [],
        'capabilities': {},
        'summary': {'engines': []},
    }
    assert engine_calls == []

def test_runtime_loop_skips_meta_and_quicksight_ticks_after_contained_tick_bug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_runtime(monkeypatch)
    calls = []

    class _Meta:
        async def tick(self, runtime):
            calls.append(("meta", runtime))

    class _QuickSight:
        async def tick(self, state):
            calls.append(("quicksight", state))

    async def _raise_unexpected(*_args, **_kwargs):
        raise RuntimeError('tick boom')

    bundle._meta = _Meta()
    bundle._quicksight = _QuickSight()
    bundle._safe_annotate_can_execute = _raise_unexpected

    asyncio.run(bundle._loop())

    assert bundle.metrics.last_error == 'tick boom'
    assert bundle.metrics.failed_ticks == 1
    assert bundle._errors == ['tick boom']
    assert calls == []


def test_runtime_loop_does_not_swallow_cancelled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_runtime(monkeypatch)

    async def _raise_cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError()

    bundle._safe_annotate_can_execute = _raise_cancelled

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bundle._loop())

    assert bundle.metrics.failed_ticks == 0
    assert bundle._errors == []
