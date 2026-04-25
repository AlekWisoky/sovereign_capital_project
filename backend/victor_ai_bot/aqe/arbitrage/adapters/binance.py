from __future__ import annotations

import asyncio

import aiohttp
from typing import Optional

from .base import ExchangeAdapter, VenueConfig
from ..models import MarketQuote, OrderBook, OrderBookLevel


class BinanceSpotAdapter(ExchangeAdapter):
    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://api.binance.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        url = f"{self.base}/api/v3/ticker/bookTicker"
        async with s.get(url, params={"symbol": symbol}) as r:
            j = await r.json()
        bid = float(j.get("bidPrice") or 0.0)
        ask = float(j.get("askPrice") or 0.0)
        return MarketQuote(venue=self.name, product="spot", symbol=symbol, bid=bid, ask=ask, ts_ms=self._now_ms(), meta={"src": "binance_spot"})

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        s = await self._sess()
        url = f"{self.base}/api/v3/depth"
        d = max(5, min(1000, int(depth)))
        async with s.get(url, params={"symbol": symbol, "limit": d}) as r:
            j = await r.json()
        bids = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (j.get("bids") or [])[:d]]
        asks = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (j.get("asks") or [])[:d]]
        return OrderBook(bids=bids, asks=asks)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class BinanceUsdMFuturesAdapter(ExchangeAdapter):
    """Binance USD-M perpetual futures (public endpoints)."""

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://fapi.binance.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        # book ticker
        url = f"{self.base}/fapi/v1/ticker/bookTicker"
        async with s.get(url, params={"symbol": symbol}) as r:
            j = await r.json()
        bid = float(j.get("bidPrice") or 0.0)
        ask = float(j.get("askPrice") or 0.0)

        # funding / mark
        fr = 0.0
        mark = 0.0
        try:
            url2 = f"{self.base}/fapi/v1/premiumIndex"
            async with s.get(url2, params={"symbol": symbol}) as r2:
                j2 = await r2.json()
            fr = float(j2.get("lastFundingRate") or 0.0)
            mark = float(j2.get("markPrice") or 0.0)
        except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
            pass

        return MarketQuote(
            venue=self.name,
            product="futures",
            symbol=symbol,
            bid=bid,
            ask=ask,
            ts_ms=self._now_ms(),
            funding_rate=fr,
            mark_price=mark,
            meta={"src": "binance_usdm"},
        )

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        s = await self._sess()
        url = f"{self.base}/fapi/v1/depth"
        d = max(5, min(1000, int(depth)))
        async with s.get(url, params={"symbol": symbol, "limit": d}) as r:
            j = await r.json()
        bids = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (j.get("bids") or [])[:d]]
        asks = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (j.get("asks") or [])[:d]]
        return OrderBook(bids=bids, asks=asks)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
