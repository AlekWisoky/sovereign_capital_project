from __future__ import annotations

import pytest

from victor_ai_bot.aqe.arbitrage.adapters.base import VenueConfig
from victor_ai_bot.aqe.arbitrage.adapters.okx import OKXSwapAdapter
from victor_ai_bot.aqe.arbitrage.adapters.kucoin import KuCoinPerpAdapter


class FakeResponse:
    def __init__(self, payload=None, json_exc=None):
        self._payload = payload
        self._json_exc = json_exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.closed = False

    def get(self, url, params=None):
        if not self._responses:
            raise AssertionError('unexpected get')
        return self._responses.pop(0)


class BadFloat:
    def __float__(self):
        raise KeyboardInterrupt('boom')


@pytest.mark.asyncio
async def test_okx_expected_funding_failure_degrades():
    adapter = OKXSwapAdapter(VenueConfig(name='okx', product='futures'))
    adapter._session = FakeSession([
        FakeResponse({'data': [{'bidPx': '1.0', 'askPx': '2.0', 'last': '1.5'}]}),
        FakeResponse(json_exc=ValueError('bad funding payload')),
    ])
    q = await adapter.fetch_quote(symbol='BTC-USDT-SWAP')
    assert q.bid == 1.0
    assert q.ask == 2.0
    assert q.mark_price == 1.5
    assert q.funding_rate == 0.0


@pytest.mark.asyncio
async def test_okx_unexpected_funding_bug_not_swallowed():
    adapter = OKXSwapAdapter(VenueConfig(name='okx', product='futures'))
    adapter._session = FakeSession([
        FakeResponse({'data': [{'bidPx': '1.0', 'askPx': '2.0', 'last': '1.5'}]}),
        FakeResponse({'data': [{'fundingRate': BadFloat()}]}),
    ])
    with pytest.raises(KeyboardInterrupt):
        await adapter.fetch_quote(symbol='BTC-USDT-SWAP')


@pytest.mark.asyncio
async def test_kucoin_expected_ticker_and_funding_failures_degrade():
    adapter = KuCoinPerpAdapter(VenueConfig(name='kucoin', product='futures'))
    adapter._session = FakeSession([
        FakeResponse(json_exc=ValueError('bad ticker payload')),
        FakeResponse(json_exc=TypeError('bad funding payload')),
    ])
    q = await adapter.fetch_quote(symbol='XBTUSDTM')
    assert q.bid == 0.0
    assert q.ask == 0.0
    assert q.mark_price == 0.0
    assert q.funding_rate == 0.0


@pytest.mark.asyncio
async def test_kucoin_unexpected_ticker_bug_not_swallowed():
    adapter = KuCoinPerpAdapter(VenueConfig(name='kucoin', product='futures'))
    adapter._session = FakeSession([
        FakeResponse({'data': {'bestBidPrice': BadFloat(), 'bestAskPrice': '2.0', 'markPrice': '1.0'}}),
    ])
    with pytest.raises(KeyboardInterrupt):
        await adapter.fetch_quote(symbol='XBTUSDTM')
