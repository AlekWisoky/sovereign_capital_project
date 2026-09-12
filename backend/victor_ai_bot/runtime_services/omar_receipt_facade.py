from __future__ import annotations

from typing import Any, Mapping

from ..omar.lifecycle_bridge import _observe_settled_outcome
from .canonical_settlement_interface import canonical_settled_outcome
from .runtime_receipt_facade import RuntimeReceiptFacade


_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


class OmarReceiptFacade(RuntimeReceiptFacade):
    """Receipt facade with direct, post-persistence OMAR learning integration.

    The receipt lifecycle remains authoritative for settlement accounting. This
    facade only carries the already-established canonical lineage into the
    existing capital writer and then reads that physical ledger row back for
    downstream learning.
    """

    def canonical_settled_outcome(self, **kwargs: Any) -> dict[str, Any] | None:
        return canonical_settled_outcome(self, **kwargs)

    def synchronize_settlement_accounting(self, runtime: Any, *, pending: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Expose complete decision/execution/sizing lineage to the canonical writer."""
        source = _dict(pending)
        context = _dict(source.get("pending_context"))
        execution_lineage = _dict(context.get("execution_lineage"))
        canonical_lineage = _dict(source.get("canonical_lineage"))
        brain = _dict(source.get("brain"))

        decision_id = _text(
            source.get("canonical_decision_id")
            or canonical_lineage.get("decision_id")
            or execution_lineage.get("decision_id")
            or brain.get("canonical_decision_id")
        )
        correlation_id = _text(
            source.get("correlation_id")
            or canonical_lineage.get("correlation_id")
            or execution_lineage.get("correlation_id")
            or brain.get("correlation_id")
        )
        sizing_id = _text(
            source.get("sizing_id")
            or canonical_lineage.get("sizing_id")
            or execution_lineage.get("sizing_id")
            or brain.get("sizing_id")
        )
        execution_id = _text(
            source.get("execution_id")
            or canonical_lineage.get("execution_id")
            or execution_lineage.get("execution_id")
            or brain.get("execution_id")
        )
        opportunity_id = _text(source.get("opportunity_id"))
        route_id = _text(source.get("route_id"))
        action = _text(source.get("action") or brain.get("omar_action") or brain.get("aqe_action"))
        if not action:
            action = _text(context.get("action"))

        canonical = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "sizing_id": sizing_id,
            "execution_id": execution_id,
            "receipt_id": _text(kwargs.get("tx_hash")),
            "outcome_id": _text(source.get("outcome_id")),
            "opportunity_id": opportunity_id,
            "route_id": route_id,
            "action": action,
        }
        canonical.update(canonical_lineage)
        canonical.update({"decision_id": decision_id, "correlation_id": correlation_id, "sizing_id": sizing_id, "execution_id": execution_id, "receipt_id": _text(kwargs.get("tx_hash")), "opportunity_id": opportunity_id, "route_id": route_id, "action": action})
        source["canonical_decision_id"] = decision_id
        source["correlation_id"] = correlation_id
        source["sizing_id"] = sizing_id
        source["execution_id"] = execution_id
        source["opportunity_id"] = opportunity_id
        source["route_id"] = route_id
        source["action"] = action
        source["canonical_lineage"] = canonical

        # Keep the decision-time economic/authority snapshot attached to the
        # physical settlement without making any of it an authorization source.
        expected_net = source.get("expected_net_usd")
        if expected_net in (None, ""):
            expected_net = context.get("expected_net_usd")
        if expected_net not in (None, ""):
            source["expected_net_usd"] = expected_net
        source["capital_demand"] = _dict(source.get("capital_demand") or context.get("capital_demand"))
        source["capital_authority"] = _dict(source.get("capital_authority") or context.get("capital_authority"))
        source["internal_prime_authority"] = _dict(
            source.get("internal_prime_authority") or context.get("internal_prime_authority")
        )
        source["prime_economics"] = _dict(source.get("prime_economics") or context.get("prime_economics"))
        source["operator_intent"] = _dict(
            source.get("operator_intent") or canonical.get("operator_intent") or context.get("operator_intent")
        )
        source["intent_fingerprint"] = _text(
            source.get("intent_fingerprint") or canonical.get("intent_fingerprint") or context.get("intent_fingerprint")
        )

        runtime._canonical_settlement_lineage = {
            **canonical,
            "canonical_lineage": canonical,
            "expected_net_usd": source.get("expected_net_usd"),
            "capital_demand": source.get("capital_demand"),
            "capital_authority": source.get("capital_authority"),
            "internal_prime_authority": source.get("internal_prime_authority"),
            "prime_economics": source.get("prime_economics"),
            "operator_intent": source.get("operator_intent"),
            "intent_fingerprint": source.get("intent_fingerprint"),
            "latency_ms": source.get("latency_ms"),
            "slippage_bps": source.get("slippage_bps"),
        }
        try:
            return dict(super().synchronize_settlement_accounting(runtime, pending=source, **kwargs) or {})
        finally:
            try:
                delattr(runtime, "_canonical_settlement_lineage")
            except _SAFE:
                pass

    def _safe_finalize_receipt_side_effects(self, *args: Any, **kwargs: Any) -> None:
        super()._safe_finalize_receipt_side_effects(*args, **kwargs)
        try:
            pending = kwargs.get("pending")
            tx_hash = str(kwargs.get("tx_hash") or "")
            if not isinstance(pending, dict) or not tx_hash:
                return
            sync = dict(getattr(self, "_last_settlement_sync", {}) or {})
            if not bool(sync.get("ok", False)):
                return
            execution_lineage = _dict(
                _dict(pending.get("pending_context")).get("execution_lineage")
            )
            execution_id = _text(
                pending.get("execution_id")
                or _dict(pending.get("canonical_lineage")).get("execution_id")
                or execution_lineage.get("execution_id")
                or _dict(pending.get("brain")).get("execution_id")
            )
            outcome = self.canonical_settled_outcome(
                tx_hash=tx_hash,
                decision_id=str(pending.get("canonical_decision_id") or ""),
                correlation_id=str(pending.get("correlation_id") or ""),
                opportunity_id=str(pending.get("opportunity_id") or ""),
                execution_id=execution_id,
            )
            if outcome is not None:
                _observe_settled_outcome(self, pending=pending, outcome=outcome)
        except _SAFE:
            # OMAR is downstream learning; settlement truth is never rolled back
            # or masked because an advisory learning update cannot be recorded.
            return
