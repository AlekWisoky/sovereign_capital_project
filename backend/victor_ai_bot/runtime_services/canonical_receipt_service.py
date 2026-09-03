from __future__ import annotations

from typing import Any, Mapping

from ..money_loop_accounting import MoneyLoopAccounting
from .receipt_service import ReceiptService

_SAFE = (AttributeError, ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError)


class CanonicalReceiptService(ReceiptService):
    """Receipt service that owns canonical settlement-to-learning handoff."""

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

    def synchronize_settlement_accounting(
        self, runtime: Any, **kwargs: Any
    ) -> dict[str, Any]:
        """Commit canonical settlement, then hand that exact settlement to OMAR."""
        result = dict(super().synchronize_settlement_accounting(runtime, **kwargs) or {})
        if not bool(result.get("ok")) or bool(result.get("duplicate")):
            return result

        pending = dict(kwargs.get("pending") or {})
        receipt_id = str(kwargs.get("tx_hash") or result.get("receiptId") or "")
        lineage = dict(pending.get("canonical_lineage") or {})
        settlement_id = str(
            lineage.get("settlement_id")
            or result.get("transactionId")
            or result.get("transaction_id")
            or ""
        )
        decoded = dict(kwargs.get("decoded") or {})
        gas_cost_wei = max(0, int(decoded.get("realized_gas_cost_wei") or 0))
        realized_after_wei = max(0, int(kwargs.get("realized_after") or 0))
        outcome = {
            "status": str(
                result.get("status")
                or (
                    "settled"
                    if int(kwargs.get("status") or 0) == 1
                    else "failed"
                )
            ),
            "ok": int(kwargs.get("status") or 0) == 1,
            "tx_hash": receipt_id,
            "receipt_id": receipt_id,
            "transaction_id": str(result.get("transactionId") or ""),
            "settlement_id": settlement_id,
            "route_id": str(kwargs.get("route_id") or ""),
            "realized_net_usd": float(result.get("netRealizedUsd") or 0.0),
            "expected_net_usd": float(kwargs.get("expected_after") or 0.0),
            # The OMAR loop subtracts realized_gas_wei from realized_pnl_wei, so
            # pass gross realized profit here to produce the canonical post-gas reward.
            "realized_pnl_wei": int(realized_after_wei + gas_cost_wei),
            "realized_gas_wei": int(gas_cost_wei),
            "latency_ms": int(kwargs.get("submit_to_receipt_ms") or 0),
            "truth_verified": bool(kwargs.get("outcome_truth_verified", True)),
        }
        try:
            from ..omar.lifecycle_bridge import _observe_settled_outcome

            learning = _observe_settled_outcome(
                runtime, pending=pending, outcome=outcome
            )
            result["learningSync"] = dict(learning or {})
            result["closedLoop"] = {
                "settlementAccounting": True,
                "learningRecorded": (
                    bool(learning.get("ok"))
                    if isinstance(learning, Mapping)
                    else False
                ),
                "completed": (
                    bool(learning.get("ok"))
                    if isinstance(learning, Mapping)
                    else False
                ),
                "reasonCodes": (
                    list(learning.get("reason_codes") or [])
                    if isinstance(learning, Mapping)
                    else ["omar_learning_callback_failed"]
                ),
            }
        except _SAFE as exc:
            result["learningSync"] = {
                "ok": False,
                "eligible_for_learning": False,
                "reason_code": f"omar_learning_callback_failed:{type(exc).__name__}",
            }
            result["closedLoop"] = {
                "settlementAccounting": True,
                "learningRecorded": False,
                "completed": False,
                "reasonCodes": ["omar_learning_callback_failed"],
            }
        return result

    def update_decision_learning(
        self,
        runtime: Any,
        *,
        route_id: str,
        rl_state: str,
        rl_action: int,
        amount_in: int,
        expected_after: int,
        realized_after: int,
        status: int,
        tx_hash: str,
        mode: str,
        latency_ms: int,
        submit_to_receipt_ms: int,
        aqe_action: str,
        pending: Mapping[str, Any],
        reward_trace: Mapping[str, Any],
    ) -> None:
        economics = self._settled_economics(runtime, tx_hash)
        enriched_trace = dict(reward_trace or {})
        if economics:
            enriched_trace.update(
                {
                    "settled_net_pnl_usd": float(
                        economics.get("signed_pnl_usd") or 0.0
                    ),
                    "settled_loss_usd": float(economics.get("loss_usd") or 0.0),
                    "reinvestable_profit_usd": float(
                        economics.get("reinvestable_profit_usd") or 0.0
                    ),
                    "settled_receipt_id": str(
                        economics.get("receipt_id") or tx_hash
                    ),
                    "settled_transaction_id": str(
                        economics.get("transaction_id") or ""
                    ),
                    "settlement_source": str(
                        economics.get("source") or "canonical_receipt_settlement"
                    ),
                }
            )
        return super().update_decision_learning(
            runtime,
            route_id=route_id,
            rl_state=rl_state,
            rl_action=rl_action,
            amount_in=amount_in,
            expected_after=expected_after,
            realized_after=realized_after,
            status=status,
            tx_hash=tx_hash,
            mode=mode,
            latency_ms=latency_ms,
            submit_to_receipt_ms=submit_to_receipt_ms,
            aqe_action=aqe_action,
            pending=pending,
            reward_trace=enriched_trace,
        )
