from __future__ import annotations

from dataclasses import asdict, dataclass
import time
import uuid
from typing import Any, Mapping


@dataclass(frozen=True)
class TradeIdentity:
    """Canonical identity shared by decision, execution, settlement, and learning."""

    decision_id: str
    correlation_id: str
    execution_id: str = ""
    settlement_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def complete_for_execution(self) -> bool:
        return bool(self.decision_id and self.correlation_id and self.execution_id)

    @property
    def complete_for_settlement(self) -> bool:
        return bool(self.complete_for_execution and self.settlement_id)


def new_decision_identity() -> TradeIdentity:
    """Create a unique decision/correlation pair at the decision boundary."""
    token = uuid.uuid4().hex
    return TradeIdentity(
        decision_id=f"decision_{token}",
        correlation_id=f"corr_{token}",
    )


def new_execution_identity(identity: TradeIdentity) -> TradeIdentity:
    if not identity.decision_id or not identity.correlation_id:
        raise ValueError("decision identity is incomplete")
    return TradeIdentity(
        decision_id=identity.decision_id,
        correlation_id=identity.correlation_id,
        execution_id=f"exec_{uuid.uuid4().hex}",
        settlement_id=identity.settlement_id,
    )


def new_settlement_identity(identity: TradeIdentity) -> TradeIdentity:
    if not identity.complete_for_execution:
        raise ValueError("execution identity is incomplete")
    return TradeIdentity(
        decision_id=identity.decision_id,
        correlation_id=identity.correlation_id,
        execution_id=identity.execution_id,
        settlement_id=f"settle_{uuid.uuid4().hex}",
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def identity_from(value: Any) -> TradeIdentity | None:
    """Read identity from an object or mapping without fabricating missing IDs."""
    if value is None:
        return None
    if isinstance(value, TradeIdentity):
        return value
    if isinstance(value, Mapping):
        source = value
    else:
        source = getattr(value, "identity", None)
        if isinstance(source, TradeIdentity):
            return source
        if not isinstance(source, Mapping):
            source = getattr(value, "metadata", None)
        if not isinstance(source, Mapping):
            source = value.__dict__ if hasattr(value, "__dict__") else {}

    nested = _mapping(source.get("identity"))
    lineage = _mapping(source.get("lineage"))
    return TradeIdentity(
        decision_id=_text(
            source.get("decision_id")
            or source.get("decisionId")
            or nested.get("decision_id")
            or nested.get("decisionId")
            or lineage.get("decision_id")
            or lineage.get("decisionId")
        ),
        correlation_id=_text(
            source.get("correlation_id")
            or source.get("correlationId")
            or nested.get("correlation_id")
            or nested.get("correlationId")
            or lineage.get("correlation_id")
            or lineage.get("correlationId")
        ),
        execution_id=_text(
            source.get("execution_id")
            or source.get("executionId")
            or nested.get("execution_id")
            or nested.get("executionId")
            or lineage.get("execution_id")
            or lineage.get("executionId")
        ),
        settlement_id=_text(
            source.get("settlement_id")
            or source.get("settlementId")
            or nested.get("settlement_id")
            or nested.get("settlementId")
            or lineage.get("settlement_id")
            or lineage.get("settlementId")
        ),
    )


def attach_identity(target: Any, identity: TradeIdentity) -> Any:
    """Attach identity to a mutable runtime object and its metadata/plan."""
    if target is None:
        return target
    for name, value in identity.to_dict().items():
        if value:
            try:
                setattr(target, name, value)
            except (AttributeError, TypeError):
                pass
    payload = identity.to_dict()
    try:
        metadata = getattr(target, "metadata", None)
        if isinstance(metadata, dict):
            metadata.setdefault("identity", {}).update(payload)
            metadata.setdefault("lineage", {}).update(payload)
    except (AttributeError, TypeError):
        pass
    try:
        plan = getattr(target, "plan", None)
        if isinstance(plan, dict):
            plan.setdefault("identity", {}).update(payload)
            plan.setdefault("lineage", {}).update(payload)
    except (AttributeError, TypeError):
        pass
    try:
        setattr(target, "identity", identity)
    except (AttributeError, TypeError):
        pass
    return target


def identity_event(identity: TradeIdentity, event: str, **extra: Any) -> dict[str, Any]:
    return {
        "event": str(event),
        "ts_ms": int(time.time() * 1000),
        **identity.to_dict(),
        **dict(extra),
    }
