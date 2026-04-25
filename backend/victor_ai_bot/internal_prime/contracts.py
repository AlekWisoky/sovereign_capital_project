from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class PrimeBorrowRequest:
    family: str
    capital_source: str
    notional_usd: float
    asset: str
    horizon_minutes: float
    confidence: float
    collateral_units: float = 0.0
    asset_price_usd: float = 0.0
    request_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrimeLoanPosition:
    loan_id: str
    family: str
    asset: str
    notional_usd: float
    borrow_cost_usd: float
    opened_ts_ms: int
    collateral_reserved_usd: float = 0.0
    collateral_ratio: float = 1.0
    collateral_haircut_pct: float = 0.0
    collateral_efficiency: float = 1.0
    collateral_units: float = 0.0
    asset_price_usd: float = 0.0
    status: str = "open"
    settled_ts_ms: int = 0
    disputed_ts_ms: int = 0
    dispute_reason_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
