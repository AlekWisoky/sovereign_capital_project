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
    # First-class canonical lifecycle identity. These remain optional for
    # legacy/non-trade outcomes and are resolved from details when available.
    decision_id: str = ""
    correlation_id: str = ""
    execution_id: str = ""
    settlement_id: str = ""

    def __post_init__(self) -> None:
        lineage = self.details.get("lineage") if isinstance(self.details, dict) else {}
        identity = self.details.get("identity") if isinstance(self.details, dict) else {}
        lineage = lineage if isinstance(lineage, dict) else {}
        identity = identity if isinstance(identity, dict) else {}
        for name in ("decision_id", "correlation_id", "execution_id", "settlement_id"):
            current = str(getattr(self, name) or "")
            if current:
                continue
            aliases = {
                "decision_id": "decisionId",
                "correlation_id": "correlationId",
                "execution_id": "executionId",
                "settlement_id": "settlementId",
            }
            alias = aliases[name]
            value = identity.get(name) or identity.get(alias)
            value = value or lineage.get(name) or lineage.get(alias)
            object.__setattr__(self, name, str(value or ""))

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
