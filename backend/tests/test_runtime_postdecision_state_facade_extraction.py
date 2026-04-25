from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_postdecision_state_facade as post_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_postdecision_state_facade import RuntimePostdecisionStateFacade

EXTRACTED_METHODS = {
    '_run_postdecision_analytics_state',
}


class _AsyncLock:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        self.calls.append(('lock_enter', None))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.calls.append(('lock_exit', None))
        return False


class _Runtime(RuntimePostdecisionStateFacade):
    def __init__(self):
        self.calls = []
        self.metrics = SimpleNamespace(scan_ms=0, last_error='boom')
        self._state_lock = _AsyncLock(self.calls)
        self._opps = []

    async def _annotate_unit_economics(self, **kwargs):
        self.calls.append(('unit_econ', dict(kwargs)))
        return True

    def _annotate_execution_capture(self, opps, regime_label):
        self.calls.append(('capture', {'opps': list(opps), 'regime_label': regime_label}))

    def _publish_dex_scan_summary(self, *, opps):
        self.calls.append(('caq', {'opps': list(opps)}))
        return True


class _RuntimeCaptureError(_Runtime):
    def _annotate_execution_capture(self, opps, regime_label):
        raise ValueError('typed capture issue')


class _RuntimePublishKeyError(_Runtime):
    def _publish_dex_scan_summary(self, *, opps):
        raise KeyError('unexpected publication bug')


def test_runtime_bundle_inherits_postdecision_state_facade():
    assert issubclass(RuntimeBundle, RuntimePostdecisionStateFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_run_postdecision_state_preserves_order_state_commit_and_summary(monkeypatch):
    runtime = _Runtime()
    opps = [SimpleNamespace(route_id='a'), SimpleNamespace(route_id='b')]
    monkeypatch.setattr(post_mod.time, 'perf_counter', lambda: 10.25)

    result = await runtime._run_postdecision_analytics_state(
        opps=opps,
        rpc='rpc',
        regime_label='risk_on',
        current_block=77,
        loop_started_at=10.0,
    )

    assert result is True
    assert runtime.calls[0] == (
        'unit_econ',
        {
            'opps': opps,
            'rpc': 'rpc',
            'current_block': 77,
        },
    )
    assert runtime.calls[1] == ('capture', {'opps': opps, 'regime_label': 'risk_on'})
    assert runtime.calls[2] == ('lock_enter', None)
    assert runtime.calls[3] == ('lock_exit', None)
    assert runtime.calls[4] == ('caq', {'opps': opps})
    assert runtime._opps == opps
    assert runtime.metrics.scan_ms == 250
    assert runtime.metrics.last_error == ''


@pytest.mark.asyncio
async def test_run_postdecision_state_is_operator_safe_on_typed_capture_failure(monkeypatch):
    runtime = _RuntimeCaptureError()
    opps = [SimpleNamespace(route_id='c')]
    monkeypatch.setattr(post_mod.time, 'perf_counter', lambda: 3.1)

    result = await runtime._run_postdecision_analytics_state(
        opps=opps,
        rpc='rpc',
        regime_label='balanced',
        current_block=9,
        loop_started_at=3.0,
    )

    assert result is True
    assert runtime._opps == opps
    assert runtime.metrics.scan_ms == 100
    assert runtime.metrics.last_error == ''
    assert runtime.calls[0][0] == 'unit_econ'
    assert runtime.calls[-1] == ('caq', {'opps': opps})


@pytest.mark.asyncio
async def test_run_postdecision_state_does_not_swallow_unexpected_publication_bug(monkeypatch):
    runtime = _RuntimePublishKeyError()
    monkeypatch.setattr(post_mod.time, 'perf_counter', lambda: 5.2)

    with pytest.raises(KeyError, match='unexpected publication bug'):
        await runtime._run_postdecision_analytics_state(
            opps=[SimpleNamespace(route_id='z')],
            rpc='rpc',
            regime_label='balanced',
            current_block=1,
            loop_started_at=5.0,
        )
