from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional


class ExecutionLane(str, Enum):
    PUBLIC = "PUBLIC"
    PROTECTED = "PROTECTED"
    PRIVATE = "PRIVATE"
    DROP = "DROP"


@dataclass(frozen=True)
class SafeSizePoint:
    size_mult: float
    expected_profit_usd: float
    slippage_cost_usd: float
    interference_penalty_usd: float
    latency_decay_cost_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OpportunityEnvelope:
    opportunity_id: str
    route_id: str
    route_family: str
    expected_profit_usd: float
    gas_estimate_usd: float
    slippage_sensitivity: float
    liquidity_fragility: float
    latency_half_life_ms: int
    mempool_copy_risk: float
    venue_reliability_score: float
    simulation_confidence: float
    safe_size_curve: List[SafeSizePoint]
    failure_cost_estimate: float
    freshness_score: float
    private_send_preference: bool
    chain_id: int
    token_path: List[str] = field(default_factory=list)
    venues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["safe_size_curve"] = [x.to_dict() for x in self.safe_size_curve]
        return out


@dataclass(frozen=True)
class CaptureScore:
    success_probability: float
    freshness_probability: float
    interference_probability: float
    venue_quality: float
    expected_realized_pnl: float
    capture_score: float
    expected_realized_value: float
    slippage_cost_estimate: float
    latency_decay_cost: float
    failure_cost_estimate: float
    telemetry_adjustments: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionDecision:
    action: str
    lane: ExecutionLane
    route_id: str
    opportunity_id: str
    size_mult: float
    expected_realized_value: float
    expected_realized_pnl: float
    success_probability: float
    freshness_probability: float
    interference_probability: float
    send_mode: str
    relay_hint: str
    reason: str
    drop_reason: str = ""
    retryable: bool = False
    endpoint_hint: str = ""
    capture_score: Optional[CaptureScore] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["lane"] = str(self.lane.value)
        out["capture_score"] = (
            self.capture_score.to_dict() if self.capture_score is not None else None
        )
        return out
