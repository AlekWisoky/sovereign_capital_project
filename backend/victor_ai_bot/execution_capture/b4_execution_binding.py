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


def _lineage(opp: Any, decision: Any | None) -> tuple[str, str, str, float]:
    meta = getattr(opp, "meta", None)
    meta = meta if isinstance(meta, dict) else {}
    lineage = meta.get("canonical_lineage") if isinstance(meta.get("canonical_lineage"), dict) else {}
    brain = meta.get("brain") if isinstance(meta.get("brain"), dict) else {}
    decision_meta = getattr(decision, "metadata", None)
    decision_meta = decision_meta if isinstance(decision_meta, dict) else {}

    sizing_id = str(
        decision_meta.get("sizing_id")
        or lineage.get("sizing_id")
        or brain.get("sizing_id")
        or meta.get("sizing_id")
        or ""
    ).strip()
    decision_id = str(
        decision_meta.get("canonical_decision_id")
        or decision_meta.get("decision_id")
        or lineage.get("decision_id")
        or brain.get("canonical_decision_id")
        or ""
    ).strip()
    correlation_id = str(
        decision_meta.get("correlation_id")
        or lineage.get("correlation_id")
        or brain.get("correlation_id")
        or ""
    ).strip()
    approved = lineage.get("approved_notional_usd")
    if approved is None:
        approved = decision_meta.get("approved_notional_usd")
    try:
        approved_usd = float(approved)
    except (TypeError, ValueError) as exc:
        raise ExecutionQuoteBindingError("approved_notional_usd_missing") from exc

    if not sizing_id:
        raise ExecutionQuoteBindingError("sizing_id_required")
    if not decision_id or not correlation_id:
        raise ExecutionQuoteBindingError("canonical_decision_lineage_required")
    if approved_usd <= 0:
        raise ExecutionQuoteBindingError("approved_notional_usd_invalid")
    return sizing_id, decision_id, correlation_id, approved_usd


async def bind_final_quote_to_execution(
    *,
    rpc_read: Any,
    cfg: Any,
    cache: Any,
    opp: Any,
    decision: Any | None,
    block_number: int,
) -> BoundExecutionQuote | None:
    """Bind canonical USD sizing to the exact raw amount used by execution.

    This adapter deliberately does not create a new sizing identity. It consumes
    the already-attached ``sizing_id`` and approved USD notional, resolves the
    authoritative execution-time quote, converts the approved notional to raw
    units, then requotes the route at that exact raw amount before calldata is
    constructed by the existing execution path.

    Opportunities without Phase-B sizing lineage return ``None`` so legacy and
    non-institutional paths retain their existing behavior. Once sizing lineage
    is present, missing quote/cache/requote truth fails closed.
    """
    sizing_id, decision_id, correlation_id, approved_usd = _lineage(opp, decision)
    if decision is not None:
        decision_meta = getattr(decision, "metadata", None)
        if isinstance(decision_meta, dict):
            if str(decision_meta.get("canonical_decision_id") or decision_id) != decision_id:
                raise ExecutionQuoteBindingError("decision_lineage_conflict")
            decision_correlation = str(decision_meta.get("correlation_id") or "")
            if decision_correlation and decision_correlation != correlation_id:
                raise ExecutionQuoteBindingError("correlation_lineage_conflict")

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
    max_raw = int(getattr(getattr(cfg, "safety", None), "max_borrow_amount", 0) or 0)
    if max_raw > 0 and raw_amount > max_raw:
        raw_amount = max_raw
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
    binding_payload = binding.to_dict()

    meta = getattr(opp, "meta", None)
    if isinstance(meta, dict):
        meta["b4_execution_quote"] = binding_payload
        lineage = meta.get("canonical_lineage")
        if isinstance(lineage, dict):
            lineage["quote_id"] = quote.quote_id
            lineage["raw_amount"] = raw_amount
            lineage["sizing_id"] = sizing_id
            lineage["decision_id"] = decision_id
            lineage["correlation_id"] = correlation_id

    if decision is not None:
        decision_meta = getattr(decision, "metadata", None)
        if isinstance(decision_meta, dict):
            execution_lineage = decision_meta.get("execution_lineage")
            if not isinstance(execution_lineage, dict):
                execution_lineage = {}
            execution_lineage.update(
                {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                    "sizing_id": sizing_id,
                    "quote_id": quote.quote_id,
                    "raw_amount": raw_amount,
                }
            )
            decision_meta["execution_lineage"] = execution_lineage
            decision_meta["quote_id"] = quote.quote_id
            try:
                decision.metadata = decision_meta
            except (AttributeError, TypeError) as exc:
                raise ExecutionQuoteBindingError("decision_metadata_not_mutable") from exc

    return binding
