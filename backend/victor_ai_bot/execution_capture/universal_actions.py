from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class UniversalAction:
    action_id: str
    family: str
    action_type: str
    route_family: str
    engine_type: str
    chain: str
    venues: List[str]
    token_path: List[str]
    expected_profit_usd: float
    expected_realized_profit_usd: float
    capital_required_usd: float
    loan_source: str = ""
    confidence: float = 0.0
    lifecycle_stage: str = "sandbox"
    risk_flags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
