from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_services.runtime_engine_facade as engine_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_engine_facade import RuntimeEngineFacade

EXTRACTED_METHODS = {
    '_engine_quotes',
    '_engine_funding_rows',
    '_engine_dex_inputs',
    '_engine_bridge_spreads',
    '_engine_bridge_quotes',
    '_engine_chain_inventory',
    '_engine_meta_candidates',
    '_scan_engine_opportunities',
}


class _Arbitrage:
    def state(self):
        return {
            'quotes': [
                {'symbol': 'ETH', 'product': 'spot'},
                {'symbol': 'BTC', 'product': 'perp', 'funding_rate': 0.0005},
                {'symbol': 'SOL', 'product': 'futures', 'funding_rate': -0.0002},
            ]
        }


class _Meta:
    def state(self):
        return {'last_candidates': [{'id': 'cand-1'}, {'id': 'cand-2'}]}


class _EngineService:
    def __init__(self):
        self.calls = []

    def scan(self, **kwargs):
        self.calls.append(kwargs)
        return {'items': [{'id': 'fresh'}], 'capabilities': {'mev': True}, 'summary': {'engines': ['fresh']}}


class _EngineServiceValueError(_EngineService):
    def scan(self, **kwargs):
        raise ValueError('bad engine scan state')


class _EngineServiceRuntimeError(_EngineService):
    def scan(self, **kwargs):
        raise RuntimeError('unexpected engine scan bug')


class _Runtime(RuntimeEngineFacade):
    def __init__(self, engine_service=None):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name='ethereum', chain_id=1))
        self._arbitrage = _Arbitrage()
        self._engine_service = engine_service or _EngineService()
        self._meta = _Meta()
        self._spread_opps = [
            SimpleNamespace(symbol='ETH', meta={'dex_price': 3200.0, 'dex_depth_usd': 250000.0}),
            SimpleNamespace(
                symbol='ARB',
                opp_type='cross_chain',
                spread=0.031,
                volume=1500.0,
                meta={'src_chain': 'ethereum', 'dst_chain': 'arbitrum'},
            ),
            SimpleNamespace(symbol='BROKEN', opp_type='cross_chain', meta=None, spread=object(), volume=1),
        ]
        self._engine_last = {'items': [{'id': 'stale'}], 'capabilities': {}, 'summary': {'engines': ['stale']}}


def test_runtime_bundle_inherits_engine_facade():
    assert issubclass(RuntimeBundle, RuntimeEngineFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_engine_helper_methods_preserve_input_shaping():
    runtime = _Runtime()

    assert runtime._engine_quotes()[0]['symbol'] == 'ETH'
    assert [row['symbol'] for row in runtime._engine_funding_rows(runtime._engine_quotes())] == ['BTC', 'SOL']

    dex_prices, dex_depths = runtime._engine_dex_inputs()
    assert dex_prices == {'ETH': 3200.0}
    assert dex_depths == {'ETH': 250000.0}

    bridge_spreads = runtime._engine_bridge_spreads()
    assert bridge_spreads == [
        {
            'src_chain': 'ethereum',
            'dst_chain': 'arbitrum',
            'symbol': 'ARB',
            'spread_ratio': 0.031,
            'capital_required_usd': 1500.0,
            'class': 'bridge_adjusted_spread_arb',
            'chain_id': 1,
        }
    ]
    assert runtime._engine_chain_inventory({'capital_engine': {'deployable_bankroll_wei': int(3e18), 'experimental_bankroll_wei': int(2e18)}}) == {
        'ethereum': 3.0,
        'arbitrum': 2.0,
    }
    assert runtime._engine_meta_candidates() == [{'id': 'cand-1'}, {'id': 'cand-2'}]


def test_scan_engine_opportunities_delegates_to_engine_service(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(engine_mod, 'is_public_mode', lambda: True)
    monkeypatch.setattr(engine_mod, 'public_broadcast_override_enabled', lambda: False)

    ok = runtime._scan_engine_opportunities(
        regime_label='balanced',
        mev_state={'risk': 0.2},
        base_opportunities=[{'id': 'base-1'}],
        treasury_state={'capital_engine': {'deployable_bankroll_wei': int(5e18), 'experimental_bankroll_wei': int(1e18)}},
    )

    assert ok is True
    assert runtime._engine_last['items'][0]['id'] == 'fresh'
    call = runtime._engine_service.calls[0]
    assert call['quotes'][0]['symbol'] == 'ETH'
    assert [row['symbol'] for row in call['funding_rows']] == ['BTC', 'SOL']
    assert call['dex_prices'] == {'ETH': 3200.0}
    assert call['bridge_spreads'][0]['symbol'] == 'ARB'
    assert call['bridge_quotes']['ethereum->arbitrum']['bridge'] == 'canonical'
    assert call['chain_inventory'] == {'ethereum': 5.0, 'arbitrum': 1.0}
    assert call['meta_candidates'] == [{'id': 'cand-1'}, {'id': 'cand-2'}]
    assert call['mev_state'] == {'risk': 0.2}
    assert call['base_opportunities'] == [{'id': 'base-1'}]
    assert call['public_mode'] is True


def test_scan_engine_opportunities_swallows_expected_local_failure():
    runtime = _Runtime(engine_service=_EngineServiceValueError())

    ok = runtime._scan_engine_opportunities(
        regime_label='balanced',
        mev_state={},
        base_opportunities=[],
        treasury_state={},
    )

    assert ok is False
    assert runtime._engine_last == {'items': [{'id': 'stale'}], 'capabilities': {}, 'summary': {'engines': ['stale']}}


def test_scan_engine_opportunities_does_not_swallow_unexpected_bug():
    runtime = _Runtime(engine_service=_EngineServiceRuntimeError())

    with pytest.raises(RuntimeError, match='unexpected engine scan bug'):
        runtime._scan_engine_opportunities(
            regime_label='balanced',
            mev_state={},
            base_opportunities=[],
            treasury_state={},
        )
