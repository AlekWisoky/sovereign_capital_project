from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

ProductType = Literal["spot", "futures"]
ArbType = Literal["spot_futures", "futures_futures", "futures_spot"]


@dataclass
class OrderBookLevel:
    price: float
    qty: float


@dataclass
class OrderBook:
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

    def top_bid(self) -> Optional[float]:
        return float(self.bids[0].price) if self.bids else None

    def top_ask(self) -> Optional[float]:
        return float(self.asks[0].price) if self.asks else None

    def depth_usd(self, *, side: Literal["bid", "ask"], levels: int = 10) -> float:
        """Approx depth in quote currency units (assumes quote ~ USD).

        Conservative: sums qty*price up to N levels.
        """
        lv = self.bids[:levels] if side == "bid" else self.asks[:levels]
        return float(sum(float(x.qty) * float(x.price) for x in lv))


@dataclass
class MarketQuote:
    venue: str
    product: ProductType
    symbol: str
    bid: float
    ask: float
    ts_ms: int
    funding_rate: float = 0.0  # per funding period, e.g. 8h
    mark_price: float = 0.0
    index_price: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArbitrageOpportunity:
    arb_type: ArbType
    symbol: str
    buy_venue: str
    sell_venue: str
    buy_product: ProductType
    sell_product: ProductType

    entry_buy: float
    entry_sell: float
    spread_pct: float

    funding_rate_buy: float = 0.0
    funding_rate_sell: float = 0.0

    est_net_profit_usd: float = 0.0
    liquidity_depth_usd: float = 0.0
    pair_lifetime_sec: float = 0.0
    transfer_latency_risk_score: float = 0.0

    confidence: float = 0.0
    created_at_ms: int = 0

    meta: Dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.arb_type}:{self.symbol}:{self.buy_venue}:{self.buy_product}->{self.sell_venue}:{self.sell_product}"
