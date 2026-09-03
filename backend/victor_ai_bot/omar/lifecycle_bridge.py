from __future__ import annotations

from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _observe_settled_outcome(
    runtime: Any, *, pending: Mapping[str, Any], outcome: Mapping[str, Any]
) -> dict[str, Any]:
    """Bridge one canonical settled outcome into OMAR without changing execution truth."""
    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason": "omar_disabled"}

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
    canonical_lineage = {"decision_id": decision_id, "correlation_id": correlation_id}
    operator_intent = _mapping(lineage.get("operator_intent") or p.get("operator_intent"))
    metadata = {
        "source": "phase2_canonical_outcome_ledger",
        "canonical_lineage": canonical_lineage,
        "operator_intent": operator_intent,
        "intent_fingerprint": str(
            lineage.get("intent_fingerprint") or p.get("intent_fingerprint") or ""
        ),
        "outcome_status": str(o.get("status") or ""),
        "truth_verified": bool(o.get("truth_verified")),
    }
    payload = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "route_id": str(o.get("route_id") or p.get("route_id") or ""),
        "tx_hash": str(o.get("tx_hash") or ""),
        "latency_ms": o.get("latency_ms"),
        "reward": float(
            o.get("realized_net_usd") if o.get("realized_net_usd") is not None else 0.0
        ),
        "outcome_truth_verified": bool(o.get("truth_verified")),
        "metadata": metadata,
    }
    observer = getattr(omar, "observe_settled_ledger_record", None)
    if callable(observer):
        settled_row = dict(o)
        settled_row["decision_id"] = decision_id
        settled_row["correlation_id"] = correlation_id
        settled_row["metadata"] = metadata
        settled_row["lineage"] = canonical_lineage
        return dict(observer(settled_row))
    observer = getattr(omar, "observe_outcome", None)
    if not callable(observer):
        return {"ok": False, "reason": "omar_observer_unavailable"}
    result = observer(**payload)
    return dict(result) if isinstance(result, Mapping) else {"ok": True, "result": result}
