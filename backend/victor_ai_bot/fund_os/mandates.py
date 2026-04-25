from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class FundMandate:
    family: str
    allowed_venues: List[str]
    capacity_ceiling_pct: float
    expected_turnover: str
    max_drawdown_pct: float
    allowed_execution_lanes: List[str]
    leverage_cap: float
    liquidity_bucket: str
    hedge_policy: str
    promotion_status: str
    capital_sources: List[str]
    stage_restrictions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
