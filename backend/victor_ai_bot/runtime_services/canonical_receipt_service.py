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

    @classmethod
    def _realized_after_usd(cls, decoded: Mapping[str, Any], *, status: int) -> float | None:
        """Return only explicitly verified USD; never infer USD from raw wei."""
        if int(status) != 1:
            return 0.0
        usd_value = cls._usd_from_micro(decoded.get("realized_profit_after_gas_usd_micro"))
        if usd_value is None:
            return None
        return max(0.0, float(usd_value))

    def settled_outcome_truth(
        self, *, status: int, decoded: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Require explicit USD truth for successful USD-denominated settlement."""
        if int(status) != 1:
            return {"ok": True, "reason_code": "ok", "reason_codes": [], "verified": True}
        raw_usd = decoded.get("realized_profit_after_gas_usd_micro")
        usd_value = self._usd_from_micro(raw_usd)
        if raw_usd is not None and raw_usd != "" and usd_value is not None:
            return {"ok": True, "reason_code": "ok", "reason_codes": [], "verified": True}
        reason_code = "settled_usd_truth_unavailable"
        return {
            "ok": False,
            "reason_code": reason_code,
            "reason_codes": [reason_code],
            "verified": False,
        }

    def synchronize_settlement_accounting(self, runtime: Any, **kwargs: Any) -> dict[str, Any]:
        """Refuse USD ledger settlement unless explicit USD receipt truth exists."""
        status = int(kwargs.get("status") or 0)
        decoded = kwargs.get("decoded") or {}
        if status == 1:
            usd_value = self._usd_from_micro(
                decoded.get("realized_profit_after_gas_usd_micro")
                if isinstance(decoded, Mapping)
                else None
            )
            if usd_value is None:
                return self.record_outcome_truth_gap(
                    runtime,
                    tx_hash=str(kwargs.get("tx_hash") or ""),
                    route_id=str(kwargs.get("route_id") or ""),
                    status=status,
                    reason_code="settled_usd_truth_unavailable",
                    pending=(kwargs.get("pending") or {}),
                )
        return super().synchronize_settlement_accounting(runtime, **kwargs)

    def record_capture_outcome(self, runtime: Any, *, pending: Mapping[str, Any], **kwargs: Any) -> None:
        """Do not emit USD capture telemetry from wei-only receipt data."""
        explicit_usd = pending.get("realized_profit_after_gas_usd_micro")
        if explicit_usd is None or explicit_usd == "":
            return
        return super().record_capture_outcome(runtime, pending=pending, **kwargs)

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
