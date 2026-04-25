from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution_capture.envelope import (
    _route_family,
    _safe_float,
    build_opportunity_envelope,
)


class BadFloat:
    def __float__(self):
        raise RuntimeError('boom')


class BadLegs:
    def __iter__(self):
        raise RuntimeError('boom')


class BadVenue:
    @property
    def venue(self):
        raise RuntimeError('boom')


class MissingTokenOut:
    @property
    def token_out(self):
        raise AttributeError('missing')

    token_in = 'A'
    venue = 'uni'


class BadTokenOut:
    @property
    def token_out(self):
        raise RuntimeError('boom')

    token_in = 'A'
    venue = 'uni'



def _opp(*, legs=None, meta=None, strategy='flash_arb'):
    return SimpleNamespace(
        id='opp-1',
        route_id='route-1',
        strategy=strategy,
        expected_profit_usd=12.0,
        meta=meta or {},
        route=SimpleNamespace(legs=legs or []),
    )



def test_safe_float_expected_coercion_failure_degrades_safely():
    assert _safe_float('nope', 1.25) == 1.25



def test_safe_float_unexpected_bug_is_not_swallowed():
    with pytest.raises(RuntimeError, match='boom'):
        _safe_float(BadFloat(), 1.0)



def test_route_family_expected_shape_failure_degrades_to_strategy_only():
    opp = _opp(legs=123, strategy='funding')
    assert _route_family(opp) == 'funding'



def test_route_family_unexpected_bug_is_not_swallowed():
    opp = _opp(legs=[BadVenue()])
    with pytest.raises(RuntimeError, match='boom'):
        _route_family(opp)



def test_build_opportunity_envelope_expected_token_path_shape_failure_degrades():
    opp = _opp(legs=[MissingTokenOut()], meta={'margin_ratio': '0.05'})
    env = build_opportunity_envelope(opp, chain_id=1)
    assert env.token_path == ['A', '']
    assert env.route_family == 'flash_arb|uni|A>A'


def test_build_opportunity_envelope_surfaces_strategy_family_in_metadata():
    opp = _opp(meta={'strategy_family': 'flash_arb'})
    env = build_opportunity_envelope(opp, chain_id=1)
    assert env.metadata['strategy_family'] == 'flash_arb'



def test_build_opportunity_envelope_unexpected_leg_iteration_bug_is_not_swallowed():
    opp = _opp(legs=BadLegs())
    with pytest.raises(RuntimeError, match='boom'):
        build_opportunity_envelope(opp, chain_id=1)


def test_build_opportunity_envelope_unexpected_token_path_bug_is_not_swallowed():
    opp = _opp(legs=[BadTokenOut()], meta={'margin_ratio': '0.05'})
    with pytest.raises(RuntimeError, match='boom'):
        build_opportunity_envelope(opp, chain_id=1)
