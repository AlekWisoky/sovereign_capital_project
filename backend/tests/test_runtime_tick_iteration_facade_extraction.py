from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_tick_iteration_facade import RuntimeTickIterationFacade

EXTRACTED_METHODS = {
    '_run_contained_tick_iteration',
}


class _Runtime(RuntimeTickIterationFacade):
    def __init__(self):
        self.calls = []
        self.failures = []

    async def _run_tick_scan_pipeline(self, **kwargs):
        self.calls.append(('scan', dict(kwargs)))
        return {
            'opps': [SimpleNamespace(id='o1')],
            'regime_label': 'balanced',
            'treasury_state': {'cap': 1.0},
            'mev_snap': {'danger': 0.25},
            'decision': SimpleNamespace(action='trade'),
        }

    async def _contain_tick_failure(self, exc):
        self.failures.append(exc)
        self.calls.append(('contain', {'exc': exc}))

    async def _run_after_tick_orchestration(self, **kwargs):
        self.calls.append(('after_tick', dict(kwargs)))


class _RuntimeExplodes(_Runtime):
    async def _run_tick_scan_pipeline(self, **kwargs):
        raise KeyError('unexpected tick bug')


def test_runtime_bundle_inherits_tick_iteration_facade():
    assert issubclass(RuntimeBundle, RuntimeTickIterationFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_run_contained_tick_iteration_preserves_scan_and_after_tick_order():
    runtime = _Runtime()

    await runtime._run_contained_tick_iteration(
        rpc=SimpleNamespace(),
        current_block=77,
        loop_started_at=12.5,
    )

    assert [name for name, _ in runtime.calls] == ['scan', 'after_tick']
    after = runtime.calls[1][1]
    assert after['current_block'] == 77
    assert after['regime_label'] == 'balanced'
    assert after['mev_snap'] == {'danger': 0.25}
    assert after['treasury_state'] == {'cap': 1.0}
    assert after['tick_failed'] is False
    assert after['loop_started_at'] == 12.5


@pytest.mark.asyncio
async def test_run_contained_tick_iteration_contains_unexpected_tick_bug_and_runs_after_tick():
    runtime = _RuntimeExplodes()

    await runtime._run_contained_tick_iteration(
        rpc=SimpleNamespace(),
        current_block=88,
        loop_started_at=9.0,
    )

    assert [name for name, _ in runtime.calls] == ['contain', 'after_tick']
    assert isinstance(runtime.failures[0], KeyError)
    after = runtime.calls[1][1]
    assert after['current_block'] == 88
    assert after['tick_failed'] is True
    assert after['regime_label'] == 'balanced'
    assert after['mev_snap'] == {}
    assert after['treasury_state'] == {}
