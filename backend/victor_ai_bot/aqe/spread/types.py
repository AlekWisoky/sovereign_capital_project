from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class OpportunityType(str, Enum):
    SPOT_FUTURES = "spot_futures"
    FUTURES_FUTURES = "futures_futures"
    SPOT_SPOT = "spot_spot"
    FUNDING_ARB = "funding_arb"
    CEX_DEX = "cex_dex"
    CROSS_CHAIN = "cross_chain"


@dataclass
class SpreadOpportunity:
    opp_id: str
    opp_type: OpportunityType
    buy_venue: str
    sell_venue: str
    symbol: str
    spread: float
    volume: float
    fees_usd: float = 0.0
    slippage_usd: float = 0.0
    transfer_usd: float = 0.0
    gas_usd: float = 0.0
    vol_risk_usd: float = 0.0
    profit_usd: float = 0.0
    alpha: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)
