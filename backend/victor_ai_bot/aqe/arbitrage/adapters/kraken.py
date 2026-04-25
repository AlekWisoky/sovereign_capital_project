from __future__ import annotations

import aiohttp
from typing import Optional

from .base import ExchangeAdapter, VenueConfig
from ..models import MarketQuote


class KrakenSpotAdapter(ExchangeAdapter):
    """Kraken spot (public endpoints).

    NOTE: Kraken uses pair codes like XBTUSD.
    Provide symbol in that format via config.
    """

    def __init__(self, cfg: VenueConfig):
        super().__init__(cfg)
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def base(self) -> str:
        return self.cfg.base_url or "https://api.kraken.com"

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        s = await self._sess()
        url = f"{self.base}/0/public/Ticker"
        async with s.get(url, params={"pair": symbol}) as r:
            j = await r.json()
        res = (j.get("result") or {})
        # result key is dynamic; pick first
        item = next(iter(res.values()), None) if isinstance(res, dict) else None
        bid = float(((item or {}).get("b") or [0])[0] or 0.0)
        ask = float(((item or {}).get("a") or [0])[0] or 0.0)
        return MarketQuote(venue=self.name, product="spot", symbol=symbol, bid=bid, ask=ask, ts_ms=self._now_ms(), meta={"src": "kraken_spot"})

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
