from __future__ import annotations

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


class CanonicalCapitalWriteService(CapitalWriteService):
    """Production capital writer using canonical signed settled economics."""

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
        bankroll = getattr(runtime, "_bankroll", None)
        economics = MoneyLoopAccounting.from_settlement_payload(
            tx_payload, receipt_id=str(receipt_id or "")
        )
        if not bool(outcome_truth_verified) or bankroll is None:
            return super().commit_receipt_settlement(
                runtime,
                tx_payload=tx_payload,
                tx_lines=tx_lines,
                receipt_id=receipt_id,
                status=status,
                amount_in=amount_in,
                submit_to_receipt_ms=submit_to_receipt_ms,
                route_id=route_id,
                route_family=route_family,
                strategy_family=strategy_family,
                capture_lane_pending=capture_lane_pending,
                realized_after_usd=realized_after_usd,
                borrow_cost_usd=borrow_cost_usd,
                net_realized_usd=net_realized_usd,
                gas_cost_wei=gas_cost_wei,
                profitability_chain=profitability_chain,
                borrowing=borrowing,
                loan_result=loan_result,
                outcome_truth_verified=outcome_truth_verified,
                prime_transition=prime_transition,
            )
        original_bankroll = runtime._bankroll
        runtime._bankroll = _CanonicalBankrollProxy(original_bankroll, economics)
        try:
            result = super().commit_receipt_settlement(
                runtime,
                tx_payload=tx_payload,
                tx_lines=tx_lines,
                receipt_id=receipt_id,
                status=status,
                amount_in=amount_in,
                submit_to_receipt_ms=submit_to_receipt_ms,
                route_id=route_id,
                route_family=route_family,
                strategy_family=strategy_family,
                capture_lane_pending=capture_lane_pending,
                realized_after_usd=realized_after_usd,
                borrow_cost_usd=borrow_cost_usd,
                net_realized_usd=net_realized_usd,
                gas_cost_wei=gas_cost_wei,
                profitability_chain=profitability_chain,
                borrowing=borrowing,
                loan_result=loan_result,
                outcome_truth_verified=outcome_truth_verified,
                prime_transition=prime_transition,
            )
        finally:
            runtime._bankroll = original_bankroll
        result = dict(result or {})
        result["settledEconomics"] = economics.to_dict()
        return result
