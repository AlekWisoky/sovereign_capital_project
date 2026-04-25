from __future__ import annotations

from typing import Any, Dict

from ..jsonsafe import to_json_safe
from .capital_truth_projection import build_compact_capital_truth_projection


CAPITAL_LEDGER_TRUTH_PHASE = "capital_ledger_truth"
CAPITAL_OPERATOR_READ_PHASE = "capital_operator_projection"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return int(default)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def build_capital_ledger_truth_projection(
    capital_summary: Dict[str, Any] | None,
    *,
    capital_truth_health: Dict[str, Any] | None = None,
    capital_truth_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = _safe_dict(capital_summary)
    health = _safe_dict(capital_truth_health)
    truth_projection = build_compact_capital_truth_projection(capital_truth_state)
    ledger = _safe_dict(summary.get("ledger"))
    balances = _safe_dict(ledger.get("balances"))
    accounting = _safe_dict(ledger.get("accounting"))
    tail = list(ledger.get("tail") or [])
    transactions = list(ledger.get("transactions") or [])
    internal_prime = _safe_dict(summary.get("internalPrime"))
    last_settlement = _safe_dict(summary.get("lastSettlement"))
    if not last_settlement:
        last_settlement = _safe_dict(truth_projection.get("lastSettlement"))
    terminal_authority = _safe_dict(summary.get("terminalProfitabilityAuthority"))
    if not terminal_authority:
        terminal_authority = _safe_dict(truth_projection.get("terminalProfitabilityAuthority"))
    capital_admission = _safe_dict(summary.get("capitalAdmission"))
    if not capital_admission:
        capital_admission = _safe_dict(truth_projection.get("capitalAdmission"))
    nav_usd = _safe_float(summary.get("navUsd"))
    nav_source = str(summary.get("navSource") or "unavailable")
    ledger_usd_balance = _safe_float(
        balances.get("USD")
        if balances.get("USD") is not None
        else truth_projection.get("ledgerUsdBalance")
    )
    ledger_available = bool(
        balances or accounting or tail or transactions or truth_projection.get("ledgerAvailable")
    )
    settlement_recorded = bool(
        last_settlement.get("receiptId")
        or last_settlement.get("transactionId")
        or transactions
        or tail
        or truth_projection.get("settlementRecorded")
    )
    capital_truth_ok = bool(health.get("ok", True))
    freshness_class = str(health.get("freshnessClass") or "")
    reliability_class = str(health.get("reliabilityClass") or "")
    degraded = bool(
        (not capital_truth_ok)
        or freshness_class in {"stale", "degraded", "unknown", "unavailable"}
        or reliability_class in {"degraded", "fragile", "unknown", "unavailable"}
    )
    status = (
        "unavailable"
        if not ledger_available and nav_source == "unavailable"
        else ("degraded" if degraded else "ok")
    )
    reason_code = (
        "capital_ledger_unavailable"
        if status == "unavailable"
        else (
            str(health.get("reasonCode") or "capital_truth_degraded") if status == "degraded" else "ok"
        )
    )
    state_contract = {
        "phase": CAPITAL_LEDGER_TRUTH_PHASE,
        "status": status,
        "reason_code": reason_code,
        "degraded": status == "degraded",
        "blocked": False,
        "sticky_cycle": True,
        "details": {
            "navSource": nav_source,
            "ledgerAvailable": ledger_available,
            "settlementRecorded": settlement_recorded,
            "transactionCount": len(transactions),
            "tailCount": len(tail),
        },
    }
    return to_json_safe(
        {
            "ok": status == "ok",
            "navUsd": nav_usd,
            "navSource": nav_source,
            "ledgerUsdBalance": ledger_usd_balance,
            "ledgerAvailable": ledger_available,
            "ledgerTransactionCount": max(len(transactions), _safe_int(truth_projection.get("ledgerTransactionCount"))),
            "ledgerTailCount": max(len(tail), _safe_int(truth_projection.get("ledgerTailCount"))),
            "settlementRecorded": settlement_recorded,
            "lastSettlement": last_settlement,
            "terminalProfitabilityAuthority": terminal_authority,
            "capitalAdmission": capital_admission,
            "internalPrime": internal_prime,
            "familyCapitalPlanVersion": str(summary.get("familyCapitalPlanVersion") or ""),
            "familyCapitalPlan": list(summary.get("familyCapitalPlan") or []),
            "stateContract": state_contract,
        }
    )



def build_capital_operator_projection(
    *,
    capital_summary: Dict[str, Any] | None,
    capital_contract: Dict[str, Any] | None,
    capital_policy: Dict[str, Any] | None,
    capital_truth_health: Dict[str, Any] | None,
    capital_truth_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = _safe_dict(capital_summary)
    contract = _safe_dict(capital_contract)
    policy = _safe_dict(capital_policy)
    health = _safe_dict(capital_truth_health)
    ledger_truth = build_capital_ledger_truth_projection(
        summary, capital_truth_health=health, capital_truth_state=capital_truth_state
    )
    exposure = _safe_dict(summary.get("exposure"))
    state_contract = {
        "phase": CAPITAL_OPERATOR_READ_PHASE,
        "status": str(ledger_truth.get("stateContract", {}).get("status") or "unavailable"),
        "reason_code": str(ledger_truth.get("stateContract", {}).get("reason_code") or "capital_truth_unavailable"),
        "degraded": bool(ledger_truth.get("stateContract", {}).get("degraded", False)),
        "blocked": False,
        "sticky_cycle": True,
        "details": {
            "navSource": str(summary.get("navSource") or "unavailable"),
            "deployableUsd": _safe_float(summary.get("deployableUsd")),
            "estimatedCapitalUsd": _safe_float(summary.get("estimatedCapitalUsd")),
            "ledgerState": str(ledger_truth.get("stateContract", {}).get("status") or "unavailable"),
        },
    }
    capital = {
        "navUsd": _safe_float(summary.get("navUsd")),
        "navSource": str(summary.get("navSource") or "unknown"),
        "deployableUsd": _safe_float(summary.get("deployableUsd")),
        "estimatedCapitalUsd": _safe_float(summary.get("estimatedCapitalUsd")),
        "deployedCapitalUsd": _safe_float(summary.get("deployedCapitalUsd")),
        "utilizationPct": _safe_float(summary.get("utilizationPct")),
        "exposure": exposure,
        "internalPrime": _safe_dict(summary.get("internalPrime")),
        "capitalContract": contract,
        "capitalPolicy": policy,
        "capitalTruthHealth": health,
        "ledgerTruth": ledger_truth,
        "familyCapitalPlanVersion": str(summary.get("familyCapitalPlanVersion") or ""),
        "familyCapitalPlan": list(summary.get("familyCapitalPlan") or []),
        "stateContract": state_contract,
    }
    return to_json_safe(
        {
            "capitalSummary": summary,
            "capitalLedgerTruth": ledger_truth,
            "capital": capital,
        }
    )


def build_capital_read_surface_payload(
    *,
    capital_summary: Dict[str, Any] | None,
    capital_contract: Dict[str, Any] | None,
    capital_policy: Dict[str, Any] | None,
    capital_truth_health: Dict[str, Any] | None,
    capital_truth_state: Dict[str, Any] | None = None,
    include_operator_projection: bool = True,
) -> Dict[str, Any]:
    contract = _safe_dict(capital_contract)
    policy = _safe_dict(capital_policy)
    health = _safe_dict(capital_truth_health)
    projection = build_capital_operator_projection(
        capital_summary=capital_summary,
        capital_contract=contract,
        capital_policy=policy,
        capital_truth_health=health,
        capital_truth_state=capital_truth_state,
    )
    payload = {
        "capitalSummary": dict(projection.get("capitalSummary") or {}),
        "capitalContract": contract,
        "capitalPolicy": policy,
        "capitalTruthHealth": health,
        "capitalLedgerTruth": dict(projection.get("capitalLedgerTruth") or {}),
    }
    if include_operator_projection:
        payload["capital"] = dict(projection.get("capital") or {})
    return to_json_safe(payload)
