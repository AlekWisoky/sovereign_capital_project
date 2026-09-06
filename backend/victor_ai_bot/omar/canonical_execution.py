from __future__ import annotations

from typing import Any, Mapping

from ..decision_identity import ensure_decision_identity, lineage_from_opportunity


class CanonicalExecutionInvariantError(RuntimeError):
    """Raised when an auto-execution attempt lacks canonical decision lineage."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def require_canonical_execution_context(
    runtime: Any,
    opportunity: Any,
    decision: Any,
    *,
    current_block: int,
) -> tuple[str, str]:
    """Make canonical decision identity a hard precondition for execution.

    OMAR is not required for this invariant. The invariant protects the
    production execution path itself: every auto trade must originate from a
    canonical decision and carry decision/correlation identity before it can
    reach governance or the execution boundary.
    """
    if decision is None:
        raise CanonicalExecutionInvariantError("execution_requires_canonical_decision")

    action = _text(getattr(decision, "action", "")).lower()
    if action != "trade":
        raise CanonicalExecutionInvariantError(
            f"execution_requires_trade_decision:action={action or 'missing'}"
        )

    chain = getattr(getattr(runtime, "cfg", None), "chain", None)
    chain_name = _text(getattr(chain, "name", "chain")) or "chain"
    identity = ensure_decision_identity(
        opportunity,
        decision,
        chain_name=chain_name,
        current_block=int(current_block),
    )
    lineage = lineage_from_opportunity(opportunity)
    decision_id = _text(lineage.get("decision_id"))
    correlation_id = _text(lineage.get("correlation_id"))
    if decision_id != identity.decision_id or correlation_id != identity.correlation_id:
        raise CanonicalExecutionInvariantError("execution_identity_resolution_failed")
    if not decision_id or not correlation_id:
        raise CanonicalExecutionInvariantError("execution_requires_decision_and_correlation_id")

    metadata = getattr(decision, "metadata", None)
    if not isinstance(metadata, Mapping):
        raise CanonicalExecutionInvariantError("execution_requires_decision_metadata")
    if _text(metadata.get("canonical_decision_id")) != decision_id:
        raise CanonicalExecutionInvariantError("decision_metadata_identity_mismatch")
    if _text(metadata.get("correlation_id")) != correlation_id:
        raise CanonicalExecutionInvariantError("decision_metadata_correlation_mismatch")

    return decision_id, correlation_id
