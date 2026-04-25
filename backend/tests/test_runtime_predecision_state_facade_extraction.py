from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_predecision_state_facade as pre_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_predecision_state_facade import RuntimePredecisionStateFacade

EXTRACTED_METHODS = {
    '_predecision_bus_snapshot',
    '_run_predecision_additive_state',
}


class _Runtime(RuntimePredecisionStateFacade):
    def __init__(self):
        self.calls = []
        self._pending = [object(), object()]

    def _refresh_unified_feature_bus(self):
        self.calls.append(('refresh_unified', None))
        return True

    def _run_spread_scan(self, **kwargs):
        self.calls.append(('spread', dict(kwargs)))
        return True

    def _run_agent_consensus_gate(self, **kwargs):
        self.calls.append(('consensus', dict(kwargs)))
        return {'ok': True}

    def _apply_score_overlays(self, **kwargs):
        self.calls.append(('overlay', dict(kwargs)))
        return None

    def _observe_blockspace(self, **kwargs):
        self.calls.append(('blockspace', dict(kwargs)))
        return True


class _RuntimeValueError(_Runtime):
    def _run_spread_scan(self, **kwargs):
        raise ValueError('bad spread state')


class _RuntimeKeyError(_Runtime):
    def _run_spread_scan(self, **kwargs):
        raise KeyError('unexpected predecision bug')


def test_runtime_bundle_inherits_predecision_state_facade():
    assert issubclass(RuntimeBundle, RuntimePredecisionStateFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_run_predecision_additive_state_preserves_refresh_snapshot_and_calls(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(pre_mod.BUS, 'snapshot', lambda: {'mev': {'pending_rate': 0.4}, 'dex': {'count': 7}})

    result = runtime._run_predecision_additive_state(
        opps=[SimpleNamespace(id='a')],
        regime_label='balanced',
        behave_state={'enabled': True},
        treasury_state={'borrow_mult_target_cap': 1.25},
        basefee_gwei=11.0,
        priority_gwei=1.2,
        mev_risk=0.3,
        pending_rate=0.4,
        current_block=77,
    )

    assert result == {
        'bus_snap': {'mev': {'pending_rate': 0.4}, 'dex': {'count': 7}},
        'mev_snap': {'pending_rate': 0.4},
    }
    assert runtime.calls[0] == ('refresh_unified', None)
    assert runtime.calls[1] == (
        'spread',
        {
            'regime_label': 'balanced',
            'mev_risk': 0.3,
            'pending_rate': 0.4,
            'treasury_state': {'borrow_mult_target_cap': 1.25},
        },
    )
    consensus = runtime.calls[2]
    assert consensus[0] == 'consensus'
    assert consensus[1]['bus_snap'] == {'mev': {'pending_rate': 0.4}, 'dex': {'count': 7}}
    assert consensus[1]['mev_snap'] == {'pending_rate': 0.4}
    overlay = runtime.calls[3]
    assert overlay[0] == 'overlay'
    assert overlay[1]['basefee_gwei'] == 11.0
    blockspace = runtime.calls[4]
    assert blockspace == (
        'blockspace',
        {
            'block_number': 77,
            'basefee_gwei': 11.0,
            'priority_gwei': 1.2,
            'pending_txs': 2,
            'mev_risk': 0.3,
        },
    )


def test_run_predecision_additive_state_is_operator_safe_on_typed_failure(monkeypatch):
    runtime = _RuntimeValueError()
    monkeypatch.setattr(pre_mod.BUS, 'snapshot', lambda: {'mev': {'pending_rate': 0.4}})

    result = runtime._run_predecision_additive_state(
        opps=[],
        regime_label='balanced',
        behave_state=None,
        treasury_state=None,
        basefee_gwei=0.0,
        priority_gwei=0.0,
        mev_risk=0.0,
        pending_rate=0.0,
        current_block=1,
    )

    assert result == {'bus_snap': {}, 'mev_snap': {}}


def test_run_predecision_additive_state_does_not_swallow_unexpected_bug(monkeypatch):
    runtime = _RuntimeKeyError()
    monkeypatch.setattr(pre_mod.BUS, 'snapshot', lambda: {'mev': {'pending_rate': 0.4}})

    with pytest.raises(KeyError, match='unexpected predecision bug'):
        runtime._run_predecision_additive_state(
            opps=[],
            regime_label='balanced',
            behave_state=None,
            treasury_state=None,
            basefee_gwei=0.0,
            priority_gwei=0.0,
            mev_risk=0.0,
            pending_rate=0.0,
            current_block=1,
        )
