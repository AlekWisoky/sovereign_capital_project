import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import victor_ai_bot.arb_engine as arb_engine_module
from victor_ai_bot.arb_engine import Edge, quote_edge, requote_opportunity, _pool_keys_for_leg
from victor_ai_bot.cache import PerBlockCache
from victor_ai_bot.models import Opportunity, Route, RouteLeg

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot'


class _Cfg(SimpleNamespace):
    pass


def _cfg(*, dynamic: bool = False):
    return _Cfg(
        chain=SimpleNamespace(univ3_quoter_v2='0xquoter', balancer_vault='0xvault', name='eth'),
        safety=SimpleNamespace(
            dynamic_slippage_enabled=dynamic,
            dynamic_slippage_probe_bps=100,
            dynamic_slippage_impact_mult=1.5,
            dynamic_slippage_min_bps=10,
            dynamic_slippage_max_bps=200,
        ),
    )


def _opp() -> Opportunity:
    return Opportunity(
        id='opp-1',
        chain='eth',
        strategy='two-leg:univ3->univ3',
        expected_profit_raw='10',
        expected_profit_usd='0',
        route=Route(
            legs=[
                RouteLeg(
                    dex='univ3',
                    venue='0xrouter',
                    token_in='0x1111111111111111111111111111111111111111',
                    token_out='0x2222222222222222222222222222222222222222',
                    amount_in='100',
                    min_out='110',
                    data='0x',
                )
            ]
        ),
        min_outs=['110'],
        route_id='route-1',
        meta={},
    )


@pytest.mark.asyncio
async def test_quote_edge_invalid_curve_params_are_safely_contained():
    edge = Edge(
        'curve',
        '0xpool',
        '0x1111111111111111111111111111111111111111',
        '0x2222222222222222222222222222222222222222',
        {'i': 'bad', 'j': 1},
    )
    out = await quote_edge(object(), _cfg(), PerBlockCache(), edge, 100)
    assert out is None


@pytest.mark.asyncio
async def test_quote_edge_programmer_bug_is_not_swallowed(monkeypatch):
    async def boom(*args, **kwargs):
        raise NameError('quote bug')

    monkeypatch.setattr(arb_engine_module, 'quote_exact_input_single', boom)
    edge = Edge(
        'univ3',
        '0xrouter',
        '0x1111111111111111111111111111111111111111',
        '0x2222222222222222222222222222222222222222',
        {'fee': 3000},
    )

    with pytest.raises(NameError):
        await quote_edge(object(), _cfg(), PerBlockCache(), edge, 100)


def test_pool_key_falls_back_for_malformed_curve_metadata():
    key = _pool_keys_for_leg(
        'curve',
        '0xAAAA',
        '0xBBBB',
        {'i': 'bad', 'j': 1},
        '0x',
    )
    assert key == 'curve:0xaaaa:0xbbbb:i=bad,j=1'


@pytest.mark.asyncio
async def test_requote_dynamic_slippage_value_error_is_safely_contained(monkeypatch):
    calls = {'count': 0}

    async def fake_quote_edge(rpc, cfg, cache, e, amount):
        calls['count'] += 1
        if calls['count'] == 1:
            return 120, {'fee': 3000}
        raise ValueError('probe failed')

    monkeypatch.setattr(arb_engine_module, 'quote_edge', fake_quote_edge)

    opp = await requote_opportunity(
        object(),
        _cfg(dynamic=True),
        PerBlockCache(),
        _opp(),
        new_amount_in=100,
        slippage_bps=50,
    )

    assert opp is not None
    assert opp.meta['slippage_model']['impact_bps_per_leg'] == [0]
    assert opp.meta['slippage_model']['applied_bps_per_leg'] == [50]
    assert opp.route.legs[0].min_out == '119'


@pytest.mark.asyncio
async def test_requote_dynamic_slippage_programmer_bug_propagates(monkeypatch):
    calls = {'count': 0}

    async def fake_quote_edge(rpc, cfg, cache, e, amount):
        calls['count'] += 1
        if calls['count'] == 1:
            return 120, {'fee': 3000}
        raise NameError('probe logic bug')

    monkeypatch.setattr(arb_engine_module, 'quote_edge', fake_quote_edge)

    with pytest.raises(NameError):
        await requote_opportunity(
            object(),
            _cfg(dynamic=True),
            PerBlockCache(),
            _opp(),
            new_amount_in=100,
            slippage_bps=50,
        )


def test_arb_engine_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'arb_engine.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            broad.append('bare except')
            continue
        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
            broad.append('except Exception')
    assert broad == []
