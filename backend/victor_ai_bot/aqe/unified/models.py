from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

_SAFE_ASDICT_EXCEPTIONS = (AttributeError, TypeError, ValueError)


@dataclass
class UnifiedOrderBookLevel:
    price: float
    size: float


@dataclass
class UnifiedOrderBook:
    venue: str
    symbol: str
    bids: List[UnifiedOrderBookLevel] = field(default_factory=list)
    asks: List[UnifiedOrderBookLevel] = field(default_factory=list)
    ts: int = 0


@dataclass
class UnifiedFundingData:
    venue: str
    symbol: str
    funding_rate: float = 0.0
    next_funding_ts: int = 0
    mark_price: float = 0.0
    ts: int = 0


@dataclass
class UnifiedPosition:
    venue: str
    symbol: str
    side: str  # long|short|flat
    size: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    ts: int = 0


@dataclass
class UnifiedCapitalState:
    total_usd: float = 0.0
    onchain_usd: float = 0.0
    cex_spot_usd: float = 0.0
    cex_futures_usd: float = 0.0
    stable_reserves_usd: float = 0.0
    drawdown_pct: float = 0.0
    ts: int = 0


@dataclass
class UnifiedDEXPoolState:
    chain: str
    venue: str
    pool: str
    token0: str
    token1: str
    price: float = 0.0
    liquidity: float = 0.0
    fee_bps: int = 0
    ts: int = 0


@dataclass
class UnifiedGasState:
    basefee_gwei: float = 0.0
    priority_gwei: float = 0.0
    max_fee_gwei: float = 0.0
    congestion: float = 0.0
    ts: int = 0


@dataclass
class UnifiedMempoolState:
    pending_rate: float = 0.0
    competition_density: float = 0.0
    mev_risk: float = 0.0
    builder_hint: str = ""
    ts: int = 0


def asdict_safe(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict):
        return dict(x)
    try:
        raw = getattr(x, "__dict__", None)
    except _SAFE_ASDICT_EXCEPTIONS:
        return {}
    return dict(raw or {}) if isinstance(raw, dict) else {}
