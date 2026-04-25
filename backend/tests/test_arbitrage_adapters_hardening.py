from __future__ import annotations

import aiohttp
import pytest

from victor_ai_bot.aqe.arbitrage.adapters.base import VenueConfig
from victor_ai_bot.aqe.arbitrage.adapters.binance import BinanceUsdMFuturesAdapter
from victor_ai_bot.aqe.arbitrage.adapters.bybit import BybitLinearPerpAdapter
from victor_ai_bot.aqe.arbitrage.adapters.kraken import KrakenSpotAdapter


class FakeResponse:
    def __init__(self, payload=None, *, json_exc=None):
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
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.mark.asyncio
async def test_binance_futures_quote_tolerates_client_error_for_premium_index():
    cfg = VenueConfig(name='binance_usdm', product='futures')
    adapter = BinanceUsdMFuturesAdapter(cfg)
    adapter._session = FakeSession([
        FakeResponse({'bidPrice': '100.0', 'askPrice': '101.0'}),
        aiohttp.ClientError('premium index unavailable'),
    ])

    quote = await adapter.fetch_quote(symbol='BTCUSDT')

    assert quote.bid == 100.0
    assert quote.ask == 101.0
    assert quote.funding_rate == 0.0
    assert quote.mark_price == 0.0


@pytest.mark.asyncio
async def test_binance_futures_quote_does_not_swallow_unexpected_runtime_error():
    cfg = VenueConfig(name='binance_usdm', product='futures')
    adapter = BinanceUsdMFuturesAdapter(cfg)
    adapter._session = FakeSession([
        FakeResponse({'bidPrice': '100.0', 'askPrice': '101.0'}),
        RuntimeError('unexpected premium index failure'),
    ])

    with pytest.raises(RuntimeError):
        await adapter.fetch_quote(symbol='BTCUSDT')


@pytest.mark.asyncio
async def test_bybit_quote_handles_non_list_result_payload():
    cfg = VenueConfig(name='bybit_linear', product='futures')
    adapter = BybitLinearPerpAdapter(cfg)
    adapter._session = FakeSession([
        FakeResponse({'result': {'list': {'oops': 'not-a-list'}}}),
    ])

    quote = await adapter.fetch_quote(symbol='BTCUSDT')

    assert quote.bid == 0.0
    assert quote.ask == 0.0
    assert quote.funding_rate == 0.0


@pytest.mark.asyncio
async def test_kraken_quote_handles_non_mapping_result_payload():
    cfg = VenueConfig(name='kraken_spot', product='spot')
    adapter = KrakenSpotAdapter(cfg)
    adapter._session = FakeSession([
        FakeResponse({'result': ['not-a-mapping']}),
    ])

    quote = await adapter.fetch_quote(symbol='XBTUSD')

    assert quote.bid == 0.0
    assert quote.ask == 0.0
