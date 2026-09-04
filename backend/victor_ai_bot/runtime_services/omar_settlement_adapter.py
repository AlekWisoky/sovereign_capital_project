from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

from victor_ai_bot.omar.lifecycle_bridge import settlement_hook


_SAFE = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except _SAFE:
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except _SAFE:
        return 0.0


def _learning_outcome(*, pending: Mapping[str, Any], decoded: Mapping[str, Any], status: int, tx_hash: str, expected_after: int, realized_after: int, submit_to_receipt_ms: int, result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "settled" if int(status) == 1 else "failed",
        "ok": int(status) == 1,
        "truth_verified": bool(result.get("blockedAutoTrading") is not True),
        "tx_hash": str(tx_hash),
        "realized_pnl_wei": _int(decoded.get("realized_profit_after_gas_wei"),) if decoded.get("realized_profit_after_gas_wei") is not None else int(max(0, realized_after)),
        "realized_profit_after_gas_wei": int(max(0, realized_after)) if int(status) == 1 else 0,
        "realized_profit_after_gas_usd_micro": _int(decoded.get("realized_profit_after_gas_usd_micro")),
        "gas_cost_wei": _int(decoded.get("realized_gas_cost_wei")),
        "slippage_bps": _float(decoded.get("realized_slippage_bps"), pending.get("realized_slippage_bps")),
        "latency_ms": int(submit_to_receipt_ms),
        "amount_in_wei": int(expected_after or pending.get("amount_in") or 0) if not pending.get("amount_in") else int(pending.get("amount_in") or 0),
        "route_id": _text(pending.get("route_id")),
        "opportunity_id": _text(pending.get("opportunity_id")),
    }


def install_receipt_settlement_hook() -> None:
    """Install the OMAR hook at the canonical settlement boundary.

    The wrapper executes only after ReceiptService.synchronize_settlement_accounting
    returns a successful canonical commit. It is intentionally idempotent and
    never changes the settlement result or execution authority.
    """
    from .receipt_service import ReceiptService

    if getattr(ReceiptService.synchronize_settlement_accounting, "_omar_hook_installed", False):
        return

    original = ReceiptService.synchronize_settlement_accounting

    @wraps(original)
    def wrapped(self: Any, runtime: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(self, runtime, *args, **kwargs)
        if not isinstance(result, dict) or not bool(result.get("ok")):
            return result

        pending = _mapping(kwargs.get("pending"))
        decoded = _mapping(kwargs.get("decoded"))
        status = _int(kwargs.get("status"))
        tx_hash = _text(kwargs.get("tx_hash"))
        expected_after = _int(kwargs.get("expected_after"))
        realized_after = _int(kwargs.get("realized_after"))
        submit_to_receipt_ms = _int(kwargs.get("submit_to_receipt_ms"))

        outcome = _learning_outcome(
            pending=pending,
            decoded=decoded,
            status=status,
            tx_hash=tx_hash,
            expected_after=expected_after,
            realized_after=realized_after,
            submit_to_receipt_ms=submit_to_receipt_ms,
            result=result,
        )
        hook_result = settlement_hook(
            runtime,
            pending=pending,
            outcome=outcome,
            committed_record=result,
        )
        enriched = dict(result)
        enriched["omarLearning"] = hook_result
        return enriched

    wrapped._omar_hook_installed = True
    ReceiptService.synchronize_settlement_accounting = wrapped


__all__ = ["install_receipt_settlement_hook"]
