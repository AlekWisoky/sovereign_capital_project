from __future__ import annotations

from typing import Any, Dict


def _float_like(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _int_like(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


from ..domain_errors import ReconciliationError
from .ledger import TreasuryLedger


def reconcile_balances(
    ledger: TreasuryLedger,
    external_balances: Dict[str, float] | None = None,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    ledger_bal = ledger.balances()
    ext = {str(k): float(v) for k, v in dict(external_balances or {}).items()}
    keys = sorted(set(ledger_bal) | set(ext))
    deltas = {k: round(float(ext.get(k, 0.0)) - float(ledger_bal.get(k, 0.0)), 8) for k in keys}
    ok = all(abs(v) < 1e-6 for v in deltas.values())
    if strict and not ok:
        raise ReconciliationError("reconciliation_failed", reason_code="reconciliation_failed")
    return {"ledgerBalances": ledger_bal, "externalBalances": ext, "deltas": deltas, "ok": ok}


def _normalized_prime_loan_metadata(
    payload: Dict[str, Any] | None, *, status: str | None = None
) -> Dict[str, Any]:
    data = dict(payload or {})
    loan_status = str(status or data.get("status") or "open")
    return {
        "loanId": str(data.get("loan_id") or data.get("loanId") or ""),
        "status": loan_status,
        "family": str(data.get("family") or ""),
        "asset": str(data.get("asset") or ""),
        "notionalUsd": round(_float_like(data.get("notional_usd") or data.get("notionalUsd")), 8),
        "collateralReservedUsd": round(
            _float_like(data.get("collateral_reserved_usd") or data.get("collateralReservedUsd")),
            8,
        ),
        "collateralRatio": round(
            _float_like(data.get("collateral_ratio") or data.get("collateralRatio")), 8
        ),
        "collateralHaircutPct": round(
            _float_like(data.get("collateral_haircut_pct") or data.get("collateralHaircutPct")),
            8,
        ),
        "collateralEfficiency": round(
            _float_like(data.get("collateral_efficiency") or data.get("collateralEfficiency")),
            8,
        ),
    }


def _state_active_prime_loans(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    active: Dict[str, Dict[str, Any]] = {}
    for row in list(state.get("openLoans") or []):
        if not isinstance(row, dict):
            continue
        normalized = _normalized_prime_loan_metadata(row, status="open")
        loan_id = normalized["loanId"]
        if loan_id:
            active[loan_id] = normalized
    for row in list(state.get("disputedLoans") or []):
        if not isinstance(row, dict):
            continue
        normalized = _normalized_prime_loan_metadata(row, status="disputed")
        loan_id = normalized["loanId"]
        if loan_id:
            active[loan_id] = normalized
    return active


def _journal_active_prime_loans(
    ledger_transactions: list[Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, int]]:
    ordered = sorted(
        enumerate(ledger_transactions),
        key=lambda item: (
            _int_like(item[1].get("ts_ms")),
            str(item[1].get("transaction_id") or ""),
            int(item[0]),
        ),
    )
    active: Dict[str, Dict[str, Any]] = {}
    counts = {
        "missing_loan_id": 0,
        "duplicate_open": 0,
        "unmatched_settlement": 0,
        "unmatched_dispute": 0,
    }
    for _, tx in ordered:
        tx_type = str(tx.get("tx_type") or "")
        if tx_type not in {
            "prime_loan_open",
            "prime_loan_disputed",
            "prime_loan_settlement",
            "prime_loan_settlement_rejected",
        }:
            continue
        md = dict(tx.get("metadata") or {})
        normalized = _normalized_prime_loan_metadata(md)
        loan_id = normalized["loanId"]
        if not loan_id:
            counts["missing_loan_id"] += 1
            continue
        if tx_type == "prime_loan_open":
            if loan_id in active:
                counts["duplicate_open"] += 1
                continue
            normalized["status"] = "open"
            active[loan_id] = normalized
            continue
        if tx_type == "prime_loan_disputed":
            if loan_id not in active:
                counts["unmatched_dispute"] += 1
                continue
            current = dict(active[loan_id])
            current.update({k: v for k, v in normalized.items() if k != "loanId"})
            current["status"] = "disputed"
            active[loan_id] = current
            continue
        if tx_type == "prime_loan_settlement":
            if loan_id not in active:
                counts["unmatched_settlement"] += 1
                continue
            active.pop(loan_id, None)
            continue
        if tx_type == "prime_loan_settlement_rejected" and loan_id in active:
            current = dict(active[loan_id])
            current.update({k: v for k, v in normalized.items() if k != "loanId"})
            active[loan_id] = current
    return active, counts


def _loan_float_mismatch(left: Dict[str, Any], right: Dict[str, Any], key: str) -> bool:
    return abs(_float_like(left.get(key)) - _float_like(right.get(key))) > 1e-6


def _loan_text_mismatch(left: Dict[str, Any], right: Dict[str, Any], key: str) -> bool:
    return str(left.get(key) or "") != str(right.get(key) or "")


def reconcile_internal_prime_journal(
    prime_state: Dict[str, Any] | None,
    ledger_transactions: list[Dict[str, Any]] | None,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    state = dict(prime_state or {})
    txs = [dict(row) for row in list(ledger_transactions or []) if isinstance(row, dict)]

    active_from_journal, journal_counts = _journal_active_prime_loans(txs)
    active_from_state = _state_active_prime_loans(state)

    derived_borrowed_usd = round(
        sum(_float_like(v.get("notionalUsd")) for v in active_from_journal.values()), 8
    )
    derived_family_exposure: Dict[str, float] = {}
    for row in active_from_journal.values():
        fam = str(row.get("family") or "")
        derived_family_exposure[fam] = round(
            derived_family_exposure.get(fam, 0.0) + _float_like(row.get("notionalUsd")),
            8,
        )
    derived_open_loan_count = len(active_from_journal)
    derived_disputed_loan_count = sum(
        1 for row in active_from_journal.values() if str(row.get("status") or "") == "disputed"
    )
    derived_reserved_collateral_usd = round(
        sum(_float_like(v.get("collateralReservedUsd")) for v in active_from_journal.values()), 8
    )

    state_open_loans = list(state.get("openLoans") or [])
    state_disputed_loans = list(state.get("disputedLoans") or [])
    has_state_active_details = bool(state_open_loans or state_disputed_loans)
    has_observed_disputed_count = "disputedLoanCount" in state or has_state_active_details
    has_observed_reserved_collateral = "reservedCollateralUsd" in state or has_state_active_details

    borrowed_usd = _float_like(state.get("borrowedUsd"))
    prime_family_exposure = {
        str(k): round(_float_like(v), 8)
        for k, v in dict(state.get("familyExposure") or {}).items()
        if abs(_float_like(v)) > 1e-6
    }
    observed_open_loan_count = _int_like(
        state.get("loanCount") or len(state_open_loans) + len(state_disputed_loans)
    )
    observed_disputed_loan_count = _int_like(
        state.get("disputedLoanCount") or len(state_disputed_loans)
    )
    observed_reserved_collateral_usd = round(_float_like(state.get("reservedCollateralUsd")), 8)

    reasons: list[str] = []
    if journal_counts["missing_loan_id"] > 0:
        reasons.append("internal_prime_journal_missing_loan_id")
    if journal_counts["duplicate_open"] > 0:
        reasons.append("internal_prime_journal_duplicate_open")
    if journal_counts["unmatched_settlement"] > 0:
        reasons.append("internal_prime_journal_unmatched_settlement")
    if journal_counts["unmatched_dispute"] > 0:
        reasons.append("internal_prime_journal_unmatched_dispute")
    if abs(derived_borrowed_usd - borrowed_usd) > 1e-6:
        reasons.append("internal_prime_journal_borrowed_mismatch")
    if derived_open_loan_count != observed_open_loan_count:
        reasons.append("internal_prime_journal_open_loan_count_mismatch")
    if has_observed_disputed_count and derived_disputed_loan_count != observed_disputed_loan_count:
        reasons.append("internal_prime_journal_disputed_loan_count_mismatch")
    if derived_family_exposure != prime_family_exposure:
        reasons.append("internal_prime_journal_family_exposure_mismatch")
    if (
        has_observed_reserved_collateral
        and abs(derived_reserved_collateral_usd - observed_reserved_collateral_usd) > 1e-6
    ):
        reasons.append("internal_prime_journal_reserved_collateral_mismatch")

    missing_active_loan_ids: list[str] = []
    unexpected_active_loan_ids: list[str] = []
    metadata_mismatch_ids: list[str] = []
    status_mismatch_ids: list[str] = []
    if has_state_active_details:
        missing_active_loan_ids = sorted(set(active_from_state) - set(active_from_journal))
        unexpected_active_loan_ids = sorted(set(active_from_journal) - set(active_from_state))
        if missing_active_loan_ids:
            reasons.append("internal_prime_journal_active_loan_missing")
        if unexpected_active_loan_ids:
            reasons.append("internal_prime_journal_active_loan_unexpected")

        for loan_id in sorted(set(active_from_state) & set(active_from_journal)):
            observed = active_from_state[loan_id]
            derived = active_from_journal[loan_id]
            if _loan_text_mismatch(observed, derived, "status"):
                status_mismatch_ids.append(loan_id)
            if (
                _loan_text_mismatch(observed, derived, "family")
                or _loan_text_mismatch(observed, derived, "asset")
                or _loan_float_mismatch(observed, derived, "notionalUsd")
                or _loan_float_mismatch(observed, derived, "collateralReservedUsd")
                or _loan_float_mismatch(observed, derived, "collateralRatio")
                or _loan_float_mismatch(observed, derived, "collateralHaircutPct")
                or _loan_float_mismatch(observed, derived, "collateralEfficiency")
            ):
                metadata_mismatch_ids.append(loan_id)
    if status_mismatch_ids:
        reasons.append("internal_prime_journal_active_loan_status_mismatch")
    if metadata_mismatch_ids:
        reasons.append("internal_prime_journal_active_loan_metadata_mismatch")

    payload = {
        "ok": len(reasons) == 0,
        "status": "ok" if len(reasons) == 0 else "degraded",
        "reasons": reasons,
        "derived": {
            "borrowed_usd": round(derived_borrowed_usd, 8),
            "open_loan_count": int(derived_open_loan_count),
            "disputed_loan_count": int(derived_disputed_loan_count),
            "reserved_collateral_usd": round(derived_reserved_collateral_usd, 8),
            "family_exposure": derived_family_exposure,
            "active_loans": active_from_journal,
        },
        "observed": {
            "borrowed_usd": round(borrowed_usd, 8),
            "open_loan_count": int(observed_open_loan_count),
            "disputed_loan_count": int(observed_disputed_loan_count),
            "reserved_collateral_usd": round(observed_reserved_collateral_usd, 8),
            "family_exposure": prime_family_exposure,
            "active_loans": active_from_state,
        },
        "journal_counts": {
            "missing_loan_id": int(journal_counts["missing_loan_id"]),
            "duplicate_open": int(journal_counts["duplicate_open"]),
            "unmatched_settlement": int(journal_counts["unmatched_settlement"]),
            "unmatched_dispute": int(journal_counts["unmatched_dispute"]),
        },
        "loan_deltas": {
            "missing_active_loan_ids": missing_active_loan_ids,
            "unexpected_active_loan_ids": unexpected_active_loan_ids,
            "status_mismatch_ids": status_mismatch_ids,
            "metadata_mismatch_ids": metadata_mismatch_ids,
        },
    }
    if strict and not payload["ok"]:
        raise ReconciliationError(
            "internal_prime_journal_reconciliation_failed",
            reason_code=(reasons[0] if reasons else "internal_prime_journal_reconciliation_failed"),
        )
    return payload
