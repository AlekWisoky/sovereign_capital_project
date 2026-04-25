from __future__ import annotations

import aiohttp
from typing import Any, Mapping, Optional

_SAFE_OKX_QUOTE_EXCEPTIONS = (aiohttp.ClientError, TimeoutError, TypeError, ValueError, AttributeError)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_data_item(payload: Any) -> Mapping[str, Any]:
    data = _mapping(payload).get("data")
    if isinstance(data, list) and data:
        return _mapping(data[0])
    return {}


from .base import ExchangeAdapter, VenueConfig
from ..models import MarketQuote, OrderBook, OrderBookLevel


class OKXSwapAdapter(ExchangeAdapter):
    """OKX swap/perpetual (public endpoints)."""

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://www.okx.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        # OKX uses instId; assume symbol provided as instId (e.g., BTC-USDT-SWAP)
        s = await self._sess()
        url = f"{self.base}/api/v5/market/ticker"
        async with s.get(url, params={"instId": symbol}) as r:
            j = await r.json()
        item = _first_data_item(j)
        bid = float(item.get("bidPx") or 0.0)
        ask = float(item.get("askPx") or 0.0)
        mark = float(item.get("last") or 0.0)

        fr = 0.0
        try:
            url2 = f"{self.base}/api/v5/public/funding-rate"
            async with s.get(url2, params={"instId": symbol}) as r2:
                j2 = await r2.json()
            it2 = _first_data_item(j2)
            fr = float(it2.get("fundingRate") or 0.0)
        except _SAFE_OKX_QUOTE_EXCEPTIONS:
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
            meta={"src": "okx_swap"},
        )

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        s = await self._sess()
        url = f"{self.base}/api/v5/market/books"
        d = max(5, min(50, int(depth)))
        async with s.get(url, params={"instId": symbol, "sz": d}) as r:
            j = await r.json()
        item = (j.get("data") or [None])[0] or {}
        bids = [OrderBookLevel(price=float(x[0]), qty=float(x[1])) for x in (item.get("bids") or [])[:d]]
        asks = [OrderBookLevel(price=float(x[0]), qty=float(x[1])) for x in (item.get("asks") or [])[:d]]
        return OrderBook(bids=bids, asks=asks)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
