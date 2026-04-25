from __future__ import annotations

from typing import Any, Dict

from ..degraded_state_contract import decision_contract
from .capital_truth_health_contract import build_capital_truth_health_view


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _unique_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def build_withdraw_control_view(
    runtime: Any | None,
    *,
    capital_truth: Dict[str, Any] | None = None,
    fund_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    truth = _safe_dict(capital_truth)
    if not truth and runtime is not None:
        getter = getattr(runtime, "capital_truth_state", None)
        if callable(getter):
            try:
                raw = getter()
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                raw = {}
            truth = _safe_dict(raw)

    health = build_capital_truth_health_view(
        _safe_dict(_safe_dict(fund_summary).get("health") or fund_summary),
        capital_truth=truth,
    )
    truth_freshness = _safe_dict(truth.get("freshness"))
    truth_freshness_class = str(truth_freshness.get("class") or "").strip()
    truth_freshness_reason_codes = _unique_strings(list(truth_freshness.get("reason_codes") or []))
    if truth_freshness_class:
        health["freshnessClass"] = truth_freshness_class
    if truth_freshness_reason_codes:
        health["freshnessReasonCodes"] = truth_freshness_reason_codes
        health["freshnessReasonCode"] = str(
            health.get("freshnessReasonCode") or truth_freshness_reason_codes[0]
        )
        if truth_freshness_class in {"aging", "stale", "unknown", "unavailable"}:
            health["nextAction"] = "refresh_capital_truth_snapshot"
            if str(health.get("recoveryNextAction") or "") in {"", "restore_capital_truth"}:
                health["recoveryNextAction"] = "refresh_capital_truth_snapshot"

    withdrawal = _safe_dict(truth.get("withdrawal"))
    capital_truth_status = str(truth.get("status") or "").strip().lower()
    withdrawal_present = bool(withdrawal)
    enforced = bool(
        withdrawal_present
        or (capital_truth_status and capital_truth_status != "ok")
        or list(truth.get("reason_codes") or [])
        or list(truth.get("status_reasons") or [])
    )
    preview_available = bool(withdrawal.get("previewable")) if enforced else False
    if enforced:
        execute_available = bool(withdrawal.get("available")) and not bool(health.get("blocked"))
    else:
        execute_available = True

    reason_codes = _unique_strings(
        list(withdrawal.get("reason_codes") or [])
        + list(health.get("reasonCodes") or [])
        + list(health.get("freshnessReasonCodes") or [])
    )
    reason_code = str(withdrawal.get("reason_code") or "").strip()
    if not reason_code and enforced:
        reason_code = str(health.get("reasonCode") or "").strip()
    if not reason_code:
        reason_code = "ok" if execute_available else "no_withdrawable_balance"
    if reason_code != "ok" and reason_code not in reason_codes:
        reason_codes = [reason_code, *reason_codes]

    if execute_available:
        status = "ready"
        action_reason_code = "ok"
        action_reason_codes = ["ok"]
    elif preview_available:
        status = "preview_only"
        action_reason_code = "capital_truth_degraded"
        action_reason_codes = _unique_strings([action_reason_code, *reason_codes])
    else:
        status = "blocked" if enforced else "ready"
        action_reason_code = reason_code if enforced else "ok"
        action_reason_codes = (reason_codes or [reason_code]) if enforced else ["ok"]

    next_action = ""
    if action_reason_code != "ok":
        next_action = str(health.get("nextAction") or "").strip()
        if not next_action and action_reason_code == "capital_truth_degraded":
            next_action = "refresh_capital_truth_snapshot"

    state_contract_reason = action_reason_code if action_reason_code != "ok" else reason_code
    return {
        "status": status,
        "reasonCode": reason_code,
        "reasonCodes": reason_codes if reason_code != "ok" else [],
        "actionReasonCode": action_reason_code,
        "actionReasonCodes": action_reason_codes,
        "previewAvailable": preview_available,
        "executeAvailable": execute_available,
        "nextAction": next_action,
        "capitalTruthHealth": health,
        "stateContract": decision_contract(
            phase="withdraw_control",
            reason_code=state_contract_reason,
            blocked=not execute_available,
            degraded=bool(action_reason_code == "capital_truth_degraded"),
            denied=False,
            sticky_cycle=True,
            details={
                "status": status,
                "previewAvailable": preview_available,
                "executeAvailable": execute_available,
                "capitalTruthStatus": str(health.get("status") or "unknown"),
                "capitalTruthFreshnessClass": str(health.get("freshnessClass") or "unknown"),
                "enforced": enforced,
            },
        ),
    }
