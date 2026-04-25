from __future__ import annotations

import sys
import types

import pytest

from victor_ai_bot.aqe.connectors.dex_adapters import BalancerAdapter, CurveAdapter, UniswapV3Adapter
from victor_ai_bot.aqe.connectors.dex import DEXQuote


class BadInt:
    def __int__(self):
        raise KeyboardInterrupt('boom')


@pytest.mark.asyncio
async def test_univ3_expected_quote_failure_degrades(monkeypatch):
    mod = types.SimpleNamespace()

    async def quote_exact_input_single(**kwargs):
        raise ValueError('bad quote')

    mod.quote_exact_input_single = quote_exact_input_single
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.quote_univ3', mod)

    adapter = UniswapV3Adapter(chain='eth', rpc=object(), quoter_v2='0xq')
    q = await adapter.quote('a', 'b', 1)
    assert q.ok is False
    assert q.amount_out == 0
    assert 'bad quote' in (q.meta or {}).get('error', '')


@pytest.mark.asyncio
async def test_univ3_unexpected_quote_bug_not_swallowed(monkeypatch):
    mod = types.SimpleNamespace()

    async def quote_exact_input_single(**kwargs):
        return types.SimpleNamespace(amount_out=BadInt(), gas_estimate=1)

    mod.quote_exact_input_single = quote_exact_input_single
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.quote_univ3', mod)

    adapter = UniswapV3Adapter(chain='eth', rpc=object(), quoter_v2='0xq')
    with pytest.raises(KeyboardInterrupt):
        await adapter.quote('a', 'b', 1)


@pytest.mark.asyncio
async def test_curve_expected_quote_failure_degrades(monkeypatch):
    mod = types.SimpleNamespace()

    async def quote_curve(*args, **kwargs):
        raise RuntimeError('curve unavailable')

    mod.quote_curve = quote_curve
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.quote_curve', mod)

    adapter = CurveAdapter(chain='eth', rpc=object(), pool='0xp', i=0, j=1)
    q = await adapter.quote('a', 'b', 1)
    assert q == DEXQuote(ok=False, amount_out=0, meta={'error': 'curve unavailable'})


@pytest.mark.asyncio
async def test_balancer_expected_quote_failure_degrades(monkeypatch):
    mod = types.SimpleNamespace()

    async def quote_balancer_given_in(*args, **kwargs):
        raise OSError('io bad')

    mod.quote_balancer_given_in = quote_balancer_given_in
    monkeypatch.setitem(sys.modules, 'victor_ai_bot.quote_balancer', mod)

    adapter = BalancerAdapter(chain='eth', rpc=object(), vault='0xv', pool_id='0xp')
    q = await adapter.quote('a', 'b', 1)
    assert q.ok is False
    assert q.amount_out == 0
    assert 'io bad' in (q.meta or {}).get('error', '')
