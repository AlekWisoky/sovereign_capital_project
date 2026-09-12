from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..arb_engine import requote_opportunity
from .b4_quote_units import usd_notional_to_raw_units
from .final_quote import FinalQuote, produce_final_quote


class ExecutionQuoteBindingError(ValueError):
    """Raised when the canonical sizing cannot be bound to execution truth."""


@dataclass(frozen=True)
class BoundExecutionQuote:
    quote: FinalQuote
    sizing_id: str
    approved_notional_usd: float
    raw_amount: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "quote_id": self.quote.quote_id,
            "quoted_at_ms": self.quote.quoted_at_ms,
            "block_number": self.quote.block_number,
            "asset_price_usd": self.quote.asset_price_usd,
            "asset_decimals": self.quote.asset_decimals,
            "raw_amount": self.raw_amount,
            "sizing_id": self.sizing_id,
            "approved_notional_usd": self.approved_notional_usd,
            "decision_id": self.quote.decision_id,
            "correlation_id": self.quote.correlation_id,
            "route_id": self.quote.route_id,
        }


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _lineage_maps(opp: Any, decision: Any | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    meta = _mapping(getattr(opp, "meta", None))
    lineage = _mapping(meta.get("canonical_lineage"))
    brain = _mapping(meta.get("brain"))
    decision_meta = _mapping(getattr(decision, "metadata", None))
    return meta, lineage, brain, decision_meta


def _lineage(opp: Any, decision: Any | None) -> tuple[str, str, str, float]:
    meta, lineage, brain, decision_meta = _lineage_maps(opp, decision)
    sizing_id = _text(
        decision_meta.get("sizing_id"),
        lineage.get("sizing_id"),
        brain.get("sizing_id"),
        meta.get("sizing_id"),
    )
    if not sizing_id:
        raise ExecutionQuoteBindingError("sizing_id_required")

    decision_id = _text(
        decision_meta.get("canonical_decision_id"),
        decision_meta.get("decision_id"),
        lineage.get("decision_id"),
        brain.get("canonical_decision_id"),
    )
    correlation_id = _text(
        decision_meta.get("correlation_id"),
        lineage.get("correlation_id"),
        brain.get("correlation_id"),
    )
    if not decision_id or not correlation_id:
        raise ExecutionQuoteBindingError("canonical_decision_lineage_required")

    approved = lineage.get("approved_notional_usd")
    if approved is None:
        approved = decision_meta.get("approved_notional_usd")
    try:
        approved_usd = float(approved)
    except (TypeError, ValueError) as exc:
        raise ExecutionQuoteBindingError("approved_notional_usd_missing") from exc
    if approved_usd <= 0:
        raise ExecutionQuoteBindingError("approved_notional_usd_invalid")
    return sizing_id, decision_id, correlation_id, approved_usd


def _validate_decision_lineage(decision: Any | None, decision_id: str, correlation_id: str) -> None:
    if decision is None:
        return
    decision_meta = _mapping(getattr(decision, "metadata", None))
    if _text(decision_meta.get("canonical_decision_id"), decision_id) != decision_id:
        raise ExecutionQuoteBindingError("decision_lineage_conflict")
    decision_correlation = _text(decision_meta.get("correlation_id"))
    if decision_correlation and decision_correlation != correlation_id:
        raise ExecutionQuoteBindingError("correlation_lineage_conflict")


def _execution_raw_cap(cfg: Any, raw_amount: int) -> int:
    max_raw = int(getattr(getattr(cfg, "safety", None), "max_borrow_amount", 0) or 0)
    if max_raw > 0:
        return min(raw_amount, max_raw)
    return raw_amount


def _record_binding_lineage(opp: Any, decision: Any | None, binding: BoundExecutionQuote) -> None:
    meta = getattr(opp, "meta", None)
    if isinstance(meta, dict):
        meta["b4_execution_quote"] = binding.to_dict()
        lineage = meta.get("canonical_lineage")
        if isinstance(lineage, dict):
            lineage.update(
                {
                    "quote_id": binding.quote.quote_id,
                    "raw_amount": binding.raw_amount,
                    "sizing_id": binding.sizing_id,
                    "decision_id": binding.quote.decision_id,
                    "correlation_id": binding.quote.correlation_id,
                }
            )

    if decision is None:
        return
    decision_meta = getattr(decision, "metadata", None)
    if not isinstance(decision_meta, dict):
        return
    execution_lineage = decision_meta.get("execution_lineage")
    if not isinstance(execution_lineage, dict):
        execution_lineage = {}
    execution_lineage.update(
        {
            "decision_id": binding.quote.decision_id,
            "correlation_id": binding.quote.correlation_id,
            "sizing_id": binding.sizing_id,
            "quote_id": binding.quote.quote_id,
            "raw_amount": binding.raw_amount,
        }
    )
    decision_meta["execution_lineage"] = execution_lineage
    decision_meta["quote_id"] = binding.quote.quote_id
    try:
        decision.metadata = decision_meta
    except (AttributeError, TypeError) as exc:
        raise ExecutionQuoteBindingError("decision_metadata_not_mutable") from exc


async def bind_final_quote_to_execution(
    *,
    rpc_read: Any,
    cfg: Any,
    cache: Any,
    opp: Any,
    decision: Any | None,
    block_number: int,
) -> BoundExecutionQuote | None:
    """Bind canonical USD sizing to the exact raw amount used by execution."""
    sizing_id, decision_id, correlation_id, approved_usd = _lineage(opp, decision)
    _validate_decision_lineage(decision, decision_id, correlation_id)

    if cache is None:
        raise ExecutionQuoteBindingError("quote_requote_cache_required")

    quote = await produce_final_quote(
        rpc_read,
        cfg,
        opp,
        decision=decision,
        block_number=int(block_number),
    )
    if quote.decision_id != decision_id or quote.correlation_id != correlation_id:
        raise ExecutionQuoteBindingError("quote_lineage_conflict")

    raw_amount = usd_notional_to_raw_units(
        approved_usd,
        asset_price_usd=quote.asset_price_usd,
        asset_decimals=quote.asset_decimals,
    )
    raw_amount = _execution_raw_cap(cfg, raw_amount)
    if raw_amount <= 0:
        raise ExecutionQuoteBindingError("quote_bound_raw_amount_invalid")

    rq = await requote_opportunity(
        rpc_read,
        cfg,
        cache,
        opp,
        new_amount_in=int(raw_amount),
        slippage_bps=int(getattr(getattr(cfg, "safety", None), "slippage_bps", 50) or 50),
    )
    if rq is None:
        raise ExecutionQuoteBindingError("quote_bound_requote_failed")

    legs = list(getattr(getattr(opp, "route", None), "legs", []) or [])
    if not legs:
        raise ExecutionQuoteBindingError("route_legs_missing")
    actual_raw = int(getattr(legs[0], "amount_in", 0) or 0)
    if actual_raw != raw_amount:
        raise ExecutionQuoteBindingError("quote_bound_raw_amount_not_applied")

    binding = BoundExecutionQuote(
        quote=quote,
        sizing_id=sizing_id,
        approved_notional_usd=approved_usd,
        raw_amount=raw_amount,
    )
    _record_binding_lineage(opp, decision, binding)
    return binding
