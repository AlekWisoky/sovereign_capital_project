from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class ExecutionOutcome:
    status: str
    reason_code: str
    retryable: bool
    degraded_mode: str = ""
    tx_hash: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapitalDecision:
    approved: bool
    reason_code: str
    borrow_cost_bps: float = 0.0
    requires_operator_review: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LaunchDecision:
    allowed: bool
    reason_code: str
    blocked_by: List[str] = field(default_factory=list)
    suggested_next_action: str = ""
    degraded_mode: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceOutcome:
    allowed: bool
    reason_code: str
    required_scope: str = ""
    review_required: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPromotionDecision:
    allowed: bool
    reason_code: str
    next_stage: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
