from __future__ import annotations

import copy
from typing import Any, Mapping

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _observe_settled_outcome(
    runtime: Any,
    *,
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Feed exactly one physically persisted canonical settlement into OMAR."""
    p = _dict(pending)
    row = _dict(outcome)
    if _text(row.get("status")).lower() != "settled":
        return {"ok": False, "reason_code": "outcome_not_settled"}
    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason_code": "omar_disabled"}
    lineage = _dict(p.get("canonical_lineage"))
    decision_id = _text(p.get("canonical_decision_id") or lineage.get("decision_id"))
    correlation_id = _text(p.get("correlation_id") or lineage.get("correlation_id"))
    if not decision_id or not correlation_id:
        return {"ok": False, "reason_code": "canonical_lineage_missing"}
    row_decision_id = _text(row.get("decision_id"))
    row_correlation_id = _text(row.get("correlation_id"))
    if row_decision_id and row_decision_id != decision_id:
        return {"ok": False, "reason_code": "canonical_lineage_mismatch"}
    if row_correlation_id and row_correlation_id != correlation_id:
        return {"ok": False, "reason_code": "canonical_lineage_mismatch"}
    row.setdefault("decision_id", decision_id)
    row.setdefault("correlation_id", correlation_id)

    operator_intent = _dict(lineage.get("operator_intent") or p.get("operator_intent"))
    metadata = {
        "canonical_lineage": {"decision_id": decision_id, "correlation_id": correlation_id},
        "source": "phase2_canonical_outcome_ledger",
        "settlement": copy.deepcopy(row),
    }
    if operator_intent:
        metadata["operator_intent"] = copy.deepcopy(operator_intent)
    intent_fingerprint = _text(lineage.get("intent_fingerprint") or p.get("intent_fingerprint"))
    if intent_fingerprint:
        metadata["intent_fingerprint"] = intent_fingerprint

    return dict(
        omar.observe_outcome(
            decision_id=decision_id,
            ok=bool(row.get("ok", True)),
            realized_net_usd=row.get("realized_net_usd"),
            expected_net_usd=row.get("expected_net_usd", p.get("expected_net_usd")),
            amount_in_wei=row.get("amount_in_wei"),
            gas_cost_usd=row.get("gas_cost_usd"),
            slippage_bps=row.get("slippage_bps"),
            latency_ms=row.get("latency_ms"),
            route_id=_text(row.get("route_id")),
            tx_hash=_text(row.get("tx_hash")),
            outcome_truth_verified=bool(row.get("truth_verified", False)),
            metadata=metadata,
        )
    )
