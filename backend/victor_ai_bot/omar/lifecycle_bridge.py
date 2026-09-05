from __future__ import annotations

from typing import Any, Mapping


_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _canonical_lineage(pending: Mapping[str, Any]) -> dict[str, str]:
    meta = _dict(pending.get("canonical_lineage"))
    brain = _dict(pending.get("brain"))
    decision_id = _text(
        meta.get("decision_id")
        or brain.get("canonical_decision_id")
        or brain.get("decision_id")
    )
    correlation_id = _text(meta.get("correlation_id") or brain.get("correlation_id"))
    return {"decision_id": decision_id, "correlation_id": correlation_id}


def _observe_settled_outcome(
    runtime: Any,
    *,
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    """Feed one canonical settled outcome into OMAR without inventing truth.

    This bridge is deliberately downstream of settlement. It requires a
    settled outcome and a complete decision/correlation lineage before a
    learning update is attempted. OMAR remains non-authoritative.
    """
    pending_map = _dict(pending)
    outcome_map = _dict(outcome)
    status = _text(outcome_map.get("status")).lower()
    if status not in {"settled", "closed", "complete", "completed"}:
        return {"ok": False, "reason_code": "outcome_not_settled"}

    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason_code": "omar_disabled"}

    lineage = _canonical_lineage(pending_map)
    if not lineage["decision_id"] or not lineage["correlation_id"]:
        return {"ok": False, "reason_code": "canonical_lineage_missing"}

    canonical_meta = _dict(pending_map.get("canonical_lineage"))
    operator_intent = _dict(canonical_meta.get("operator_intent"))
    intent_fingerprint = _text(canonical_meta.get("intent_fingerprint"))
    route_id = _text(outcome_map.get("route_id") or pending_map.get("route_id"))
    tx_hash = _text(outcome_map.get("tx_hash") or outcome_map.get("txHash"))

    kwargs = {
        "decision_id": lineage["decision_id"],
        "ok": bool(outcome_map.get("ok", True)),
        "realized_net_usd": float(
            outcome_map.get("realized_net_usd", outcome_map.get("realizedNetUsd", 0.0)) or 0.0
        ),
        "expected_net_usd": float(
            outcome_map.get("expected_net_usd", outcome_map.get("expectedNetUsd", 0.0)) or 0.0
        ),
        "amount_in_wei": int(
            outcome_map.get("amount_in_wei", outcome_map.get("amountInWei", 0)) or 0
        ),
        "gas_cost_usd": float(
            outcome_map.get("gas_cost_usd", outcome_map.get("gasCostUsd", 0.0)) or 0.0
        ),
        "slippage_bps": float(
            outcome_map.get("slippage_bps", outcome_map.get("slippageBps", 0.0)) or 0.0
        ),
        "latency_ms": int(outcome_map.get("latency_ms", outcome_map.get("latencyMs", 0)) or 0),
        "route_id": route_id,
        "tx_hash": tx_hash,
        "outcome_truth_verified": bool(
            outcome_map.get("truth_verified", outcome_map.get("outcome_truth_verified", True))
        ),
        "metadata": {
            "canonical_lineage": lineage,
            "source": "phase2_canonical_outcome_ledger",
            "settlement": dict(outcome_map),
        },
    }
    if operator_intent:
        kwargs["metadata"]["operator_intent"] = operator_intent
    if intent_fingerprint:
        kwargs["metadata"]["intent_fingerprint"] = intent_fingerprint

    try:
        learned = omar.observe_outcome(**kwargs)
    except _SAFE as exc:
        return {"ok": False, "reason_code": "omar_observe_failed", "error": str(exc)}

    return dict(learned) if isinstance(learned, Mapping) else {"ok": True, "result": learned}
