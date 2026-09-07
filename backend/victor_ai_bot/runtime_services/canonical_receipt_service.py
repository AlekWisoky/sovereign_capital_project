from __future__ import annotations

from typing import Any, Mapping

from ..money_loop_accounting import MoneyLoopAccounting
from .receipt_service import ReceiptService

class CanonicalReceiptService(ReceiptService):
    """Receipt service that attributes learning to canonical settled economics."""
    @staticmethod
    def _settled_economics(runtime: Any, tx_hash: str) -> dict[str, Any]:
        ledger = getattr(runtime, "_ledger", None)
        if ledger is None or not hasattr(ledger, "transactions_all"):
            return {}
        try:
            for row in reversed(list(ledger.transactions_all() or [])):
                if not isinstance(row, Mapping):
                    continue
                if str(row.get("receipt_id") or "") != str(tx_hash or ""):
                    continue
                if str(row.get("tx_type") or "") != "receipt_settlement":
                    continue
                return MoneyLoopAccounting.from_ledger_transaction(row).to_dict()
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}
        return {}

    def update_decision_learning(self, runtime: Any, *, route_id: str, rl_state: str, rl_action: int, amount_in: int, expected_after: int, realized_after: int, status: int, tx_hash: str, mode: str, latency_ms: int, submit_to_receipt_ms: int, aqe_action: str, pending: Mapping[str, Any], reward_trace: Mapping[str, Any]) -> None:
        economics = self._settled_economics(runtime, tx_hash)
        enriched_trace = dict(reward_trace or {})
        if economics:
            enriched_trace.update({
                "settled_net_pnl_usd": float(economics.get("signed_pnl_usd") or 0.0),
                "settled_loss_usd": float(economics.get("loss_usd") or 0.0),
                "reinvestable_profit_usd": float(economics.get("reinvestable_profit_usd") or 0.0),
                "settled_receipt_id": str(economics.get("receipt_id") or tx_hash),
                "settled_transaction_id": str(economics.get("transaction_id") or ""),
                "settlement_source": str(economics.get("source") or "canonical_receipt_settlement"),
            })
        return super().update_decision_learning(runtime, route_id=route_id, rl_state=rl_state, rl_action=rl_action, amount_in=amount_in, expected_after=expected_after, realized_after=realized_after, status=status, tx_hash=tx_hash, mode=mode, latency_ms=latency_ms, submit_to_receipt_ms=submit_to_receipt_ms, aqe_action=aqe_action, pending=pending, reward_trace=enriched_trace)
