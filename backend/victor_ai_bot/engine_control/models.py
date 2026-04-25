from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class EngineCapability:
    engine_type: str
    maturity: str
    allowed_lifecycle_stages: List[str]
    max_capital_pct: float
    max_size_mult: float
    execution_permission: str
    required_confidence: float
    required_telemetry_points: int
    allowed_envs: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EngineOpportunity:
    opportunity_id: str
    engine_type: str
    strategy_family: str
    route_family: str
    chain: str
    chain_id: int
    expected_profit_usd: float
    expected_realized_profit_usd: float
    capital_required_usd: float
    inventory_requirements: Dict[str, float]
    confidence: float
    regime: str
    latency_sensitivity: float
    risk_flags: List[str] = field(default_factory=list)
    lifecycle_eligibility: str = "sandbox"
    policy_eligibility: str = "observe_only"
    venues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EngineAdmissionDecision:
    allowed: bool
    mode: str
    reason: str
    max_capital_usd: float
    max_size_mult: float
    telemetry_sufficient: bool
    calibration_sufficient: bool
    maturity: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
