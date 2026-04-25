from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_after_tick_facade import RuntimeAfterTickFacade

EXTRACTED_METHODS = {
    '_run_after_tick_orchestration',
}


class _CB:
    def __init__(self, allow: bool):
        self._allow = bool(allow)

    def allow_auto_trading(self) -> bool:
        return self._allow

    def remaining_cooldown_s(self) -> int:
        return 17


class _Runtime(RuntimeAfterTickFacade):
    def __init__(self, allow_auto: bool = True):
        self._auto_trading = True
        self._cb = _CB(allow_auto)
        self._errors = []
        self.calls = []

    def _maybe_dispatch_auto_trade(self, *, current_block: int, decision):
        self.calls.append(('dispatch', {'current_block': current_block, 'decision': decision}))

    def _scan_engine_opportunities(self, **kwargs):
        self.calls.append(('engine_scan', dict(kwargs)))

    async def _run_post_tick_tails(self, *, tick_failed: bool):
        self.calls.append(('post_tick', {'tick_failed': tick_failed}))

    async def _run_loop_iteration_tail(self, *, loop_started_at: float):
        self.calls.append(('loop_tail', {'loop_started_at': loop_started_at}))


class _RuntimeExplodes(_Runtime):
    def _scan_engine_opportunities(self, **kwargs):
        raise KeyError('unexpected after-tick bug')


def test_runtime_bundle_inherits_after_tick_facade():
    assert issubclass(RuntimeBundle, RuntimeAfterTickFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_after_tick_orchestration_preserves_call_order_and_arguments():
    runtime = _Runtime(allow_auto=True)
    decision = SimpleNamespace(action='trade')
    opps = [SimpleNamespace(id='o1')]

    await runtime._run_after_tick_orchestration(
        current_block=55,
        decision=decision,
        regime_label='balanced',
        mev_snap={'danger': 0.4},
        opps=opps,
        treasury_state={'cap': 1.2},
        tick_failed=False,
        loop_started_at=12.5,
    )

    assert [name for name, _ in runtime.calls] == [
        'dispatch',
        'engine_scan',
        'post_tick',
        'loop_tail',
    ]
    engine_scan = runtime.calls[1][1]
    assert engine_scan['regime_label'] == 'balanced'
    assert engine_scan['mev_state'] == {'danger': 0.4}
    assert engine_scan['base_opportunities'] == opps
    assert engine_scan['treasury_state'] == {'cap': 1.2}
    assert runtime._auto_trading is True
    assert runtime._errors == []
    assert runtime.calls[3][1]['loop_started_at'] == 12.5


@pytest.mark.asyncio
async def test_after_tick_orchestration_trips_circuit_breaker_and_skips_engine_scan_on_failed_tick():
    runtime = _Runtime(allow_auto=False)

    await runtime._run_after_tick_orchestration(
        current_block=2,
        decision=None,
        regime_label='balanced',
        mev_snap={},
        opps=[],
        treasury_state=None,
        tick_failed=True,
        loop_started_at=1.0,
    )

    assert [name for name, _ in runtime.calls] == [
        'dispatch',
        'post_tick',
        'loop_tail',
    ]
    assert runtime._auto_trading is False
    assert runtime._errors == ['circuit_breaker_tripped:cooldown_s=17']
    assert runtime.calls[1][1]['tick_failed'] is True


@pytest.mark.asyncio
async def test_after_tick_orchestration_does_not_swallow_unexpected_bug():
    runtime = _RuntimeExplodes(allow_auto=True)
    with pytest.raises(KeyError, match='unexpected after-tick bug'):
        await runtime._run_after_tick_orchestration(
            current_block=1,
            decision=None,
            regime_label='balanced',
            mev_snap={},
            opps=[],
            treasury_state=None,
            tick_failed=False,
            loop_started_at=1.0,
        )
