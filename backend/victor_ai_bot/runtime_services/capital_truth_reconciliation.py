from __future__ import annotations

from typing import Any, Dict


def _int_like(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_like(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _append_reason(reasons: list[str], reason: str) -> None:
    reason = str(reason or "").strip()
    if reason and reason not in reasons:
        reasons.append(reason)


def build_capital_truth_reconciliation_payload(
    *,
    treasury_balance_wei: int,
    deployed_capital_wei: int,
    withdrawable_balance_wei: int,
    realized_profit_wei: int,
    prime_state_ready: bool,
    prime_state_reason: str,
    borrowed_usd: float,
    prime_capacity_usd: float,
    prime_utilization: float,
    prime_family_exposure: Dict[str, Any],
    prime_open_loan_count: int,
    reserved_collateral_usd: float,
    collateralization_ratio: float,
    prime_journal_reconciliation: Dict[str, Any],
    prime_ledger_reconciliation: Dict[str, Any],
    receipt_settlement: Dict[str, Any],
    receipt_outcome_truth: Dict[str, Any],
    receipt_outcome_truth_degraded: bool,
    receipt_outcome_truth_reason_code: str,
    convergence: Dict[str, Any],
    auto_reinvest: bool,
    reinvest_rate_pct: float,
    launch_mode: str,
    capital_engine_present: bool,
    recovery_history: Dict[str, Any],
    profit_destination: str,
) -> Dict[str, Any]:
    status = "ok"
    reasons: list[str] = []

    if treasury_balance_wei < deployed_capital_wei:
        status = "degraded"
        _append_reason(reasons, "treasury_balance_below_deployable")
    if withdrawable_balance_wei > realized_profit_wei:
        status = "degraded"
        _append_reason(reasons, "withdrawable_exceeds_realized_profit")
    if not bool(prime_state_ready):
        status = "degraded"
        if prime_state_reason:
            _append_reason(reasons, prime_state_reason)
    if prime_capacity_usd > 0.0 and borrowed_usd - prime_capacity_usd > 1e-6:
        status = "degraded"
        _append_reason(reasons, "internal_prime_capacity_exceeded")
    if prime_capacity_usd > 0.0:
        expected_utilization = max(0.0, min(1.0, borrowed_usd / max(1.0, prime_capacity_usd)))
        if abs(expected_utilization - prime_utilization) > 1e-6:
            status = "degraded"
            _append_reason(reasons, "internal_prime_utilization_mismatch")
    max_family_exposure_usd = max(
        (_float_like(v) for v in dict(prime_family_exposure or {}).values()), default=0.0
    )
    if max_family_exposure_usd - max(0.0, borrowed_usd) > 1e-6:
        status = "degraded"
        _append_reason(reasons, "internal_prime_family_exposure_exceeds_borrowed")
    if int(prime_open_loan_count) > 0 and borrowed_usd <= 0.0:
        status = "degraded"
        _append_reason(reasons, "internal_prime_open_loans_without_borrowed")
    if receipt_outcome_truth_degraded:
        status = "degraded"
        _append_reason(reasons, receipt_outcome_truth_reason_code)

    if not bool((prime_journal_reconciliation or {}).get("ok", False)):
        status = "degraded"
        for reason in list((prime_journal_reconciliation or {}).get("reasons") or []):
            _append_reason(reasons, str(reason))

    if not bool((prime_ledger_reconciliation or {}).get("ok", False)):
        status = "degraded"
        for reason in list((prime_ledger_reconciliation or {}).get("reasons") or []):
            _append_reason(reasons, str(reason))

    if not bool((receipt_settlement or {}).get("ok", False)):
        status = "degraded"
        for reason in list((receipt_settlement or {}).get("reason_codes") or []):
            _append_reason(reasons, str(reason))

    if not bool((convergence or {}).get("ok", False)):
        status = "degraded"
        for reason in list((convergence or {}).get("reason_codes") or []):
            _append_reason(reasons, str(reason))

    status_reason_code = reasons[0] if reasons else "ok"
    freshness = {
        "class": str((convergence or {}).get("freshness_class") or "unknown"),
        "reason_codes": list((convergence or {}).get("freshness_reason_codes") or []),
        "reference_ts_ms": int((convergence or {}).get("reference_ts_ms") or 0),
        "newest_source_ts_ms": int((convergence or {}).get("newest_source_ts_ms") or 0),
        "source_spread_ms": int((convergence or {}).get("source_spread_ms") or 0),
    }
    reconciliation = {
        "ledger_stale": bool(
            "ledger_freshness_stale" in list((convergence or {}).get("reason_codes") or [])
        ),
        "internal_prime_borrowed_usd": round(_float_like(borrowed_usd), 6),
        "internal_prime_capacity_usd": round(_float_like(prime_capacity_usd), 6),
        "internal_prime_utilization": round(_float_like(prime_utilization), 6),
        "internal_prime_family_exposure": {
            str(k): round(_float_like(v), 8) for k, v in dict(prime_family_exposure or {}).items()
        },
        "internal_prime_open_loan_count": _int_like(prime_open_loan_count),
        "internal_prime_reserved_collateral_usd": round(_float_like(reserved_collateral_usd), 6),
        "internal_prime_collateralization_ratio": round(_float_like(collateralization_ratio), 6),
        "internal_prime_journal": dict(prime_journal_reconciliation or {}),
        "internal_prime_ledger": dict(prime_ledger_reconciliation or {}),
        "auto_reinvest_enabled": bool(auto_reinvest),
        "reinvest_rate_pct": round(_float_like(reinvest_rate_pct), 6),
        "launch_mode": str(launch_mode or ""),
        "capital_engine_present": bool(capital_engine_present),
        "capital_convergence": dict(convergence or {}),
        "capital_truth_history": dict(recovery_history or {}),
        "receipt_outcome_truth": {
            "is_degraded": bool(receipt_outcome_truth_degraded),
            "reason_code": (
                str(receipt_outcome_truth_reason_code or "settled_profit_truth_unavailable")
                if receipt_outcome_truth_degraded
                else "ok"
            ),
            "updated_ts_ms": int((receipt_outcome_truth or {}).get("updated_ts_ms") or 0),
            "degraded_since_ts_ms": int((receipt_outcome_truth or {}).get("degraded_since_ts_ms") or 0),
            "last_recovered_ts_ms": int((receipt_outcome_truth or {}).get("last_recovered_ts_ms") or 0),
            "degraded_count": int((receipt_outcome_truth or {}).get("degraded_count") or 0),
            "last_healthy_ts_ms": int((receipt_outcome_truth or {}).get("last_healthy_ts_ms") or 0),
        },
        "receipt_settlement": dict(receipt_settlement or {}),
    }
    withdrawal_available = bool(withdrawable_balance_wei > 0 and status == "ok")
    withdrawal = {
        "available": withdrawal_available,
        "reason_code": (
            "ok"
            if withdrawal_available
            else (status_reason_code if status_reason_code != "ok" else "no_withdrawable_balance")
        ),
        "reason_codes": (
            ["ok"]
            if withdrawal_available
            else ([status_reason_code] if status_reason_code != "ok" else ["no_withdrawable_balance"])
        ),
        "previewable": bool(withdrawable_balance_wei > 0),
        "profit_destination": str(profit_destination or ""),
    }
    return {
        "status": status,
        "status_reason_code": status_reason_code,
        "reasons": list(reasons),
        "freshness": freshness,
        "reconciliation": reconciliation,
        "withdrawal": withdrawal,
    }
