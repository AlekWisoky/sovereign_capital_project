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

    pending_lineage = _dict(p.get("canonical_lineage"))
    outcome_lineage = _dict(row.get("canonical_lineage"))
    decision_id = _text(p.get("canonical_decision_id") or pending_lineage.get("decision_id"))
    correlation_id = _text(p.get("correlation_id") or pending_lineage.get("correlation_id"))
    execution_id = _text(p.get("execution_id") or pending_lineage.get("execution_id"))
    sizing_id = _text(p.get("sizing_id") or pending_lineage.get("sizing_id"))
    opportunity_id = _text(p.get("opportunity_id") or pending_lineage.get("opportunity_id"))
    route_id = _text(p.get("route_id") or pending_lineage.get("route_id"))
    action = _text(p.get("action") or pending_lineage.get("action"))
    outcome_id = _text(row.get("outcome_id") or outcome_lineage.get("outcome_id"))
    receipt_id = _text(row.get("receipt_id") or outcome_lineage.get("receipt_id") or row.get("tx_hash"))

    if not decision_id or not correlation_id:
        return {"ok": False, "reason_code": "canonical_lineage_missing"}
    for name, expected, actual in (
        ("decision", decision_id, _text(row.get("decision_id") or outcome_lineage.get("decision_id"))),
        ("correlation", correlation_id, _text(row.get("correlation_id") or outcome_lineage.get("correlation_id"))),
        ("execution", execution_id, _text(row.get("execution_id") or outcome_lineage.get("execution_id"))),
        ("sizing", sizing_id, _text(row.get("sizing_id") or outcome_lineage.get("sizing_id"))),
        ("opportunity", opportunity_id, _text(row.get("opportunity_id") or outcome_lineage.get("opportunity_id"))),
        ("route", route_id, _text(row.get("route_id") or outcome_lineage.get("route_id"))),
        ("action", action, _text(row.get("action") or outcome_lineage.get("action"))),
    ):
        if expected and actual != expected:
            return {"ok": False, "reason_code": f"{name}_lineage_mismatch"}
    if not execution_id or not sizing_id or not opportunity_id or not route_id or not action or not outcome_id or not receipt_id:
        return {"ok": False, "reason_code": "canonical_lineage_incomplete"}

    operator_intent = _dict(pending_lineage.get("operator_intent") or p.get("operator_intent"))
    metadata = {
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "execution_id": execution_id,
            "sizing_id": sizing_id,
            "receipt_id": receipt_id,
            "outcome_id": outcome_id,
            "opportunity_id": opportunity_id,
            "route_id": route_id,
            "action": action,
        },
        "source": "phase2_canonical_outcome_ledger",
        "settlement": copy.deepcopy(row),
        "capital_demand": copy.deepcopy(row.get("capital_demand") or p.get("capital_demand") or {}),
        "capital_authority": copy.deepcopy(row.get("capital_authority") or p.get("capital_authority") or {}),
        "internal_prime_authority": copy.deepcopy(row.get("internal_prime_authority") or p.get("internal_prime_authority") or {}),
    }
    if operator_intent:
        metadata["operator_intent"] = copy.deepcopy(operator_intent)
    intent_fingerprint = _text(pending_lineage.get("intent_fingerprint") or p.get("intent_fingerprint"))
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
            route_id=route_id,
            tx_hash=_text(row.get("tx_hash") or receipt_id),
            outcome_truth_verified=bool(row.get("truth_verified", False)),
            metadata=metadata,
        )
    )
