from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionIdentity:
    """First-class identity for one real execution attempt.

    The execution ID is created at the production execution boundary. It is
    intentionally not derived from a transaction hash, opportunity ID, or
    decision ID because retries and replacement transactions are distinct
    execution attempts.
    """

    execution_id: str
    decision_id: str
    correlation_id: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def create_execution_identity(decision: Any, opp: Any) -> ExecutionIdentity:
    """Create a unique execution-attempt identity from canonical decision lineage."""
    decision_meta = _dict(getattr(decision, "metadata", None))
    opp_meta = _dict(getattr(opp, "meta", None))
    brain = _dict(opp_meta.get("brain"))
    lineage = _dict(opp_meta.get("canonical_lineage"))

    decision_id = _text(
        decision_meta.get("canonical_decision_id")
        or decision_meta.get("decision_id")
        or brain.get("canonical_decision_id")
        or lineage.get("decision_id")
    )
    correlation_id = _text(
        decision_meta.get("correlation_id")
        or brain.get("correlation_id")
        or lineage.get("correlation_id")
    )
    if not decision_id or not correlation_id:
        raise ValueError("canonical_decision_lineage_required_for_execution_identity")

    return ExecutionIdentity(
        execution_id=f"execution_{uuid4().hex}",
        decision_id=decision_id,
        correlation_id=correlation_id,
    )


def attach_execution_identity(
    identity: ExecutionIdentity, *, decision: Any, opp: Any, result: Any | None = None
) -> None:
    """Propagate one execution identity through decision, opportunity, and result."""
    decision_meta = _dict(getattr(decision, "metadata", None))
    decision_meta["execution_id"] = identity.execution_id
    decision_meta["canonical_decision_id"] = identity.decision_id
    decision_meta["correlation_id"] = identity.correlation_id
    decision_meta["execution_lineage"] = {
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
        "execution_id": identity.execution_id,
    }
    try:
        decision.metadata = decision_meta
    except (AttributeError, TypeError):
        pass

    opp_meta = _dict(getattr(opp, "meta", None))
    brain = _dict(opp_meta.get("brain"))
    brain["execution_id"] = identity.execution_id
    opp_meta["brain"] = brain
    opp_meta["execution_lineage"] = {
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
        "execution_id": identity.execution_id,
    }
    try:
        opp.meta = opp_meta
    except (AttributeError, TypeError):
        pass

    if result is not None:
        plan = _dict(getattr(result, "plan", None))
        plan["execution_id"] = identity.execution_id
        plan["canonical_decision_id"] = identity.decision_id
        plan["correlation_id"] = identity.correlation_id
        plan["execution_lineage"] = {
            "decision_id": identity.decision_id,
            "correlation_id": identity.correlation_id,
            "execution_id": identity.execution_id,
        }
        try:
            result.plan = plan
        except (AttributeError, TypeError):
            pass
