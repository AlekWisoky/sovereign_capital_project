from __future__ import annotations

from typing import Any, Dict

from ..jsonsafe import to_json_safe
from .summary_read_contract import build_summary_read_contract


CAPITAL_TRUTH_READ_MODEL = "ledgered_capital_truth_v3_converged"
CAPITAL_TRUTH_SUMMARY_PHASE = "capital_truth_summary"
CAPITAL_TRUTH_SUMMARY_READ_MODEL = "capital_truth_projection_v1"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def build_capital_truth_projection(
    *,
    now_ms: int,
    status: str,
    status_reason_code: str,
    reasons: list[str],
    chain: str,
    categories: Dict[str, Any],
    family_allocations: Dict[str, Any],
    family_capital_plan_version: str,
    family_capital_plan: list[Dict[str, Any]],
    freshness: Dict[str, Any],
    ledger: Dict[str, Any],
    reconciliation: Dict[str, Any],
    withdrawal: Dict[str, Any],
) -> Dict[str, Any]:
    reason_codes = (
        [
            status_reason_code,
            *[reason for reason in reasons if reason != status_reason_code],
        ]
        if status_reason_code != "ok"
        else []
    )
    truth = {
        "ok": True,
        "canonical": True,
        "service": "capital_truth_service",
        "status": str(status or "ok"),
        "reason_code": str(status_reason_code or "ok"),
        "reason": str(status_reason_code or "ok"),
        "reason_codes": list(reason_codes),
        "status_reasons": list(reasons or []),
        "ts_ms": int(now_ms),
        "observed_ts_ms": int(now_ms),
        "chain": str(chain or ""),
        "ledgered": True,
        "auditable": True,
        "read_model": CAPITAL_TRUTH_READ_MODEL,
        "categories": dict(categories or {}),
        "accounts": {
            "capital": {
                "total_wei": str(dict(categories or {}).get("total_capital_wei") or "0"),
                "deployable_wei": str(dict(categories or {}).get("deployable_capital_wei") or "0"),
                "reserved_wei": str(dict(categories or {}).get("reserved_capital_wei") or "0"),
                "locked_wei": str(dict(categories or {}).get("capital_locked_wei") or "0"),
                "treasury_balance_wei": str(
                    dict(categories or {}).get("treasury_balance_wei") or "0"
                ),
            },
            "profit": {
                "realized_wei": str(dict(categories or {}).get("realized_profit_wei") or "0"),
                "retained_wei": str(dict(categories or {}).get("retained_profit_wei") or "0"),
                "withdrawable_wei": str(
                    dict(categories or {}).get("withdrawable_balance_wei") or "0"
                ),
            },
            "family_allocations": dict(family_allocations or {}),
            "family_capital_plan": list(family_capital_plan or []),
        },
        "family_allocations": dict(family_allocations or {}),
        "familyCapitalPlanVersion": str(family_capital_plan_version or ""),
        "familyCapitalPlan": list(family_capital_plan or []),
        "freshness": dict(freshness or {}),
        "ledger": dict(ledger or {}),
        "reconciliation": dict(reconciliation or {}),
        "withdrawal": dict(withdrawal or {}),
    }
    reconciliation_payload = _safe_dict(truth.get("reconciliation"))
    truth["summaryContract"] = build_summary_read_contract(
        family="capital_truth",
        payload=truth,
        source_contracts={
            "receiptSettlement": _safe_dict(reconciliation_payload.get("receipt_settlement")),
            "internalPrimeJournal": _safe_dict(
                reconciliation_payload.get("internal_prime_journal")
            ),
            "internalPrimeLedger": _safe_dict(reconciliation_payload.get("internal_prime_ledger")),
            "capitalConvergence": _safe_dict(reconciliation_payload.get("capital_convergence")),
        },
        phase=CAPITAL_TRUTH_SUMMARY_PHASE,
        read_model=CAPITAL_TRUTH_SUMMARY_READ_MODEL,
    )
    return to_json_safe(truth)


def build_compact_capital_truth_projection(capital_truth: Dict[str, Any] | None) -> Dict[str, Any]:
    truth = _safe_dict(capital_truth)
    ledger = _safe_dict(truth.get("ledger"))
    balances = _safe_dict(ledger.get("balances"))
    accounting = _safe_dict(ledger.get("accounting"))
    transactions = list(ledger.get("transactions") or [])
    tail = list(ledger.get("tail") or [])
    reconciliation = _safe_dict(truth.get("reconciliation"))
    receipt_settlement = _safe_dict(reconciliation.get("receipt_settlement"))
    withdrawal = _safe_dict(truth.get("withdrawal"))
    return to_json_safe(
        {
            "status": str(truth.get("status") or ("ok" if truth.get("ok") else "unavailable")),
            "reasonCode": str(truth.get("reason_code") or "capital_truth_unavailable"),
            "reasonCodes": list(truth.get("reason_codes") or []),
            "readModel": str(truth.get("read_model") or ""),
            "familyCapitalPlanVersion": str(truth.get("familyCapitalPlanVersion") or ""),
            "familyCapitalPlan": list(truth.get("familyCapitalPlan") or []),
            "ledgerUsdBalance": _safe_float(balances.get("USD")),
            "ledgerAvailable": bool(balances or accounting or transactions or tail),
            "ledgerTransactionCount": len(transactions),
            "ledgerTailCount": len(tail),
            "lastLedgerTsMs": _safe_int(ledger.get("last_ts_ms")),
            "settlementRecorded": bool(
                receipt_settlement.get("last_receipt_id")
                or receipt_settlement.get("last_transaction_id")
                or transactions
                or tail
            ),
            "lastSettlement": {
                "receiptId": str(receipt_settlement.get("last_receipt_id") or ""),
                "transactionId": str(receipt_settlement.get("last_transaction_id") or ""),
                "status": str(receipt_settlement.get("status") or ""),
            },
            "terminalProfitabilityAuthority": {
                "stage": (
                    "realized_settlement"
                    if bool(receipt_settlement.get("ok", False))
                    else "unverified"
                ),
                "authoritative": bool(receipt_settlement.get("ok", False)),
                "reasonCodes": list(receipt_settlement.get("reason_codes") or []),
            },
            "capitalAdmission": {
                "ok": str(truth.get("status") or "") == "ok",
                "reasonCode": str(truth.get("reason_code") or "capital_truth_unavailable"),
            },
            "withdrawal": {
                "available": bool(withdrawal.get("available", False)),
                "previewable": bool(withdrawal.get("previewable", False)),
                "reasonCodes": list(withdrawal.get("reason_codes") or []),
            },
            "summaryContract": _safe_dict(truth.get("summaryContract")),
        }
    )
