from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

from victor_ai_bot.omar.lifecycle_bridge import settlement_hook


_SAFE = (AttributeError, KeyError, TypeError, ValueError, RuntimeError)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _int(*values: Any) -> int:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return int(value)
        except _SAFE:
            continue
    return 0


def _float(*values: Any) -> float:
    for value in values:
        if value in (None, ""):
            continue
        try:
            return float(value)
        except _SAFE:
            continue
    return 0.0


def _runtime_capital_snapshot(runtime: Any) -> dict[str, Any]:
    try:
        reader = getattr(runtime, "capital_engine_state", None)
        if callable(reader):
            value = reader()
            if isinstance(value, Mapping):
                return dict(value)
    except _SAFE:
        pass
    return {}


def _runtime_prime_snapshot(runtime: Any, pending: Mapping[str, Any]) -> dict[str, Any]:
    prime = _mapping(pending.get("internal_prime") or pending.get("internalPrime"))
    if prime:
        return prime
    service = getattr(runtime, "_internal_prime", None)
    if service is None:
        return {}
    snapshot: dict[str, Any] = {}
    try:
        state_fn = getattr(service, "state", None)
        if callable(state_fn):
            value = state_fn()
            if isinstance(value, Mapping):
                snapshot.update(value)
    except _SAFE:
        pass
    for attr in ("authority_id", "authorityId", "loan_id", "loanId"):
        try:
            value = getattr(service, attr, None)
        except _SAFE:
            value = None
        if value not in (None, ""):
            snapshot[attr] = value
    return snapshot


def _learning_outcome(
    *,
    pending: Mapping[str, Any],
    decoded: Mapping[str, Any],
    status: int,
    tx_hash: str,
    expected_after: int,
    realized_after: int,
    submit_to_receipt_ms: int,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": "settled" if int(status) == 1 else "failed",
        "ok": int(status) == 1,
        "truth_verified": bool(result.get("blockedAutoTrading") is not True),
        "tx_hash": str(tx_hash),
        "realized_pnl_wei": _int(
            decoded.get("realized_profit_after_gas_wei"), realized_after
        ),
        "realized_profit_after_gas_wei": int(max(0, realized_after)) if int(status) == 1 else 0,
        "realized_profit_after_gas_usd_micro": _int(
            decoded.get("realized_profit_after_gas_usd_micro")
        ),
        "gas_cost_wei": _int(
            decoded.get("realized_gas_cost_wei"), decoded.get("gas_cost_wei")
        ),
        "slippage_bps": _float(
            decoded.get("realized_slippage_bps"),
            pending.get("realized_slippage_bps"),
        ),
        "latency_ms": int(submit_to_receipt_ms),
        "amount_in_wei": _int(
            pending.get("amount_in"), pending.get("amount_in_wei"), expected_after
        ),
        "route_id": _text(pending.get("route_id")),
        "opportunity_id": _text(pending.get("opportunity_id")),
    }


def install_receipt_settlement_hook() -> None:
    """Install OMAR at the canonical settlement boundary.

    The wrapper runs only after ReceiptService.synchronize_settlement_accounting
    returns a successful canonical commit. It never changes settlement authority
    or the returned accounting result; it only appends OMAR learning metadata.
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
        capital_state = _runtime_capital_snapshot(runtime)
        if capital_state:
            pending["capital_engine_state"] = capital_state
        prime_state = _runtime_prime_snapshot(runtime, pending)
        if prime_state:
            pending["internal_prime"] = prime_state
        if "capital_admission" not in pending and isinstance(result.get("capitalAdmission"), Mapping):
            pending["capital_admission"] = dict(result.get("capitalAdmission") or {})

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
