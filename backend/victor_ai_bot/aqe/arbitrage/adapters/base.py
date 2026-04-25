from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..models import MarketQuote, OrderBook, ProductType


@dataclass
class VenueConfig:
    name: str
    product: ProductType
    base_url: str = ""
    fee_bps: int = 10
    meta: Dict[str, Any] | None = None


class ExchangeAdapter:
    """Minimal adapter interface (Phase 5).

    This is intentionally small to keep the system dependency-light.
    Implementations should use public endpoints in observe-mode.

    Execution is NOT handled by this interface in Phase 5.
    """

    def __init__(self, cfg: VenueConfig):
        self.cfg = cfg

    @property
    def name(self) -> str:
        return str(self.cfg.name)

    @property
    def product(self) -> ProductType:
        return self.cfg.product

    async def fetch_quote(self, *, symbol: str) -> MarketQuote:
        raise NotImplementedError

    async def fetch_orderbook(self, *, symbol: str, depth: int = 10) -> Optional[OrderBook]:
        return None

    async def close(self) -> None:
        return None

    # Helpers
    def _now_ms(self) -> int:
        return int(time.time() * 1000)
