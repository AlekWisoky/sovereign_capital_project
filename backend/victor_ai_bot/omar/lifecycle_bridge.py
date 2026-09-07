from __future__ import annotations

import copy
import inspect
from typing import Any, Mapping

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _chain_name(runtime: Any) -> str:
    return _text(getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "")) or "default"


def _observe_settled_outcome(runtime: Any, *, pending: Mapping[str, Any], outcome: Mapping[str, Any]) -> dict[str, Any]:
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
    if _text(row.get("decision_id")) != decision_id or _text(row.get("correlation_id")) != correlation_id:
        return {"ok": False, "reason_code": "canonical_lineage_mismatch"}
    metadata = {
        "canonical_lineage": {"decision_id": decision_id, "correlation_id": correlation_id},
        "source": "phase2_canonical_outcome_ledger",
        "settlement": copy.deepcopy(row),
    }
    return dict(omar.observe_outcome(
        decision_id=decision_id,
        ok=bool(row.get("ok", True)),
        realized_net_usd=float(row.get("realized_net_usd", 0.0) or 0.0),
        expected_net_usd=float(row.get("expected_net_usd", 0.0) or 0.0),
        amount_in_wei=int(row.get("amount_in_wei", 0) or 0),
        gas_cost_usd=float(row.get("gas_cost_usd", 0.0) or 0.0),
        slippage_bps=float(row.get("slippage_bps", 0.0) or 0.0),
        latency_ms=int(row.get("latency_ms", 0) or 0),
        route_id=_text(row.get("route_id")),
        tx_hash=_text(row.get("tx_hash")),
        outcome_truth_verified=bool(row.get("truth_verified", False)),
        metadata=metadata,
    ))


def _patch_receipt_settlement_learning() -> None:
    from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade
    original = getattr(RuntimeReceiptFacade, "_safe_finalize_receipt_side_effects", None)
    if original is None or getattr(original, "_omar_receipt_learning_patched", False):
        return

    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        signature = inspect.signature(original)
        bound = signature.bind_partial(self, *args, **kwargs)
        result = original(self, *args, **kwargs)
        try:
            runtime = bound.arguments.get("self")
            pending = _dict(bound.arguments.get("pending"))
            if runtime is None or not pending:
                return result
            sync = _dict(getattr(runtime, "_last_settlement_sync", None))
            if not bool(sync.get("ok", False)):
                return result
            reader = getattr(runtime, "canonical_settled_outcome", None)
            if not callable(reader):
                return result
            lineage = _dict(pending.get("canonical_lineage"))
            decision_id = _text(pending.get("canonical_decision_id") or lineage.get("decision_id"))
            correlation_id = _text(pending.get("correlation_id") or lineage.get("correlation_id"))
            outcome = reader(tx_hash=_text(bound.arguments.get("tx_hash")), decision_id=decision_id, correlation_id=correlation_id, opportunity_id=_text(pending.get("opportunity_id")))
            if outcome is not None:
                _observe_settled_outcome(runtime, pending=pending, outcome=outcome)
        except _SAFE:
            return result
        return result

    wrapped._omar_receipt_learning_patched = True
    RuntimeReceiptFacade._safe_finalize_receipt_side_effects = wrapped


def install_omar_lifecycle_hooks() -> None:
    _patch_receipt_settlement_learning()
