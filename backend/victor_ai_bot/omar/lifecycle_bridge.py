from __future__ import annotations

from typing import Any, Mapping

from .real_learning import OmarRealLearningLoop
from .settled_ledger_bridge import ingest_settled_ledger_record


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _resolve_real_learning_loop(runtime: Any) -> OmarRealLearningLoop | None:
    """Resolve the actual production OMAR real-learning loop."""
    direct = getattr(runtime, "_real_learning", None)
    if isinstance(direct, OmarRealLearningLoop):
        return direct

    omar = getattr(runtime, "_omar", None)
    if omar is not None:
        try:
            if hasattr(omar, "bind_runtime"):
                omar.bind_runtime(runtime)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        loop = getattr(omar, "_real_learning", None)
        if isinstance(loop, OmarRealLearningLoop):
            return loop

    try:
        from .integration import active_omar_runtime

        active = active_omar_runtime()
        if active is None:
            return None
        if hasattr(active, "bind_runtime"):
            active.bind_runtime(runtime)
        loop = getattr(active, "_real_learning", None)
        return loop if isinstance(loop, OmarRealLearningLoop) else None
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        return None


def _observe_settled_outcome(
    runtime: Any, *, pending: Mapping[str, Any], outcome: Mapping[str, Any]
) -> dict[str, Any]:
    """Feed one canonical settled outcome directly into OmarRealLearningLoop."""
    loop = _resolve_real_learning_loop(runtime)
    if loop is None:
        return {"ok": False, "eligible_for_learning": False, "reason_code": "omar_loop_unavailable"}

    p = _mapping(pending)
    o = _mapping(outcome)
    brain = _mapping(p.get("brain"))
    lineage = _mapping(p.get("canonical_lineage"))

    decision_id = str(
        lineage.get("decision_id")
        or brain.get("canonical_decision_id")
        or p.get("decision_id")
        or ""
    )
    correlation_id = str(
        lineage.get("correlation_id")
        or brain.get("correlation_id")
        or p.get("correlation_id")
        or ""
    )
    execution_id = str(
        lineage.get("execution_id") or p.get("execution_id") or o.get("execution_id") or ""
    )
    settlement_id = str(
        lineage.get("settlement_id")
        or o.get("settlement_id")
        or o.get("transaction_id")
        or o.get("transactionId")
        or ""
    )
    action = str(p.get("action") or p.get("aqe_action") or o.get("action") or "trade")

    operator_intent = _mapping(
        lineage.get("operator_intent") or p.get("operator_intent") or o.get("operator_intent")
    )
    canonical_lineage = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "execution_id": execution_id,
        "settlement_id": settlement_id,
    }
    metadata = {
        "source": "canonical_receipt_settlement",
        "canonical_lineage": canonical_lineage,
        "operator_intent": operator_intent,
        "intent_fingerprint": str(
            lineage.get("intent_fingerprint") or p.get("intent_fingerprint") or ""
        ),
        "outcome_status": str(o.get("status") or ""),
        "truth_verified": bool(o.get("truth_verified", True)),
    }
    settled_row = dict(o)
    settled_row.update(
        {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "execution_id": execution_id,
            "settlement_id": settlement_id,
            "action": action,
            "route_id": str(o.get("route_id") or p.get("route_id") or ""),
            "tx_hash": str(o.get("tx_hash") or o.get("receipt_id") or ""),
            "status": str(o.get("status") or "settled"),
            "metadata": metadata,
            "lineage": canonical_lineage,
        }
    )
    result = ingest_settled_ledger_record(loop, settled_row)
    return {**dict(result), "canonical_lineage": canonical_lineage}
