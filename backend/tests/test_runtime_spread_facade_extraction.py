from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_spread_facade import RuntimeSpreadFacade

EXTRACTED_METHODS = {
    '_spread_quotes',
    '_spread_scan_state',
    '_run_spread_scan',
}


class _Arbitrage:
    def state(self):
        return {
            'quotes': [
                {'symbol': 'ETH', 'venue': 'binance', 'bid': 100.0, 'ask': 101.0},
                {'symbol': 'ETH', 'venue': 'coinbase', 'bid': 102.0, 'ask': 103.0},
            ]
        }


class _SpreadOpp:
    def __init__(self, opp_id: str):
        self.opp_id = opp_id

    def as_dict(self):
        return {'opp_id': self.opp_id}


class _SpreadEngine:
    def __init__(self):
        self.calls = []

    def scan(self, state):
        self.calls.append(state)
        return [_SpreadOpp('spread-1')]


class _SpreadEngineValueError(_SpreadEngine):
    def scan(self, state):
        raise ValueError('bad spread state')


class _SpreadEngineKeyError(_SpreadEngine):
    def scan(self, state):
        raise KeyError('unexpected spread bug')


class _Runtime(RuntimeSpreadFacade):
    def __init__(self, spread_engine=None):
        self._arbitrage = _Arbitrage()
        self._spread_engine = spread_engine or _SpreadEngine()
        self._spread_opps = []
        self._spread_last = {}


def test_runtime_bundle_inherits_spread_facade():
    assert issubclass(RuntimeBundle, RuntimeSpreadFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_spread_scan_state_preserves_input_shaping():
    runtime = _Runtime()

    quotes = runtime._spread_quotes()
    assert quotes[0]['symbol'] == 'ETH'

    state = runtime._spread_scan_state(
        regime_label='balanced',
        mev_risk=0.2,
        pending_rate=0.3,
        treasury_state={'aggressiveness': {'aggressiveness_level': 'HIGH'}},
    )
    assert state == {
        'quotes': quotes,
        'regime': 'balanced',
        'stress': {'mev': 0.2, 'pending_rate': 0.3},
        'aggressiveness_level': 'HIGH',
    }


def test_run_spread_scan_updates_spread_state_and_publication():
    runtime = _Runtime()

    ok = runtime._run_spread_scan(
        regime_label='balanced',
        mev_risk=0.1,
        pending_rate=0.05,
        treasury_state={'aggressiveness': {'aggressiveness_level': 'MEDIUM'}},
    )

    assert ok is True
    assert runtime._spread_engine.calls[0]['regime'] == 'balanced'
    assert runtime._spread_engine.calls[0]['stress'] == {'mev': 0.1, 'pending_rate': 0.05}
    assert runtime._spread_engine.calls[0]['aggressiveness_level'] == 'MEDIUM'
    assert len(runtime._spread_opps) == 1
    assert runtime._spread_last['regime'] == 'balanced'
    assert runtime._spread_last['count'] == 1
    assert runtime._spread_last['ts'] > 0


def test_run_spread_scan_swallows_expected_local_failure():
    runtime = _Runtime(spread_engine=_SpreadEngineValueError())

    ok = runtime._run_spread_scan(
        regime_label='balanced',
        mev_risk=0.0,
        pending_rate=0.0,
        treasury_state={},
    )

    assert ok is False
    assert runtime._spread_opps == []
    assert runtime._spread_last == {}


def test_run_spread_scan_does_not_swallow_unexpected_bug():
    runtime = _Runtime(spread_engine=_SpreadEngineKeyError())

    with pytest.raises(KeyError, match='unexpected spread bug'):
        runtime._run_spread_scan(
            regime_label='balanced',
            mev_risk=0.0,
            pending_rate=0.0,
            treasury_state={},
        )
