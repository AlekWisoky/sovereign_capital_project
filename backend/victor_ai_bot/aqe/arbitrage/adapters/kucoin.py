from __future__ import annotations

import aiohttp
from typing import Any, Mapping, Optional

_SAFE_KUCOIN_QUOTE_EXCEPTIONS = (aiohttp.ClientError, TimeoutError, TypeError, ValueError, AttributeError)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


from .base import ExchangeAdapter, VenueConfig
from ..models import MarketQuote, OrderBook, OrderBookLevel


class KuCoinSpotAdapter(ExchangeAdapter):
    """KuCoin spot adapter (public endpoints).

    Symbols use the KuCoin format, e.g. "BTC-USDT".
    """

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://api.kucoin.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        url = f"{self.base}/api/v1/market/orderbook/level1"
        async with s.get(url, params={"symbol": symbol}) as r:
            j = await r.json()
        data = _mapping(j).get("data") or {}
        bid = float(data.get("bestBid") or 0.0)
        ask = float(data.get("bestAsk") or 0.0)
        return MarketQuote(venue=self.name, product="spot", symbol=symbol, bid=bid, ask=ask, ts_ms=self._now_ms(), meta={"src": "kucoin_spot"})

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        s = await self._sess()
        # KuCoin provides L2 books; use level2_20 or level2_100 where possible.
        d = 20 if int(depth) <= 20 else 100
        url = f"{self.base}/api/v1/market/orderbook/level2_{d}"
        async with s.get(url, params={"symbol": symbol}) as r:
            j = await r.json()
        data = _mapping(j).get("data") or {}
        bids = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (data.get("bids") or [])[:d]]
        asks = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (data.get("asks") or [])[:d]]
        return OrderBook(bids=bids, asks=asks)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


class KuCoinPerpAdapter(ExchangeAdapter):
    """KuCoin Futures (public endpoints).

    KuCoin futures symbols are often like "XBTUSDTM".
    This adapter is best-effort: it pulls best bid/ask and attempts to include
    mark price + funding rate when available.
    """

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://api-futures.kucoin.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        bid = 0.0
        ask = 0.0
        mark = 0.0
        fr = 0.0
        # Ticker
        try:
            url = f"{self.base}/api/v1/ticker"
            async with s.get(url, params={"symbol": symbol}) as r:
                j = await r.json()
            data = _mapping(j).get("data") or {}
            bid = float(data.get("bestBidPrice") or data.get("bestBid") or 0.0)
            ask = float(data.get("bestAskPrice") or data.get("bestAsk") or 0.0)
            mark = float(data.get("markPrice") or 0.0)
        except _SAFE_KUCOIN_QUOTE_EXCEPTIONS:
            pass
        # Funding rate (best-effort)
        try:
            url2 = f"{self.base}/api/v1/contract/funding-rates"
            async with s.get(url2, params={"symbol": symbol}) as r2:
                j2 = await r2.json()
            data2 = _mapping(j2).get("data") or {}
            fr = float(data2.get("fundingRate") or 0.0)
        except _SAFE_KUCOIN_QUOTE_EXCEPTIONS:
            pass
        return MarketQuote(
            venue=self.name,
            product="futures",
            symbol=symbol,
            bid=float(bid),
            ask=float(ask),
            ts_ms=self._now_ms(),
            funding_rate=float(fr),
            mark_price=float(mark),
            meta={"src": "kucoin_perp"},
        )

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
