from __future__ import annotations

import aiohttp
from typing import Optional

from .base import ExchangeAdapter, VenueConfig
from ..models import MarketQuote, OrderBook, OrderBookLevel


class BybitLinearPerpAdapter(ExchangeAdapter):
    """Bybit linear perpetual futures (public endpoints).

    NOTE: Bybit API schemas evolve. This adapter is defensive:
    - if a field is missing, defaults are used.
    """

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://api.bybit.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        url = f"{self.base}/v5/market/tickers"
        async with s.get(url, params={"category": "linear", "symbol": symbol}) as r:
            j = await r.json()
        lst = (((j or {}).get("result") or {}).get("list") or [])
        if not isinstance(lst, list):
            lst = []
        item = lst[0] if lst and isinstance(lst[0], dict) else None
        bid = float((item or {}).get("bid1Price") or 0.0)
        ask = float((item or {}).get("ask1Price") or 0.0)
        fr = float((item or {}).get("fundingRate") or 0.0)
        mark = float((item or {}).get("markPrice") or 0.0)
        idx = float((item or {}).get("indexPrice") or 0.0)
        return MarketQuote(
            venue=self.name,
            product="futures",
            symbol=symbol,
            bid=bid,
            ask=ask,
            ts_ms=self._now_ms(),
            funding_rate=fr,
            mark_price=mark,
            index_price=idx,
            meta={"src": "bybit_linear"},
        )

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        s = await self._sess()
        url = f"{self.base}/v5/market/orderbook"
        d = max(5, min(50, int(depth)))
        async with s.get(url, params={"category": "linear", "symbol": symbol, "limit": d}) as r:
            j = await r.json()
        ob = ((j or {}).get("result") or {})
        bids = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (ob.get("b") or [])[:d]]
        asks = [OrderBookLevel(price=float(p), qty=float(q)) for p, q in (ob.get("a") or [])[:d]]
        return OrderBook(bids=bids, asks=asks)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
