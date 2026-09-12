from __future__ import annotations

import hashlib
from typing import Any, Mapping

from ..money_loop_accounting import MoneyLoopAccounting, SettledReceiptEconomics
from .capital_write_service import CapitalWriteService


class _CanonicalBankrollProxy:
    def __init__(self, bankroll: Any, economics: SettledReceiptEconomics) -> None:
        self._bankroll = bankroll
        self._economics = economics

    def project_trade_state(self, **_: Any) -> dict[str, Any]:
        return dict(self._bankroll.project_settled_outcome_state(self._economics) or {})

    def __getattr__(self, name: str) -> Any:
        return getattr(self._bankroll, name)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _outcome_id(lineage: Mapping[str, Any], receipt_id: str) -> str:
    """Return one idempotent outcome identity for the persisted settlement."""
    existing = _text(lineage.get("outcome_id"))
    if existing:
        return existing
    canonical = "|".join(
        _text(lineage.get(key))
        for key in (
            "decision_id",
            "correlation_id",
            "sizing_id",
            "execution_id",
            "opportunity_id",
            "route_id",
            "action",
        )
    )
    digest = hashlib.sha256(f"{canonical}|{_text(receipt_id)}".encode("utf-8")).hexdigest()[:24]
    return f"outcome_{digest}"


class CanonicalCapitalWriteService(CapitalWriteService):
    """Production capital writer using canonical signed settled economics."""

    def _annotate_settlement_payload(
        self, runtime: Any, tx_payload: Mapping[str, Any], *, receipt_id: str, status: int,
        amount_in: int, submit_to_receipt_ms: int, route_id: str, gas_cost_wei: int,
        realized_after_usd: float, net_realized_usd: float,
        borrowing: Mapping[str, Any], outcome_truth_verified: bool,
    ) -> dict[str, Any]:
        payload = dict(tx_payload or {})
        metadata = _dict(payload.get("metadata"))
        context = _dict(getattr(runtime, "_canonical_settlement_lineage", None))
        lineage = _dict(context.get("canonical_lineage"))
        decision_id = _text(context.get("decision_id") or lineage.get("decision_id"))
        correlation_id = _text(context.get("correlation_id") or lineage.get("correlation_id"))
        sizing_id = _text(context.get("sizing_id") or lineage.get("sizing_id"))
        execution_id = _text(context.get("execution_id") or lineage.get("execution_id"))
        opportunity_id = _text(context.get("opportunity_id") or lineage.get("opportunity_id"))
        resolved_route_id = _text(context.get("route_id") or route_id or lineage.get("route_id"))
        action = _text(context.get("action") or lineage.get("action"))
        outcome_id = _text(context.get("outcome_id"))
        if not outcome_id and bool(outcome_truth_verified):
            outcome_id = _outcome_id(
                {
                    "decision_id": decision_id,
                    "correlation_id": correlation_id,
                    "sizing_id": sizing_id,
                    "execution_id": execution_id,
                    "opportunity_id": opportunity_id,
                    "route_id": resolved_route_id,
                    "action": action,
                },
                receipt_id,
            )
        if bool(outcome_truth_verified):
            required = {
                "decision_id": decision_id,
                "correlation_id": correlation_id,
                "sizing_id": sizing_id,
                "execution_id": execution_id,
                "receipt_id": _text(receipt_id),
                "outcome_id": outcome_id,
                "opportunity_id": opportunity_id,
                "route_id": resolved_route_id,
                "action": action,
            }
            missing = [key for key, value in required.items() if not _text(value)]
            if missing:
                raise ValueError(f"canonical_settlement_lineage_incomplete:{','.join(missing)}")

        canonical_lineage = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "sizing_id": sizing_id,
            "execution_id": execution_id,
            "receipt_id": _text(receipt_id),
            "outcome_id": outcome_id,
            "opportunity_id": opportunity_id,
            "route_id": resolved_route_id,
            "action": action,
        }
        canonical_lineage.update(_dict(context.get("canonical_lineage")))
        canonical_lineage.update({"receipt_id": _text(receipt_id), "outcome_id": outcome_id})
        metadata.update(
            {
                "canonical_decision_id": decision_id,
                "decision_id": decision_id,
                "correlation_id": correlation_id,
                "sizing_id": sizing_id,
                "execution_id": execution_id,
                "receipt_id": _text(receipt_id),
                "outcome_id": outcome_id,
                "opportunity_id": opportunity_id,
                "route_id": resolved_route_id,
                "action": action,
                "canonical_lineage": canonical_lineage,
                "execution_lineage": _dict(context.get("execution_lineage")),
                "expected_net_usd": context.get("expected_net_usd"),
                "realized_net_usd": float(net_realized_usd),
                "gas_cost_wei": int(gas_cost_wei),
                "gas_cost_usd": metadata.get("gas_cost_usd"),
                "slippage_bps": context.get("slippage_bps"),
                "latency_ms": int(context.get("latency_ms") or submit_to_receipt_ms or 0),
                "prime_economics": _dict(context.get("prime_economics")),
                "borrowing_economics": _dict(borrowing),
                "capital_demand": _dict(context.get("capital_demand")),
                "capital_authority": _dict(context.get("capital_authority")),
                "internal_prime_authority": _dict(context.get("internal_prime_authority")),
                "settlement_verified": bool(outcome_truth_verified),
                "truth_verified": bool(outcome_truth_verified),
                "settlement_status": "settled" if int(status) == 1 else "failed",
                "amount_in_wei": int(amount_in),
                "net_realized_usd": float(net_realized_usd),
                "realized_after_gas_usd": float(realized_after_usd),
            }
        )
        payload["metadata"] = metadata
        return payload

    def commit_receipt_settlement(
        self,
        runtime: Any,
        *,
        tx_payload: Mapping[str, Any],
        tx_lines: list[dict[str, Any]] | None,
        receipt_id: str,
        status: int,
        amount_in: int,
        submit_to_receipt_ms: int,
        route_id: str,
        route_family: str,
        strategy_family: str,
        capture_lane_pending: str,
        realized_after_usd: float,
        borrow_cost_usd: float,
        net_realized_usd: float,
        gas_cost_wei: int,
        profitability_chain: Mapping[str, Any],
        borrowing: Mapping[str, Any],
        loan_result: Mapping[str, Any],
        outcome_truth_verified: bool,
        prime_transition: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        tx_payload = self._annotate_settlement_payload(
            runtime,
            tx_payload,
            receipt_id=str(receipt_id or ""),
            status=int(status),
            amount_in=int(amount_in),
            submit_to_receipt_ms=int(submit_to_receipt_ms),
            route_id=str(route_id or ""),
            gas_cost_wei=int(gas_cost_wei),
            realized_after_usd=float(realized_after_usd),
            net_realized_usd=float(net_realized_usd),
            borrowing=borrowing,
            outcome_truth_verified=bool(outcome_truth_verified),
        )
        bankroll = getattr(runtime, "_bankroll", None)
        economics = MoneyLoopAccounting.from_settlement_payload(tx_payload, receipt_id=str(receipt_id or ""))
        if not bool(outcome_truth_verified) or bankroll is None:
            return super().commit_receipt_settlement(runtime, tx_payload=tx_payload, tx_lines=tx_lines, receipt_id=receipt_id, status=status, amount_in=amount_in, submit_to_receipt_ms=submit_to_receipt_ms, route_id=route_id, route_family=route_family, strategy_family=strategy_family, capture_lane_pending=capture_lane_pending, realized_after_usd=realized_after_usd, borrow_cost_usd=borrow_cost_usd, net_realized_usd=net_realized_usd, gas_cost_wei=gas_cost_wei, profitability_chain=profitability_chain, borrowing=borrowing, loan_result=loan_result, outcome_truth_verified=outcome_truth_verified, prime_transition=prime_transition)
        original_bankroll = runtime._bankroll
        runtime._bankroll = _CanonicalBankrollProxy(original_bankroll, economics)
        try:
            result = super().commit_receipt_settlement(runtime, tx_payload=tx_payload, tx_lines=tx_lines, receipt_id=receipt_id, status=status, amount_in=amount_in, submit_to_receipt_ms=submit_to_receipt_ms, route_id=route_id, route_family=route_family, strategy_family=strategy_family, capture_lane_pending=capture_lane_pending, realized_after_usd=realized_after_usd, borrow_cost_usd=borrow_cost_usd, net_realized_usd=net_realized_usd, gas_cost_wei=gas_cost_wei, profitability_chain=profitability_chain, borrowing=borrowing, loan_result=loan_result, outcome_truth_verified=outcome_truth_verified, prime_transition=prime_transition)
        finally:
            runtime._bankroll = original_bankroll
        result = dict(result or {})
        result["settledEconomics"] = economics.to_dict()
        result["outcome_id"] = _text(tx_payload.get("metadata", {}).get("outcome_id"))
        result["canonical_lineage"] = _dict(tx_payload.get("metadata", {}).get("canonical_lineage"))
        return result
