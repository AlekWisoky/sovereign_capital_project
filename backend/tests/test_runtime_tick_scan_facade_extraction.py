from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_tick_scan_facade import RuntimeTickScanFacade

EXTRACTED_METHODS = {
    '_run_tick_scan_pipeline',
}


class _Runtime(RuntimeTickScanFacade):
    def __init__(self):
        self.calls = []

    def _resolve_amount_in(self):
        self.calls.append(('resolve_amount_in', {}))
        return 42

    async def _scan_primary_opportunities(self, rpc, *, current_block: int, amount_in: int):
        self.calls.append(('scan_primary', {'rpc': rpc, 'current_block': current_block, 'amount_in': amount_in}))
        return [SimpleNamespace(id='opp-1')]

    async def _safe_annotate_can_execute(self, rpc, opps):
        self.calls.append(('annotate_can_execute', {'rpc': rpc, 'opps': opps}))

    async def _gas_signal_snapshot(self, rpc):
        self.calls.append(('gas_signals', {'rpc': rpc}))
        return {'basefee_gwei': 11.0, 'priority_gwei': 2.0}

    def _market_signal_snapshot(self, opps):
        self.calls.append(('market_signals', {'opps': opps}))
        return {
            'mev_risk': 0.2,
            'pending_rate': 1.5,
            'avg_margin_ratio': 0.03,
            'volatility_proxy': 0.4,
        }

    def _behave_regime_state(self, **kwargs):
        self.calls.append(('behave_regime', dict(kwargs)))
        return {'regime_label': 'volatile'}

    def _resolve_market_regime(self, **kwargs):
        self.calls.append(('resolve_market_regime', dict(kwargs)))
        return {'regime_label': 'volatile', 'market_regime': {'label': 'volatile'}}

    def _apply_treasury_guidance(self, **kwargs):
        self.calls.append(('treasury_guidance', dict(kwargs)))
        return {'treasury_state': {'cap': 1.5}, 'behave_state': {'regime_label': 'volatile', 'overlay': 'fast'}}

    def _run_predecision_additive_state(self, **kwargs):
        self.calls.append(('predecision_state', dict(kwargs)))
        return {'mev_snap': {'danger': 0.7}}

    async def _run_decision_finalize(self, **kwargs):
        self.calls.append(('decision_finalize', dict(kwargs)))
        return SimpleNamespace(action='trade')


class _RuntimeExplodes(_Runtime):
    async def _scan_primary_opportunities(self, rpc, *, current_block: int, amount_in: int):
        raise KeyError('unexpected scan bug')


def test_runtime_bundle_inherits_tick_scan_facade():
    assert issubclass(RuntimeBundle, RuntimeTickScanFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


@pytest.mark.asyncio
async def test_tick_scan_pipeline_preserves_order_and_outputs():
    runtime = _Runtime()
    rpc = object()

    result = await runtime._run_tick_scan_pipeline(
        rpc=rpc,
        current_block=123,
        loop_started_at=8.5,
    )

    assert [name for name, _ in runtime.calls] == [
        'resolve_amount_in',
        'scan_primary',
        'annotate_can_execute',
        'gas_signals',
        'market_signals',
        'behave_regime',
        'resolve_market_regime',
        'treasury_guidance',
        'predecision_state',
        'decision_finalize',
    ]
    assert result['regime_label'] == 'volatile'
    assert result['treasury_state'] == {'cap': 1.5}
    assert result['mev_snap'] == {'danger': 0.7}
    assert result['decision'].action == 'trade'
    assert runtime.calls[1][1]['amount_in'] == 42
    assert runtime.calls[-1][1]['current_block'] == 123
    assert runtime.calls[-1][1]['loop_started_at'] == 8.5


@pytest.mark.asyncio
async def test_tick_scan_pipeline_does_not_swallow_unexpected_bug():
    runtime = _RuntimeExplodes()
    with pytest.raises(KeyError, match='unexpected scan bug'):
        await runtime._run_tick_scan_pipeline(
            rpc=object(),
            current_block=7,
            loop_started_at=1.0,
        )
