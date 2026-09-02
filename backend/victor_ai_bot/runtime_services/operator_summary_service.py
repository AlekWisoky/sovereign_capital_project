from __future__ import annotations

import time
from collections.abc import Mapping as ABCMapping
from typing import Any, Dict, List

from ..jsonsafe import json_safe
from .control_state import unavailable_state
from .state_summary_service import StateSummaryService
from .family_hardening_service import family_hardening_unavailable_summary
from .auxiliary_state_service import AuxiliaryStateService
from .profitability_truth import inspect_profit_after_costs_truth
from .summary_read_contract import build_summary_read_contract
from .state_service import (
    execution_gate_info,
    resolve_auto_trade_gate_and_recovery,
    select_top_opportunity,
)
from .route_runtime_truth import execution_route_truth
from .execution_lifecycle_projection import (
    build_execution_lifecycle_projections,
    build_receipt_summary_projection,
    select_focus_execution_lifecycle,
)
from .capital_truth_read_context import build_capital_truth_read_context
from ..fund_os.family_identity import family_identity


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _unique_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        sval = str(value or "").strip()
        if sval and sval not in out:
            out.append(sval)
    return out


def _humanize_code(value: str) -> str:
    return str(value or "").replace("_", " ")


def _family_identity_payload(value: Any) -> Dict[str, Any]:
    return family_identity(str(value or "flashloan_atomic") or "flashloan_atomic")


def _canonical_strategy_projection(value: Any) -> Dict[str, Any]:
    info = _family_identity_payload(value)
    return {
        "strategies": [str(info.get("launchFamily") or "")],
        "strategyRuntimeFamilies": [str(info.get("runtimeFamily") or "")],
        "strategyCapitalFamilies": [str(info.get("capitalFamily") or "")],
        "strategyDisplayNames": [str(info.get("displayName") or "")],
        "strategyAliases": list(info.get("aliases") or []),
        "strategyIdentities": [info],
    }


def _family_hardening_service_state(family_hardening: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = _safe_dict(family_hardening)
    status = (
        str(payload.get("status") or ("ok" if bool(payload.get("ok", True)) else "unavailable"))
        .strip()
        .lower()
    )
    ok = bool(payload.get("ok", status == "ok")) and status == "ok"
    reason_codes = _unique_strings(list(payload.get("reason_codes") or []))
    reason_code = str(
        payload.get("reason_code")
        or payload.get("reason")
        or (
            "family_hardening_service_unavailable"
            if status == "unavailable"
            else (status if status and status != "ok" else "")
        )
    )
    if not ok and reason_code and reason_code not in reason_codes:
        reason_codes = [reason_code, *reason_codes]
    return {
        "ok": ok,
        "status": status,
        "reason_code": reason_code,
        "reason_codes": reason_codes,
    }


def _fund_health_hold_state(
    fund_summary: Dict[str, Any], family_hardening: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    health = _safe_dict(fund_summary.get("health")) if isinstance(fund_summary, dict) else {}
    if (
        not health
        and isinstance(fund_summary, dict)
        and any(
            key in fund_summary
            for key in (
                "holdReasonCode",
                "holdReasonCodes",
                "suggestedNextAction",
                "capitalTruthReasonCodes",
                "recoveryStatus",
                "recoveryReasonCode",
                "recoveryReasonCodes",
                "recoveryNextAction",
            )
        )
    ):
        health = dict(fund_summary)
    hold_reason_codes = _unique_strings(list(health.get("holdReasonCodes") or []))
    hold_reason_code = str(
        health.get("holdReasonCode") or (hold_reason_codes[0] if hold_reason_codes else "")
    )
    if hold_reason_code and hold_reason_code not in hold_reason_codes:
        hold_reason_codes = [hold_reason_code, *hold_reason_codes]
    global_execution_reason_codes = _unique_strings(
        list(health.get("globalExecutionReasonCodes") or [])
    )
    capital_truth_reason_codes = _unique_strings(list(health.get("capitalTruthReasonCodes") or []))
    receipt_outcome_truth_reason_codes = _unique_strings(
        list(health.get("receiptOutcomeTruthReasonCodes") or [])
    )
    internal_prime_reason_codes = _unique_strings(
        list(health.get("internalPrimeReasonCodes") or [])
    )
    family_hardening_reason_codes = _unique_strings(
        list(health.get("familyHardeningReasonCodes") or [])
    )
    family_hardening_service = _family_hardening_service_state(family_hardening)
    if not family_hardening_service["ok"]:
        family_hardening_reason_codes = _unique_strings(
            [
                *[str(x) for x in family_hardening_reason_codes if str(x)],
                *[
                    str(x)
                    for x in list(family_hardening_service.get("reason_codes") or [])
                    if str(x)
                ],
            ]
        )
    if not hold_reason_codes and family_hardening_reason_codes:
        hold_reason_codes = list(family_hardening_reason_codes)
        hold_reason_code = hold_reason_codes[0]
    suggested_next_action = str(health.get("suggestedNextAction") or "")
    if not suggested_next_action and family_hardening_reason_codes:
        suggested_next_action = "restore_family_hardening"
    elif not suggested_next_action and receipt_outcome_truth_reason_codes:
        suggested_next_action = "restore_receipt_outcome_truth"
    recovery_reason_codes = _unique_strings(list(health.get("recoveryReasonCodes") or []))
    inferred_recovery_status = (
        "global_execution_blocked"
        if global_execution_reason_codes
        else (
            "family_hardening_restore_required"
            if family_hardening_reason_codes
            else (
                "internal_prime_reconciliation_required"
                if internal_prime_reason_codes
                else (
                    "capital_truth_restore_required"
                    if (receipt_outcome_truth_reason_codes or capital_truth_reason_codes)
                    else "ready"
                )
            )
        )
    )
    if not recovery_reason_codes:
        if global_execution_reason_codes:
            recovery_reason_codes = list(global_execution_reason_codes)
        elif family_hardening_reason_codes:
            recovery_reason_codes = list(family_hardening_reason_codes)
        elif internal_prime_reason_codes:
            recovery_reason_codes = list(internal_prime_reason_codes)
        elif receipt_outcome_truth_reason_codes:
            recovery_reason_codes = list(receipt_outcome_truth_reason_codes)
        elif capital_truth_reason_codes:
            recovery_reason_codes = list(capital_truth_reason_codes)
    recovery_reason_code = str(
        health.get("recoveryReasonCode")
        or (recovery_reason_codes[0] if recovery_reason_codes else "ok")
    )
    if recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    recovery_status = str(health.get("recoveryStatus") or inferred_recovery_status)
    if recovery_status == "ready" and family_hardening_reason_codes:
        recovery_status = "family_hardening_restore_required"
    recovery_next_action = str(health.get("recoveryNextAction") or suggested_next_action)
    recovery_ready = bool(
        health.get("recoveryReady", recovery_status == "ready" and not recovery_reason_codes)
    )
    capital_truth_freshness_class = str(health.get("capitalTruthFreshnessClass") or "")
    capital_truth_freshness_reason_codes = _unique_strings(
        list(health.get("capitalTruthFreshnessReasonCodes") or [])
    )
    receipt_outcome_truth_freshness_class = str(
        health.get("receiptOutcomeTruthFreshnessClass") or ""
    )
    receipt_outcome_truth_freshness_reason_codes = _unique_strings(
        list(health.get("receiptOutcomeTruthFreshnessReasonCodes") or [])
    )
    internal_prime_freshness_class = str(health.get("internalPrimeFreshnessClass") or "")
    internal_prime_freshness_reason_codes = _unique_strings(
        list(health.get("internalPrimeFreshnessReasonCodes") or [])
    )
    recovery_freshness_reason_codes = _unique_strings(
        list(health.get("recoveryFreshnessReasonCodes") or [])
    )
    recovery_freshness_reason_code = str(
        health.get("recoveryFreshnessReasonCode")
        or (recovery_freshness_reason_codes[0] if recovery_freshness_reason_codes else "ok")
    )
    if (
        recovery_freshness_reason_code != "ok"
        and recovery_freshness_reason_code not in recovery_freshness_reason_codes
    ):
        recovery_freshness_reason_codes = [
            recovery_freshness_reason_code,
            *recovery_freshness_reason_codes,
        ]
    recovery_freshness_class = str(
        health.get("recoveryFreshnessClass")
        or ("current" if recovery_status in {"ready", "global_execution_blocked"} else "unknown")
    )
    recovery_freshness_next_action = str(health.get("recoveryFreshnessNextAction") or "")
    recovery_history_component = str(health.get("recoveryHistoryComponent") or "")
    if not recovery_history_component and family_hardening_reason_codes:
        recovery_history_component = "family_hardening"
    elif not recovery_history_component and receipt_outcome_truth_reason_codes:
        recovery_history_component = "receipt_outcome_truth"
    recovery_history_status = str(
        health.get("recoveryHistoryStatus")
        or (
            "blocked"
            if recovery_status == "global_execution_blocked"
            else (
                "degraded"
                if family_hardening_reason_codes
                else ("recovered" if recovery_ready else "steady")
            )
        )
    )
    recovery_degraded_since_ts_ms = int(health.get("recoveryDegradedSinceTsMs") or 0)
    recovery_recovered_at_ts_ms = int(health.get("recoveryRecoveredAtTsMs") or 0)
    recovery_degraded_duration_ms = int(health.get("recoveryDegradedDurationMs") or 0)
    capital_truth_recovery_history_status = str(
        health.get("capitalTruthRecoveryHistoryStatus")
        or ("degraded" if capital_truth_reason_codes else "steady")
    )
    receipt_outcome_truth_recovery_history_status = str(
        health.get("receiptOutcomeTruthRecoveryHistoryStatus")
        or ("degraded" if receipt_outcome_truth_reason_codes else "steady")
    )
    capital_truth_degraded_since_ts_ms = int(health.get("capitalTruthDegradedSinceTsMs") or 0)
    capital_truth_recovered_at_ts_ms = int(health.get("capitalTruthRecoveredAtTsMs") or 0)
    capital_truth_degraded_duration_ms = int(health.get("capitalTruthDegradedDurationMs") or 0)
    receipt_outcome_truth_degraded_since_ts_ms = int(
        health.get("receiptOutcomeTruthDegradedSinceTsMs") or 0
    )
    receipt_outcome_truth_recovered_at_ts_ms = int(
        health.get("receiptOutcomeTruthRecoveredAtTsMs") or 0
    )
    receipt_outcome_truth_degraded_duration_ms = int(
        health.get("receiptOutcomeTruthDegradedDurationMs") or 0
    )
    internal_prime_recovery_history_status = str(
        health.get("internalPrimeRecoveryHistoryStatus")
        or ("degraded" if internal_prime_reason_codes else "steady")
    )
    internal_prime_degraded_since_ts_ms = int(health.get("internalPrimeDegradedSinceTsMs") or 0)
    internal_prime_recovered_at_ts_ms = int(health.get("internalPrimeRecoveredAtTsMs") or 0)
    internal_prime_degraded_duration_ms = int(health.get("internalPrimeDegradedDurationMs") or 0)
    recovery_degraded_count = int(health.get("recoveryDegradedCount") or 0)
    recovery_last_healthy_ts_ms = int(health.get("recoveryLastHealthyTsMs") or 0)
    recovery_recovered_recently = bool(health.get("recoveryRecoveredRecently", False))
    recovery_degradation_severity_class = str(
        health.get("recoveryDegradationSeverityClass")
        or (
            "blocked"
            if recovery_history_status == "blocked"
            else (
                "recovering"
                if recovery_history_status == "recovered" and recovery_recovered_recently
                else ("stable" if recovery_history_status == "steady" else "acute")
            )
        )
    )
    capital_truth_degraded_count = int(health.get("capitalTruthDegradedCount") or 0)
    capital_truth_last_healthy_ts_ms = int(health.get("capitalTruthLastHealthyTsMs") or 0)
    capital_truth_recovered_recently = bool(health.get("capitalTruthRecoveredRecently", False))
    receipt_outcome_truth_degraded_count = int(health.get("receiptOutcomeTruthDegradedCount") or 0)
    receipt_outcome_truth_last_healthy_ts_ms = int(
        health.get("receiptOutcomeTruthLastHealthyTsMs") or 0
    )
    receipt_outcome_truth_recovered_recently = bool(
        health.get("receiptOutcomeTruthRecoveredRecently", False)
    )
    capital_truth_degradation_severity_class = str(
        health.get("capitalTruthDegradationSeverityClass")
        or (
            "recovering"
            if capital_truth_recovery_history_status == "recovered"
            and capital_truth_recovered_recently
            else ("stable" if capital_truth_recovery_history_status == "steady" else "acute")
        )
    )
    receipt_outcome_truth_degradation_severity_class = str(
        health.get("receiptOutcomeTruthDegradationSeverityClass")
        or (
            "recovering"
            if receipt_outcome_truth_recovery_history_status == "recovered"
            and receipt_outcome_truth_recovered_recently
            else (
                "stable" if receipt_outcome_truth_recovery_history_status == "steady" else "acute"
            )
        )
    )
    internal_prime_degraded_count = int(health.get("internalPrimeDegradedCount") or 0)
    internal_prime_last_healthy_ts_ms = int(health.get("internalPrimeLastHealthyTsMs") or 0)
    internal_prime_recovered_recently = bool(health.get("internalPrimeRecoveredRecently", False))
    internal_prime_degradation_severity_class = str(
        health.get("internalPrimeDegradationSeverityClass")
        or (
            "recovering"
            if internal_prime_recovery_history_status == "recovered"
            and internal_prime_recovered_recently
            else ("stable" if internal_prime_recovery_history_status == "steady" else "acute")
        )
    )
    capital_truth_reliability_reason_codes = _unique_strings(
        list(health.get("capitalTruthReliabilityReasonCodes") or [])
    )
    receipt_outcome_truth_reliability_reason_codes = _unique_strings(
        list(health.get("receiptOutcomeTruthReliabilityReasonCodes") or [])
    )
    capital_truth_reliability_class = str(
        health.get("capitalTruthReliabilityClass")
        or (
            "degraded"
            if capital_truth_reason_codes
            else (
                "unavailable"
                if capital_truth_freshness_class == "unavailable"
                else ("unknown" if capital_truth_freshness_class == "unknown" else "stable")
            )
        )
    )
    capital_truth_reliability_reason_code = str(
        health.get("capitalTruthReliabilityReasonCode")
        or (
            capital_truth_reliability_reason_codes[0]
            if capital_truth_reliability_reason_codes
            else (
                f"capital_truth_reliability_{capital_truth_reliability_class}"
                if capital_truth_reliability_class != "stable"
                else "ok"
            )
        )
    )
    if (
        capital_truth_reliability_reason_code != "ok"
        and capital_truth_reliability_reason_code not in capital_truth_reliability_reason_codes
    ):
        capital_truth_reliability_reason_codes = [
            capital_truth_reliability_reason_code,
            *capital_truth_reliability_reason_codes,
        ]
    capital_truth_recovered_fragile = bool(
        health.get(
            "capitalTruthRecoveredFragile",
            capital_truth_recovery_history_status == "recovered"
            and capital_truth_reliability_class == "fragile",
        )
    )
    receipt_outcome_truth_reliability_class = str(
        health.get("receiptOutcomeTruthReliabilityClass")
        or (
            "degraded"
            if receipt_outcome_truth_reason_codes
            else (
                "unavailable"
                if receipt_outcome_truth_freshness_class == "unavailable"
                else ("unknown" if receipt_outcome_truth_freshness_class == "unknown" else "stable")
            )
        )
    )
    receipt_outcome_truth_reliability_reason_code = str(
        health.get("receiptOutcomeTruthReliabilityReasonCode")
        or (
            receipt_outcome_truth_reliability_reason_codes[0]
            if receipt_outcome_truth_reliability_reason_codes
            else (
                f"receipt_outcome_truth_reliability_{receipt_outcome_truth_reliability_class}"
                if receipt_outcome_truth_reliability_class != "stable"
                else "ok"
            )
        )
    )
    if (
        receipt_outcome_truth_reliability_reason_code != "ok"
        and receipt_outcome_truth_reliability_reason_code
        not in receipt_outcome_truth_reliability_reason_codes
    ):
        receipt_outcome_truth_reliability_reason_codes = [
            receipt_outcome_truth_reliability_reason_code,
            *receipt_outcome_truth_reliability_reason_codes,
        ]
    receipt_outcome_truth_recovered_fragile = bool(
        health.get(
            "receiptOutcomeTruthRecoveredFragile",
            receipt_outcome_truth_recovery_history_status == "recovered"
            and receipt_outcome_truth_reliability_class == "fragile",
        )
    )
    internal_prime_reliability_reason_codes = _unique_strings(
        list(health.get("internalPrimeReliabilityReasonCodes") or [])
    )
    internal_prime_reliability_class = str(
        health.get("internalPrimeReliabilityClass")
        or (
            "degraded"
            if internal_prime_reason_codes
            else (
                "unavailable"
                if internal_prime_freshness_class == "unavailable"
                else ("unknown" if internal_prime_freshness_class == "unknown" else "stable")
            )
        )
    )
    internal_prime_reliability_reason_code = str(
        health.get("internalPrimeReliabilityReasonCode")
        or (
            internal_prime_reliability_reason_codes[0]
            if internal_prime_reliability_reason_codes
            else (
                f"internal_prime_reliability_{internal_prime_reliability_class}"
                if internal_prime_reliability_class != "stable"
                else "ok"
            )
        )
    )
    if (
        internal_prime_reliability_reason_code != "ok"
        and internal_prime_reliability_reason_code not in internal_prime_reliability_reason_codes
    ):
        internal_prime_reliability_reason_codes = [
            internal_prime_reliability_reason_code,
            *internal_prime_reliability_reason_codes,
        ]
    internal_prime_recovered_fragile = bool(
        health.get(
            "internalPrimeRecoveredFragile",
            internal_prime_recovery_history_status == "recovered"
            and internal_prime_reliability_class == "fragile",
        )
    )
    family_hardening_reliability_reason_codes = _unique_strings(
        list(health.get("familyHardeningReliabilityReasonCodes") or [])
    )
    family_hardening_reliability_class = str(
        health.get("familyHardeningReliabilityClass")
        or (
            "unavailable"
            if recovery_history_component == "family_hardening"
            and any(str(x).endswith("_unavailable") for x in family_hardening_reason_codes)
            else ("degraded" if family_hardening_reason_codes else "stable")
        )
    )
    family_hardening_reliability_reason_code = str(
        health.get("familyHardeningReliabilityReasonCode")
        or (
            family_hardening_reliability_reason_codes[0]
            if family_hardening_reliability_reason_codes
            else (
                f"family_hardening_reliability_{family_hardening_reliability_class}"
                if family_hardening_reliability_class != "stable"
                else "ok"
            )
        )
    )
    if (
        family_hardening_reliability_reason_code != "ok"
        and family_hardening_reliability_reason_code
        not in family_hardening_reliability_reason_codes
    ):
        family_hardening_reliability_reason_codes = [
            family_hardening_reliability_reason_code,
            *family_hardening_reliability_reason_codes,
        ]
    family_hardening_recovered_fragile = bool(
        health.get(
            "familyHardeningRecoveredFragile",
            recovery_history_status == "recovered"
            and family_hardening_reliability_class == "fragile",
        )
    )
    recovery_reliability_reason_codes = _unique_strings(
        list(health.get("recoveryReliabilityReasonCodes") or [])
    )
    recovery_reliability_class = str(
        health.get("recoveryReliabilityClass")
        or (
            "blocked"
            if recovery_status == "global_execution_blocked"
            else (
                family_hardening_reliability_class
                if recovery_history_component == "family_hardening"
                else (
                    receipt_outcome_truth_reliability_class
                    if recovery_history_component == "receipt_outcome_truth"
                    else (
                        capital_truth_reliability_class
                        if recovery_history_component == "capital_truth"
                        else (
                            internal_prime_reliability_class
                            if recovery_history_component == "internal_prime_reconciliation"
                            else "stable"
                        )
                    )
                )
            )
        )
    )
    recovery_reliability_reason_code = str(
        health.get("recoveryReliabilityReasonCode")
        or (
            recovery_reliability_reason_codes[0]
            if recovery_reliability_reason_codes
            else (
                f"recovery_reliability_{recovery_reliability_class}"
                if recovery_reliability_class != "stable"
                else "ok"
            )
        )
    )
    if (
        recovery_reliability_reason_code != "ok"
        and recovery_reliability_reason_code not in recovery_reliability_reason_codes
    ):
        recovery_reliability_reason_codes = [
            recovery_reliability_reason_code,
            *recovery_reliability_reason_codes,
        ]
    if not recovery_reliability_reason_codes:
        if recovery_history_component == "family_hardening":
            recovery_reliability_reason_codes = _unique_strings(
                [
                    *(
                        [f"recovery_reliability_{recovery_reliability_class}"]
                        if recovery_reliability_class != "stable"
                        else []
                    ),
                    *family_hardening_reliability_reason_codes,
                ]
            )
        elif recovery_history_component == "receipt_outcome_truth":
            recovery_reliability_reason_codes = _unique_strings(
                [
                    *(
                        [f"recovery_reliability_{recovery_reliability_class}"]
                        if recovery_reliability_class != "stable"
                        else []
                    ),
                    *receipt_outcome_truth_reliability_reason_codes,
                ]
            )
    recovery_reliability_next_action = str(
        health.get("recoveryReliabilityNextAction")
        or recovery_next_action
        or recovery_freshness_next_action
    )
    recovery_recovered_fragile = bool(
        health.get(
            "recoveryRecoveredFragile",
            recovery_history_status == "recovered" and recovery_reliability_class == "fragile",
        )
    )
    return {
        "health": health,
        "hold_reason_code": hold_reason_code,
        "hold_reason_codes": hold_reason_codes,
        "global_execution_reason_codes": global_execution_reason_codes,
        "capital_truth_reason_codes": capital_truth_reason_codes,
        "receipt_outcome_truth_reason_codes": receipt_outcome_truth_reason_codes,
        "internal_prime_reason_codes": internal_prime_reason_codes,
        "family_hardening_reason_codes": family_hardening_reason_codes,
        "suggested_next_action": suggested_next_action,
        "recovery_status": recovery_status,
        "recovery_reason_code": recovery_reason_code,
        "recovery_reason_codes": recovery_reason_codes,
        "recovery_next_action": recovery_next_action,
        "recovery_ready": recovery_ready,
        "capital_truth_freshness_class": capital_truth_freshness_class,
        "capital_truth_freshness_reason_codes": capital_truth_freshness_reason_codes,
        "receipt_outcome_truth_freshness_class": receipt_outcome_truth_freshness_class,
        "receipt_outcome_truth_freshness_reason_codes": receipt_outcome_truth_freshness_reason_codes,
        "internal_prime_freshness_class": internal_prime_freshness_class,
        "internal_prime_freshness_reason_codes": internal_prime_freshness_reason_codes,
        "recovery_freshness_class": recovery_freshness_class,
        "recovery_freshness_reason_code": recovery_freshness_reason_code,
        "recovery_freshness_reason_codes": recovery_freshness_reason_codes,
        "recovery_freshness_next_action": recovery_freshness_next_action,
        "recovery_history_component": recovery_history_component,
        "recovery_history_status": recovery_history_status,
        "recovery_degraded_since_ts_ms": recovery_degraded_since_ts_ms,
        "recovery_recovered_at_ts_ms": recovery_recovered_at_ts_ms,
        "recovery_degraded_duration_ms": recovery_degraded_duration_ms,
        "recovery_degraded_count": recovery_degraded_count,
        "recovery_last_healthy_ts_ms": recovery_last_healthy_ts_ms,
        "recovery_recovered_recently": recovery_recovered_recently,
        "recovery_degradation_severity_class": recovery_degradation_severity_class,
        "capital_truth_recovery_history_status": capital_truth_recovery_history_status,
        "capital_truth_degraded_since_ts_ms": capital_truth_degraded_since_ts_ms,
        "capital_truth_recovered_at_ts_ms": capital_truth_recovered_at_ts_ms,
        "capital_truth_degraded_duration_ms": capital_truth_degraded_duration_ms,
        "capital_truth_degraded_count": capital_truth_degraded_count,
        "capital_truth_last_healthy_ts_ms": capital_truth_last_healthy_ts_ms,
        "capital_truth_recovered_recently": capital_truth_recovered_recently,
        "capital_truth_degradation_severity_class": capital_truth_degradation_severity_class,
        "receipt_outcome_truth_recovery_history_status": receipt_outcome_truth_recovery_history_status,
        "receipt_outcome_truth_degraded_since_ts_ms": receipt_outcome_truth_degraded_since_ts_ms,
        "receipt_outcome_truth_recovered_at_ts_ms": receipt_outcome_truth_recovered_at_ts_ms,
        "receipt_outcome_truth_degraded_duration_ms": receipt_outcome_truth_degraded_duration_ms,
        "receipt_outcome_truth_degraded_count": receipt_outcome_truth_degraded_count,
        "receipt_outcome_truth_last_healthy_ts_ms": receipt_outcome_truth_last_healthy_ts_ms,
        "receipt_outcome_truth_recovered_recently": receipt_outcome_truth_recovered_recently,
        "receipt_outcome_truth_degradation_severity_class": receipt_outcome_truth_degradation_severity_class,
        "internal_prime_recovery_history_status": internal_prime_recovery_history_status,
        "internal_prime_degraded_since_ts_ms": internal_prime_degraded_since_ts_ms,
        "internal_prime_recovered_at_ts_ms": internal_prime_recovered_at_ts_ms,
        "internal_prime_degraded_duration_ms": internal_prime_degraded_duration_ms,
        "internal_prime_degraded_count": internal_prime_degraded_count,
        "internal_prime_last_healthy_ts_ms": internal_prime_last_healthy_ts_ms,
        "internal_prime_recovered_recently": internal_prime_recovered_recently,
        "internal_prime_degradation_severity_class": internal_prime_degradation_severity_class,
        "capital_truth_reliability_class": capital_truth_reliability_class,
        "capital_truth_reliability_reason_code": capital_truth_reliability_reason_code,
        "capital_truth_reliability_reason_codes": capital_truth_reliability_reason_codes,
        "capital_truth_recovered_fragile": capital_truth_recovered_fragile,
        "receipt_outcome_truth_reliability_class": receipt_outcome_truth_reliability_class,
        "receipt_outcome_truth_reliability_reason_code": receipt_outcome_truth_reliability_reason_code,
        "receipt_outcome_truth_reliability_reason_codes": receipt_outcome_truth_reliability_reason_codes,
        "receipt_outcome_truth_recovered_fragile": receipt_outcome_truth_recovered_fragile,
        "internal_prime_reliability_class": internal_prime_reliability_class,
        "internal_prime_reliability_reason_code": internal_prime_reliability_reason_code,
        "internal_prime_reliability_reason_codes": internal_prime_reliability_reason_codes,
        "internal_prime_recovered_fragile": internal_prime_recovered_fragile,
        "family_hardening_reliability_class": family_hardening_reliability_class,
        "family_hardening_reliability_reason_code": family_hardening_reliability_reason_code,
        "family_hardening_reliability_reason_codes": family_hardening_reliability_reason_codes,
        "family_hardening_recovered_fragile": family_hardening_recovered_fragile,
        "recovery_reliability_class": recovery_reliability_class,
        "recovery_reliability_reason_code": recovery_reliability_reason_code,
        "recovery_reliability_reason_codes": recovery_reliability_reason_codes,
        "recovery_reliability_next_action": recovery_reliability_next_action,
        "recovery_recovered_fragile": recovery_recovered_fragile,
    }


def _hold_detail_message(
    reason_codes: List[str],
    suggested_next_action: str,
    *,
    prefix: str = "Command hold is active because",
) -> str:
    if not reason_codes:
        return ""
    detail = prefix + " " + " and ".join(_humanize_code(code) for code in reason_codes) + "."
    if suggested_next_action:
        detail += f" Next action: {_humanize_code(suggested_next_action)}."
    return detail


def _profit_after_costs_info(opp: Dict[str, Any]) -> tuple[int, bool, str]:
    truth = inspect_profit_after_costs_truth(_safe_dict(opp.get("meta")))
    return int(max(0, truth.value_wei)), bool(truth.verified), str(truth.reason_code)


def _route_execution_info(opp: Dict[str, Any]) -> Dict[str, Any]:
    meta = _safe_dict(opp.get("meta"))
    route_truth = execution_route_truth(meta)
    return {
        "ready": bool(route_truth.get("ready", False)),
        "reason": str(route_truth.get("reason") or "execution_route_not_ready"),
        "reason_codes": list(route_truth.get("reason_codes") or []),
        "runtime_degraded": bool(route_truth.get("runtime_degraded", False)),
        "runtime_reason_codes": list(route_truth.get("runtime_reason_codes") or []),
        "plan_executable": bool(route_truth.get("plan_executable", True)),
        "invalid_causes": list(route_truth.get("invalid_causes") or []),
    }


def _execution_eligibility_info(opp: Dict[str, Any]) -> tuple[bool, bool, str]:
    can_execute = bool(opp.get("can_execute", False))
    meta = _safe_dict(opp.get("meta"))
    safety = _safe_dict(meta.get("safety"))
    if not can_execute:
        exec_ready = bool(safety.get("exec_ready", False)) if "exec_ready" in safety else False
        return False, exec_ready, str(safety.get("reason") or "simulation_not_ok")
    route_info = _route_execution_info(opp)
    if not bool(route_info.get("ready", True)):
        return True, False, str(route_info.get("reason") or "execution_route_not_ready")
    if "exec_ready" not in safety:
        return True, False, "exec_ready_unavailable"
    exec_ready = bool(safety.get("exec_ready", False))
    if not exec_ready:
        return True, False, str(safety.get("reason") or "execution_not_ready")
    return True, True, "ok"


_OPERATOR_SUMMARY_COMPONENT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class OperatorSummaryService:
    def __init__(
        self,
        *,
        state_summary: StateSummaryService | None = None,
        auxiliary_state: AuxiliaryStateService | None = None,
    ) -> None:
        self.state_summary = state_summary or StateSummaryService()
        self.auxiliary_state = auxiliary_state or AuxiliaryStateService()

    @staticmethod
    async def _base_snapshot(runtime: Any) -> Dict[str, Any]:
        snapshot_fn = getattr(runtime, "snapshot", None)
        if snapshot_fn is None:
            return {}
        try:
            payload = await snapshot_fn()
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            return {}
        return dict(payload) if isinstance(payload, ABCMapping) else {}

    @staticmethod
    def _runtime_mapping(
        runtime: Any,
        *,
        method_name: str,
        default: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not hasattr(runtime, method_name):
            return dict(default)
        try:
            payload = getattr(runtime, method_name)()
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            return dict(default)
        return dict(payload) if isinstance(payload, ABCMapping) else dict(default)

    @staticmethod
    def _family_hardening_default() -> Dict[str, Any]:
        return family_hardening_unavailable_summary()

    @staticmethod
    def _auto_trade_recovery_view(recovery: Dict[str, Any]) -> Dict[str, Any]:
        history_status = str(recovery.get("history_status") or "steady")
        stage = str(recovery.get("stage") or "")
        if history_status == "recovered" and (not stage or stage == "ok"):
            stage = str(recovery.get("history_stage") or stage or "ok")
        if not stage:
            stage = "ok"
        reason_codes = [str(x) for x in list(recovery.get("reason_codes") or []) if str(x)]
        reason_code = str(recovery.get("reason_code") or "")
        if history_status == "recovered" and (not reason_code or reason_code == "ok"):
            history_reason_codes = [
                str(x) for x in list(recovery.get("history_reason_codes") or []) if str(x)
            ]
            reason_code = str(
                recovery.get("history_reason_code")
                or (history_reason_codes[0] if history_reason_codes else "")
                or (reason_codes[0] if reason_codes else "")
                or reason_code
                or "ok"
            )
            if history_reason_codes:
                reason_codes = history_reason_codes
        if not reason_code:
            reason_code = "ok"
        return {
            "blocked": bool(recovery.get("blocked", False)),
            "ready": bool(recovery.get("ready", True)),
            "stage": stage,
            "status": str(recovery.get("status") or "ready"),
            "reasonCode": reason_code,
            "reasonCodes": reason_codes,
            "suggestedNextAction": str(
                recovery.get("next_action")
                or recovery.get("component_reliability_next_action")
                or recovery.get("reliability_next_action")
                or ""
            ),
            "component": str(recovery.get("component") or recovery.get("history_component") or ""),
            "historyStatus": history_status,
            "degradedSinceTsMs": int(recovery.get("degraded_since_ts_ms") or 0),
            "recoveredAtTsMs": int(recovery.get("recovered_at_ts_ms") or 0),
            "degradedDurationMs": int(recovery.get("degraded_duration_ms") or 0),
            "degradedCount": int(recovery.get("degraded_count") or 0),
            "lastHealthyTsMs": int(recovery.get("last_healthy_ts_ms") or 0),
            "recoveredRecently": bool(recovery.get("recovered_recently", False)),
            "degradationSeverityClass": str(recovery.get("degradation_severity_class") or "stable"),
            "historyComponent": str(
                recovery.get("history_component") or recovery.get("component") or ""
            ),
            "historyStage": str(recovery.get("history_stage") or recovery.get("stage") or "ok"),
            "reliabilityClass": str(recovery.get("reliability_class") or "stable"),
            "reliabilityReasonCode": str(recovery.get("reliability_reason_code") or "ok"),
            "reliabilityReasonCodes": [
                str(x) for x in list(recovery.get("reliability_reason_codes") or []) if str(x)
            ],
            "reliabilityNextAction": str(recovery.get("reliability_next_action") or ""),
            "componentReliabilityClass": str(
                recovery.get("component_reliability_class")
                or recovery.get("reliability_class")
                or "stable"
            ),
            "componentReliabilityReasonCode": str(
                recovery.get("component_reliability_reason_code")
                or recovery.get("reliability_reason_code")
                or "ok"
            ),
            "componentReliabilityReasonCodes": [
                str(x)
                for x in list(
                    recovery.get("component_reliability_reason_codes")
                    or recovery.get("reliability_reason_codes")
                    or []
                )
                if str(x)
            ],
            "componentReliabilityNextAction": str(
                recovery.get("component_reliability_next_action")
                or recovery.get("reliability_next_action")
                or ""
            ),
            "componentRecoveredFragile": bool(
                recovery.get(
                    "component_recovered_fragile",
                    str(recovery.get("history_status") or "") == "recovered"
                    and str(
                        recovery.get("component_reliability_class")
                        or recovery.get("reliability_class")
                        or ""
                    )
                    == "fragile",
                )
            ),
            "familyHardeningReasonCodes": [
                str(x) for x in list(recovery.get("family_hardening_reason_codes") or []) if str(x)
            ],
            "receiptOutcomeTruthReasonCodes": [
                str(x)
                for x in list(recovery.get("receipt_outcome_truth_reason_codes") or [])
                if str(x)
            ],
            "history": [
                {
                    "tsMs": int(item.get("ts_ms") or 0),
                    "eventType": str(item.get("event_type") or ""),
                    "stage": (
                        str(item.get("history_stage") or item.get("stage") or "ok")
                        if str(item.get("history_status") or "") == "recovered"
                        and bool(
                            item.get("component_recovered_fragile", False)
                            or str(
                                item.get("component_reliability_class")
                                or item.get("reliability_class")
                                or ""
                            )
                            == "fragile"
                        )
                        and str(item.get("stage") or "") in {"", "ok"}
                        else str(item.get("stage") or "ok")
                    ),
                    "reasonCode": (
                        str(
                            item.get("history_reason_code")
                            or (
                                [
                                    str(x)
                                    for x in list(item.get("history_reason_codes") or [])
                                    if str(x)
                                ][0]
                                if [
                                    str(x)
                                    for x in list(item.get("history_reason_codes") or [])
                                    if str(x)
                                ]
                                else ""
                            )
                            or item.get("reason_code")
                            or "ok"
                        )
                        if str(item.get("history_status") or "") == "recovered"
                        and bool(
                            item.get("component_recovered_fragile", False)
                            or str(
                                item.get("component_reliability_class")
                                or item.get("reliability_class")
                                or ""
                            )
                            == "fragile"
                        )
                        and str(item.get("reason_code") or "") in {"", "ok"}
                        else str(item.get("reason_code") or "ok")
                    ),
                    "reasonCodes": (
                        [str(x) for x in list(item.get("history_reason_codes") or []) if str(x)]
                        if str(item.get("history_status") or "") == "recovered"
                        and bool(
                            item.get("component_recovered_fragile", False)
                            or str(
                                item.get("component_reliability_class")
                                or item.get("reliability_class")
                                or ""
                            )
                            == "fragile"
                        )
                        and [str(x) for x in list(item.get("history_reason_codes") or []) if str(x)]
                        and not [str(x) for x in list(item.get("reason_codes") or []) if str(x)]
                        else [str(x) for x in list(item.get("reason_codes") or []) if str(x)]
                    ),
                    "component": str(
                        item.get("blocker_component") or item.get("history_component") or ""
                    ),
                    "suggestedNextAction": str(
                        item.get("next_action")
                        or item.get("component_reliability_next_action")
                        or item.get("reliability_next_action")
                        or ""
                    ),
                    "historyStatus": str(item.get("history_status") or "steady"),
                    "degraded": bool(
                        item.get(
                            "degraded",
                            str(item.get("history_status") or "") in {"blocked", "degraded"},
                        )
                    ),
                    "degradedSinceTsMs": int(item.get("degraded_since_ts_ms") or 0),
                    "recoveredAtTsMs": int(item.get("recovered_at_ts_ms") or 0),
                    "lastHealthyTsMs": int(item.get("last_healthy_ts_ms") or 0),
                    "updatedTsMs": int(item.get("updated_ts_ms") or 0),
                    "degradedCount": int(item.get("degraded_count") or 0),
                    "historyComponent": str(
                        item.get("history_component") or item.get("blocker_component") or ""
                    ),
                    "historyStage": str(item.get("history_stage") or item.get("stage") or "ok"),
                    "reliabilityClass": str(item.get("reliability_class") or "stable"),
                    "reliabilityReasonCode": str(item.get("reliability_reason_code") or "ok"),
                    "reliabilityReasonCodes": [
                        str(x) for x in list(item.get("reliability_reason_codes") or []) if str(x)
                    ],
                    "reliabilityNextAction": str(item.get("reliability_next_action") or ""),
                    "componentReliabilityClass": str(
                        item.get("component_reliability_class")
                        or item.get("reliability_class")
                        or "stable"
                    ),
                    "componentReliabilityReasonCode": str(
                        item.get("component_reliability_reason_code")
                        or item.get("reliability_reason_code")
                        or "ok"
                    ),
                    "componentReliabilityReasonCodes": [
                        str(x)
                        for x in list(
                            item.get("component_reliability_reason_codes")
                            or item.get("reliability_reason_codes")
                            or []
                        )
                        if str(x)
                    ],
                    "componentReliabilityNextAction": str(
                        item.get("component_reliability_next_action")
                        or item.get("reliability_next_action")
                        or ""
                    ),
                    "componentRecoveredFragile": bool(
                        item.get(
                            "component_recovered_fragile",
                            str(item.get("history_status") or "") == "recovered"
                            and str(
                                item.get("component_reliability_class")
                                or item.get("reliability_class")
                                or ""
                            )
                            == "fragile",
                        )
                    ),
                    "familyHardeningReasonCodes": [
                        str(x)
                        for x in list(item.get("family_hardening_reason_codes") or [])
                        if str(x)
                    ],
                    "receiptOutcomeTruthReasonCodes": [
                        str(x)
                        for x in list(item.get("receipt_outcome_truth_reason_codes") or [])
                        if str(x)
                    ],
                }
                for item in list(recovery.get("recent_events") or [])
                if isinstance(item, dict)
            ],
        }

    @staticmethod
    def _execution_auto_trading(runtime: Any, metrics: Dict[str, Any]) -> bool:
        metric_value = metrics.get("auto_trading")
        if metric_value is not None:
            return bool(metric_value)
        if hasattr(runtime, "_auto_trading"):
            return bool(getattr(runtime, "_auto_trading", False))
        cfg = getattr(runtime, "cfg", None)
        execution = getattr(cfg, "execution", None) if cfg is not None else None
        return bool(getattr(execution, "auto_trading", False))

    def _wealth_goal_view(
        self, runtime: Any
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
        if not hasattr(runtime, "wealth_goal_state"):
            return None, None
        try:
            wg_state = runtime.wealth_goal_state() or {}
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            return None, None
        if not isinstance(wg_state, dict) or not bool(wg_state.get("ok")):
            return None, None
        wealth_goal_details = wg_state
        state = _safe_dict(wg_state.get("state"))
        wealth_goal = {
            "targetReturnPct": _safe_float(state.get("targetReturnPct")),
            "timeframeDays": _safe_int(state.get("timeframeDays"), 7),
            "riskTolerance": str(state.get("riskTolerance") or "moderate"),
            "maxDrawdownPct": _safe_float(state.get("maxDrawdownPct")),
            "capitalCommitmentPct": _safe_float(state.get("capitalCommitmentPct")),
            "currentReturnPct": _safe_float(state.get("currentReturnPct")),
            "progressPct": _safe_float(state.get("progressPct")),
            "goalAchieved": bool(state.get("goalAchieved")),
            "suggestedNextTargetPct": _safe_float(state.get("suggestedNextTargetPct")),
            "goalId": str(state.get("goalId") or ""),
            "activeSinceMs": _safe_int(state.get("activeSinceMs")),
            "achievedAtMs": _safe_int(state.get("achievedAtMs")),
            "nextGoalAllowed": bool(state.get("nextGoalAllowed", True)),
            "pacing": str(state.get("pacing") or ""),
            "aggressivenessCap": _safe_float(state.get("aggressivenessCap"), 1.0),
            "capitalBaseUsd": _safe_float(state.get("capitalBaseUsd")),
            "executionRealismScore": _safe_float(state.get("executionRealismScore")),
            "stabilityScore": _safe_float(state.get("stabilityScore")),
            "nextGoalReasons": list(state.get("nextGoalReasons") or []),
            "nextGoalBlockedReasons": list(state.get("nextGoalBlockedReasons") or []),
            "goalLadder": list(state.get("goalLadder") or []),
            "pacingReasons": list(state.get("pacingReasons") or []),
            "goalStatus": str(state.get("goalStatus") or "active"),
            "goalUrgency": str(state.get("goalUrgency") or "steady"),
            "nextGoalAggressivenessHint": _safe_float(state.get("nextGoalAggressivenessHint"), 1.0),
            "blockedGoalReasonCodes": list(state.get("blockedGoalReasonCodes") or []),
            "goalVelocityPctPerDay": _safe_float(state.get("goalVelocityPctPerDay")),
            "goalHorizonCompatibility": _safe_float(state.get("goalHorizonCompatibility"), 1.0),
            "explanation": _safe_dict(wg_state.get("explanation")),
            "history": list(wg_state.get("history") or []),
        }
        return wealth_goal, wealth_goal_details

    def _audit_items(self, runtime: Any, *, limit: int = 250) -> List[Dict[str, Any]]:
        cc = getattr(runtime, "_cc", None)
        if cc is None:
            return []
        try:
            return list(cc.audit.tail(limit=limit))
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            return []

    def _governance_history(self, audit_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for it in audit_items:
            if str(it.get("kind")) != "governance_change":
                continue
            payload = _safe_dict(it.get("payload"))
            out.append(
                {
                    "id": str(it.get("hash") or ""),
                    "tsMs": _safe_int(it.get("ts_ms")),
                    "actor": str(it.get("actor") or ""),
                    "action": "Controls updated",
                    "reason": str(it.get("reason") or ""),
                    "before": _safe_dict(payload.get("before")),
                    "after": _safe_dict(payload.get("after")),
                    "hash": str(it.get("hash") or ""),
                    "prevHash": str(it.get("prev_hash") or ""),
                }
            )
        return out[:50]

    def _decision_feed(self, audit_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        decisions: List[Dict[str, Any]] = []
        for it in audit_items[::-1]:
            if str(it.get("kind")) not in {"trade_lifecycle", "execution_veto", "trade_outcome"}:
                continue
            payload = _safe_dict(it.get("payload"))
            intent = str(payload.get("reason") or payload.get("mode") or "trade_event")
            rtrace = _safe_dict(payload.get("reward_trace"))
            ppm = _safe_int(rtrace.get("reward_scaled_ppm")) if rtrace else 0
            reward = ppm / 1_000_000.0
            strategy_value = (
                payload.get("strategy_family")
                or payload.get("family")
                or payload.get("route_family")
                or "flashloan_atomic"
            )
            decisions.append(
                {
                    "id": str(it.get("hash") or ""),
                    "tsMs": _safe_int(it.get("ts_ms")),
                    "intent": intent,
                    "confidence": 0.75,
                    **_canonical_strategy_projection(strategy_value),
                    "outcome": (
                        "success"
                        if bool(payload.get("ok"))
                        else ("skipped" if str(it.get("kind")) == "execution_veto" else "fail")
                    ),
                    "reward": float(reward),
                    "rewardTrace": rtrace,
                    "notes": str(payload.get("route_id") or ""),
                }
            )
        return decisions[:50]

    async def build_snapshot(self, runtime: Any) -> Dict[str, Any]:
        base = await self._base_snapshot(runtime)
        metrics = _safe_dict(base.get("metrics"))
        chain = str(
            base.get("chain") or getattr(getattr(runtime, "cfg", None), "chain", None) or ""
        )
        cc = getattr(runtime, "_cc", None)
        controls = getattr(cc, "controls", None) if cc is not None else None
        auto_trading = self._execution_auto_trading(runtime, metrics)
        paused = (
            bool(getattr(controls, "paused", False)) if controls is not None else (not auto_trading)
        )
        sandbox_only = (
            bool(getattr(controls, "sandbox_only", False)) if controls is not None else False
        )
        defensive = (
            bool(getattr(controls, "defensive_mode", False)) if controls is not None else False
        )
        explicit_mode = (
            str(getattr(controls, "control_mode", "") or "").strip().lower()
            if controls is not None
            else ""
        )
        control_mode = (
            explicit_mode
            if explicit_mode in {"view_only", "assist", "auto"}
            else ("view_only" if paused else ("auto" if auto_trading else "assist"))
        )
        if control_mode == "view_only":
            paused = True
        elif control_mode in {"assist", "auto"}:
            paused = False
        sys_state = (
            "paused"
            if paused
            else ("sandbox_only" if sandbox_only else ("defensive" if defensive else "active"))
        )

        try:
            pnl = await runtime._pnl.summary(window=50)  # type: ignore[attr-defined]
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            pnl = {}
        capital_context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=self.auxiliary_state,
            state_summary=self.state_summary,
        )
        capital_truth = capital_context.capital_truth
        capital_summary = dict(capital_context.capital_summary or {})
        nav_usd = float(capital_summary.get("navUsd") or 0.0)
        rpc_state = _safe_dict(base.get("rpc"))
        opportunities = list(base.get("opportunities") or []) if isinstance(base, dict) else []
        opps_after_cost_positive = 0
        opps_executable = 0
        for o in opportunities:
            if not isinstance(o, dict):
                continue
            profit_after, verified, _reason = _profit_after_costs_info(o)
            if not (verified and profit_after > 0):
                continue
            opps_after_cost_positive += 1
            can_execute, exec_ready, _eligibility_reason = _execution_eligibility_info(o)
            if can_execute and exec_ready:
                opps_executable += 1
        obs = {
            "loopMsP50": _safe_float(metrics.get("loop_p50_ms") or metrics.get("last_tick_ms")),
            "loopMsP90": _safe_float(metrics.get("loop_p90_ms")),
            "loopMsP99": _safe_float(metrics.get("loop_p99_ms")),
            "rpcErrRate": _safe_float(rpc_state.get("error_rate")),
            "oppsSeen": len(opportunities),
            "oppsAfterCostPositive": opps_after_cost_positive,
            "oppsExecutable": opps_executable,
            "execLatencyMsP50": _safe_float(metrics.get("exec_e2e_p50_ms")),
            "execLatencyMsP90": _safe_float(metrics.get("exec_e2e_p90_ms")),
            "execLatencyMsP99": _safe_float(metrics.get("exec_e2e_p99_ms")),
            "submitToReceiptMsP50": _safe_float(metrics.get("submit_to_receipt_p50_ms")),
            "submitToReceiptMsP90": _safe_float(metrics.get("submit_to_receipt_p90_ms")),
            "submitToReceiptMsP99": _safe_float(metrics.get("submit_to_receipt_p99_ms")),
        }
        rpc_degraded = bool(_safe_float(rpc_state.get("error_rate")) >= 0.10)
        if not rpc_degraded:
            for bucket in ("read", "send"):
                entries = rpc_state.get(bucket) or []
                if isinstance(entries, list) and any(
                    not bool((x or {}).get("ok", True)) for x in entries if isinstance(x, dict)
                ):
                    rpc_degraded = True
                    break
        gas_breaker = False
        an = getattr(runtime, "_anomaly", None)
        if an is not None and hasattr(an, "snapshot"):
            try:
                gas_breaker = bool(_safe_dict(an.snapshot()).get("gas_spike"))
            except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
                gas_breaker = False
        audit_items = self._audit_items(runtime)
        gov_hist = self._governance_history(audit_items)
        decisions = self._decision_feed(audit_items)
        storage_state = {}
        if cc is not None and hasattr(cc, "state"):
            try:
                storage_state = _safe_dict(cc.state())
            except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
                storage_state = {}
        pause_reason = ""
        if control_mode == "view_only":
            pause_reason = "View Only mode is active. Autonomous trading is disabled until you switch back to Assist or Auto."
        elif paused:
            pause_reason = "Trading is paused by operator control."
        elif control_mode == "assist":
            pause_reason = "Assist mode keeps live scanning and AI explanations on while autonomous execution stays off."
        elif sandbox_only:
            pause_reason = (
                "Sandbox-only mode is active. Execution stays in protected dry-run posture."
            )
        elif defensive:
            pause_reason = "Defensive mode is active. Risk clamps and anomaly breakers are steering sizing and send posture."
        if rpc_degraded:
            pause_reason = (
                pause_reason + " " if pause_reason else ""
            ) + "RPC health is degraded, so execution quality may be reduced."

        wealth_goal, wealth_goal_details = self._wealth_goal_view(runtime)
        market_regime = _safe_dict(getattr(runtime, "_market_regime", {}))
        meta_candidates: List[Dict[str, Any]] = []
        if hasattr(runtime, "meta_state"):
            try:
                mstate = runtime.meta_state() or {}
            except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
                mstate = {}
            for cand in list(_safe_dict(mstate).get("last_candidates") or [])[:12]:
                if not isinstance(cand, dict):
                    continue
                meta_candidates.append(
                    {
                        "id": str(cand.get("id") or ""),
                        "tsMs": int(_safe_float(cand.get("created_ts")) * 1000),
                        "title": str(cand.get("description") or "Candidate"),
                        "summary": str(cand.get("reason") or ""),
                        "expectedDeltaPct": _safe_float(cand.get("score")) * 100.0,
                        "riskDelta": (
                            _safe_float(
                                (_safe_dict(cand.get("stress_report")).get("risk_delta") or 0.0)
                            )
                            if isinstance(cand.get("stress_report"), dict)
                            else _safe_float(cand.get("correlation_penalty")) * 100.0
                        ),
                        "probationCapPct": float(
                            max(
                                0.5,
                                min(
                                    10.0,
                                    2.5
                                    + _safe_float(
                                        _safe_dict(cand.get("stress_report")).get(
                                            "robustness_score"
                                        )
                                    )
                                    * 4.0,
                                ),
                            )
                        ),
                        "status": (
                            "approved"
                            if str(cand.get("lifecycle_stage") or "")
                            in {"paper_trading", "production"}
                            else (
                                "rejected"
                                if str(cand.get("lifecycle_stage") or "") == "retired"
                                else "queued"
                            )
                        ),
                    }
                )
        try:
            capture_analytics = (
                runtime.execution_capture_analytics()
                if hasattr(runtime, "execution_capture_analytics")
                else {}
            )
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            capture_analytics = {}

        recent = list(_safe_dict(pnl).get("recent") or [])
        equity: List[Dict[str, Any]] = []
        realized_after_gas: List[Dict[str, Any]] = []
        drawdown_series: List[Dict[str, Any]] = []
        cum = 0.0
        peak = 0.0
        for r in reversed(recent[-40:]):
            if not isinstance(r, dict):
                continue
            usd_micro = _safe_int(r.get("realized_profit_after_gas_usd_micro"))
            usd = usd_micro / 1_000_000.0
            ts_ms = _safe_int(r.get("ts")) * 1000
            cum += usd
            equity.append({"tsMs": ts_ms, "navUsd": max(0.0, cum), "regime": ""})
            realized_after_gas.append({"tsMs": ts_ms, "valueUsd": usd})
            peak = max(peak, usd)
            dd = 0.0 if peak <= 0 else max(0.0, ((peak - usd) / peak) * 100.0)
            drawdown_series.append({"tsMs": ts_ms, "drawdownPct": round(dd, 4)})

        drawdown_state = self.state_summary.drawdown(runtime)
        family_hardening = self._runtime_mapping(
            runtime,
            method_name="family_hardening_state",
            default=self._family_hardening_default(),
        )
        fund_summary_state = self.state_summary.fund_summary(runtime)
        fund_hold_state = _fund_health_hold_state(fund_summary_state, family_hardening)
        capital_context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=self.auxiliary_state,
            state_summary=self.state_summary,
            fund_summary=fund_hold_state,
        )
        capital_truth = capital_context.capital_truth
        capital_summary = dict(capital_context.capital_summary or {})
        capital_truth_health = dict(capital_context.capital_truth_health or {})
        hard_stop_state = _safe_dict(drawdown_state.get("hardStop"))
        execution_gate = execution_gate_info(runtime)
        gate_reason_codes = _unique_strings(list(execution_gate.get("reason_codes") or []))
        global_execution_reason_codes = _unique_strings(
            gate_reason_codes + list(fund_hold_state.get("global_execution_reason_codes") or [])
        )
        hold_reason_codes = _unique_strings(
            list(fund_hold_state.get("hold_reason_codes") or []) + gate_reason_codes
        )
        hold_reason_code = str(
            fund_hold_state.get("hold_reason_code")
            or (hold_reason_codes[0] if hold_reason_codes else "")
        )
        suggested_next_action = str(fund_hold_state.get("suggested_next_action") or "")
        recovery_status = str(fund_hold_state.get("recovery_status") or "ready")
        recovery_reason_code = str(fund_hold_state.get("recovery_reason_code") or "ok")
        recovery_reason_codes = list(fund_hold_state.get("recovery_reason_codes") or [])
        recovery_next_action = str(
            fund_hold_state.get("recovery_next_action") or suggested_next_action
        )
        recovery_ready = bool(fund_hold_state.get("recovery_ready", recovery_status == "ready"))
        capital_truth_reason_codes = list(fund_hold_state.get("capital_truth_reason_codes") or [])
        internal_prime_reason_codes = list(fund_hold_state.get("internal_prime_reason_codes") or [])
        family_hardening_reason_codes = list(
            fund_hold_state.get("family_hardening_reason_codes") or []
        )
        posture_hold_reason_codes = _unique_strings(
            family_hardening_reason_codes + capital_truth_reason_codes + internal_prime_reason_codes
        )
        recovery_reliability_class = str(
            fund_hold_state.get("recovery_reliability_class") or "stable"
        )
        recovery_reliability_reason_code = str(
            fund_hold_state.get("recovery_reliability_reason_code")
            or (
                f"recovery_reliability_{recovery_reliability_class}"
                if recovery_reliability_class != "stable"
                else "ok"
            )
        )
        recovery_reliability_reason_codes = _unique_strings(
            list(fund_hold_state.get("recovery_reliability_reason_codes") or [])
        )
        if (
            recovery_reliability_reason_code != "ok"
            and recovery_reliability_reason_code not in recovery_reliability_reason_codes
        ):
            recovery_reliability_reason_codes = [
                recovery_reliability_reason_code,
                *recovery_reliability_reason_codes,
            ]
        recovery_reliability_next_action = str(
            fund_hold_state.get("recovery_reliability_next_action") or recovery_next_action
        )
        reliability_advisory_active = recovery_reliability_class not in {"", "stable"}
        reliability_advisory_severity = (
            "warning"
            if recovery_reliability_class
            in {"blocked", "unavailable", "unknown", "degraded", "fragile"}
            else ("caution" if recovery_reliability_class == "cautious" else "normal")
        )
        gate_blocked = bool(execution_gate.get("blocked", False))
        if gate_blocked:
            sys_state = "paused"
            gate_reasons = []
            if bool(execution_gate.get("drawdown_hard_stop_active", False)):
                gate_reasons.append("drawdown hard stop is active")
            if bool(execution_gate.get("kill_switch_active", False)):
                gate_reasons.append("kill switch suppressions are active")
            gate_reason_text = (
                " and ".join(gate_reasons)
                if gate_reasons
                else "global execution safety gates are active"
            )
            gate_message = f"Execution is safety-blocked because {gate_reason_text}."
            pause_reason = (pause_reason + " " if pause_reason else "") + gate_message
            opps_executable = 0
            obs["oppsExecutable"] = 0
        elif sys_state == "active" and posture_hold_reason_codes:
            sys_state = "defensive"
            opps_executable = 0
            obs["oppsExecutable"] = 0
        elif sys_state == "active" and reliability_advisory_severity == "warning":
            sys_state = "defensive"
        extra_hold_reason_codes = [
            code for code in hold_reason_codes if code and code not in gate_reason_codes
        ]
        hold_prefix = (
            "System posture is defensive because"
            if sys_state == "defensive" and not gate_blocked
            else "Command hold is active because"
        )
        hold_detail = _hold_detail_message(
            extra_hold_reason_codes,
            suggested_next_action,
            prefix=hold_prefix,
        )
        if hold_detail:
            pause_reason = (pause_reason + " " if pause_reason else "") + hold_detail
        if reliability_advisory_active:
            reliability_detail = _hold_detail_message(
                recovery_reliability_reason_codes,
                recovery_reliability_next_action,
                prefix=(
                    "System posture is defensive because recovery reliability is"
                    if reliability_advisory_severity == "warning"
                    else "Recovery reliability is"
                ),
            )
            if reliability_detail:
                pause_reason = (pause_reason + " " if pause_reason else "") + reliability_detail
        top_candidate = select_top_opportunity(list(getattr(runtime, "_opps", []) or []))
        _, auto_trade_gate_snake, auto_trade_recovery_snake = resolve_auto_trade_gate_and_recovery(
            runtime,
            top_candidate,
        )
        gate_stage = str(auto_trade_gate_snake.get("stage") or "ok")
        gate_reason = str(auto_trade_gate_snake.get("reason_code") or "ok")
        gate_reason_codes = [
            str(x) for x in list(auto_trade_gate_snake.get("reason_codes") or []) if str(x)
        ]
        gate_next_action = str(auto_trade_gate_snake.get("next_action") or "")
        if (
            gate_stage == "family_hold"
            and gate_reason == "family_hardening_unavailable"
            and gate_next_action == "restore_family_hardening"
        ):
            gate_reason = "family_hardening_service_unavailable"
            gate_reason_codes = [
                (
                    "family_hardening_service_unavailable"
                    if code == "family_hardening_unavailable"
                    else code
                )
                for code in gate_reason_codes
            ]
        auto_trade_gate = {
            "allowed": bool(auto_trade_gate_snake.get("allowed", True)),
            "stage": gate_stage,
            "reasonCode": gate_reason,
            "reasonCodes": gate_reason_codes,
            "suggestedNextAction": gate_next_action,
        }
        auto_trade_recovery = self._auto_trade_recovery_view(auto_trade_recovery_snake)
        if not bool(auto_trade_gate.get("allowed", True)):
            gate_detail = _hold_detail_message(
                gate_reason_codes or [gate_reason],
                gate_next_action,
                prefix="Autonomous execution is blocked because",
            )
            if gate_detail:
                pause_reason = (pause_reason + " " if pause_reason else "") + gate_detail
        receipt_summary = self.state_summary.receipt_summary(runtime)
        execution_quality = {
            "endpointQuality": self._runtime_mapping(
                runtime,
                method_name="endpoint_quality_state",
                default={"lanes": {}, "summary": {}, "generatedAtMs": 0},
            ),
            "endpointUniverse": self.state_summary.endpoint_universe(runtime),
            "routeQuality": self.state_summary.route_quality(runtime),
            "liveExecution": self.state_summary.execution_live(runtime),
            "drawdown": drawdown_state,
            "killSwitch": self.state_summary.kill_switch(runtime),
        }
        services = self.state_summary.service_health(runtime)
        v1_focus_info = _family_identity_payload(
            getattr(
                getattr(getattr(runtime, "cfg", None), "execution", None),
                "v1_focus",
                "flashloan_atomic",
            )
        )
        v1_strategy_projection = _canonical_strategy_projection(v1_focus_info.get("runtimeFamily"))
        execution_lifecycles = build_execution_lifecycle_projections(
            live_execution=execution_quality.get("liveExecution") or {},
            receipt_summary=receipt_summary,
            auto_trade_gate=auto_trade_gate,
            execution_gate=execution_gate,
            v1_focus=v1_focus_info,
        )
        flashloan_lifecycle = select_focus_execution_lifecycle(execution_lifecycles, v1_focus_info)
        payload = {
            "ok": True,
            "portfolio": {
                "navUsd": float(nav_usd),
                "navSource": str(capital_summary.get("navSource") or "unknown"),
                "pct24h": 0.0,
                "pct7d": 0.0,
                "drawdownPct": _safe_float(drawdown_state.get("drawdownPct")),
                "state": sys_state,
                "updatedAtMs": int(time.time() * 1000),
            },
            "aiIntent": {
                "intent": "Flash-loan atomic arbitrage only (v1). Compound safely under deterministic gates.",
                "confidence": 0.75,
                **v1_strategy_projection,
            },
            "exposure": {
                "activePct": 60,
                "sandboxPct": 10,
                "idlePct": 25,
                "atRiskPct": _safe_float(
                    _safe_dict(capital_summary.get("exposure")).get("atRiskPct")
                ),
            },
            "alerts": [
                {
                    "id": "cc_v1",
                    "tsMs": int(time.time() * 1000),
                    "severity": "info",
                    "title": "v1 focus locked",
                    "detail": "System is scoped to flash-loan atomic arbitrage until alpha is proven.",
                },
                {
                    "id": "cc_nav",
                    "tsMs": int(time.time() * 1000),
                    "severity": "warn" if nav_usd == 0.0 else "info",
                    "title": "USD NAV availability",
                    "detail": "USD series uses realized_after_gas_usd_micro when available; otherwise shows 0 (analytics-only).",
                },
            ],
            "allocations": list(
                capital_summary.get("allocations")
                or [
                    {
                        "id": "atomic_core",
                        "name": "Flashloan Atomic",
                        "capitalUsd": float(nav_usd),
                        "roiPct": _safe_float(_safe_dict(pnl).get("efficiency_pct")),
                        "volPct": 0.0,
                        "riskScore": 35,
                        "status": "active" if not paused else "paused",
                    },
                ]
            ),
            "capitalFlows": list(capital_summary.get("capitalFlows") or []),
            "decisions": decisions,
            "receiptSummary": build_receipt_summary_projection(receipt_summary),
            "flashloanArbLifecycle": flashloan_lifecycle,
            "executionLifecycles": execution_lifecycles,
            "regime": {
                "current": str(market_regime.get("regime") or "unknown"),
                "confidence": _safe_float(market_regime.get("confidence"), 0.6),
                "history": [],
            },
            "risk": {
                "composite": 40,
                "caps": {
                    "maxDailyLossPct": _safe_float(
                        getattr(
                            getattr(getattr(runtime, "cfg", None), "safety", None),
                            "max_daily_loss_pct",
                            3.0,
                        )
                    ),
                    "maxExposurePct": 80.0,
                    "sandboxCapPct": 10.0,
                    "probationCapPct": 2.5,
                },
                "breakers": {
                    "drawdownBreaker": bool(hard_stop_state.get("active", False)),
                    "gasAnomalyBreaker": bool(gas_breaker),
                    "driftBreaker": False,
                },
            },
            "controlMode": control_mode,
            "pausedReason": pause_reason,
            "rpcDegraded": rpc_degraded,
            "executionGate": execution_gate,
            "autoTradeGate": auto_trade_gate,
            "autoTradeRecovery": auto_trade_recovery,
            "globalExecutionBlocked": bool(global_execution_reason_codes),
            "globalExecutionReasonCodes": global_execution_reason_codes,
            "capitalTruthReasonCodes": capital_truth_reason_codes,
            "receiptOutcomeTruthReasonCodes": list(
                fund_hold_state.get("receipt_outcome_truth_reason_codes") or []
            ),
            "internalPrimeReasonCodes": internal_prime_reason_codes,
            "familyHardeningReasonCodes": family_hardening_reason_codes,
            "holdReasonCode": hold_reason_code,
            "holdReasonCodes": hold_reason_codes,
            "suggestedNextAction": suggested_next_action if hold_reason_code else "",
            "recoveryStatus": recovery_status,
            "recoveryReasonCode": recovery_reason_code,
            "recoveryReasonCodes": recovery_reason_codes,
            "recoveryNextAction": recovery_next_action if recovery_reason_codes else "",
            "recoveryReady": recovery_ready,
            "capitalTruthFreshnessClass": str(
                fund_hold_state.get("capital_truth_freshness_class") or ""
            ),
            "capitalTruthFreshnessReasonCodes": list(
                fund_hold_state.get("capital_truth_freshness_reason_codes") or []
            ),
            "receiptOutcomeTruthFreshnessClass": str(
                fund_hold_state.get("receipt_outcome_truth_freshness_class") or ""
            ),
            "receiptOutcomeTruthFreshnessReasonCodes": list(
                fund_hold_state.get("receipt_outcome_truth_freshness_reason_codes") or []
            ),
            "internalPrimeFreshnessClass": str(
                fund_hold_state.get("internal_prime_freshness_class") or ""
            ),
            "internalPrimeFreshnessReasonCodes": list(
                fund_hold_state.get("internal_prime_freshness_reason_codes") or []
            ),
            "recoveryFreshnessClass": str(
                fund_hold_state.get("recovery_freshness_class")
                or ("current" if recovery_ready else "unknown")
            ),
            "recoveryFreshnessReasonCode": str(
                fund_hold_state.get("recovery_freshness_reason_code") or "ok"
            ),
            "recoveryFreshnessReasonCodes": list(
                fund_hold_state.get("recovery_freshness_reason_codes") or []
            ),
            "recoveryFreshnessNextAction": str(
                fund_hold_state.get("recovery_freshness_next_action") or ""
            ),
            "recoveryHistoryComponent": str(
                fund_hold_state.get("recovery_history_component") or ""
            ),
            "recoveryHistoryStatus": str(
                fund_hold_state.get("recovery_history_status") or "steady"
            ),
            "recoveryDegradedSinceTsMs": int(
                fund_hold_state.get("recovery_degraded_since_ts_ms") or 0
            ),
            "recoveryRecoveredAtTsMs": int(fund_hold_state.get("recovery_recovered_at_ts_ms") or 0),
            "recoveryDegradedDurationMs": int(
                fund_hold_state.get("recovery_degraded_duration_ms") or 0
            ),
            "recoveryDegradedCount": int(fund_hold_state.get("recovery_degraded_count") or 0),
            "recoveryLastHealthyTsMs": int(fund_hold_state.get("recovery_last_healthy_ts_ms") or 0),
            "recoveryRecoveredRecently": bool(
                fund_hold_state.get("recovery_recovered_recently", False)
            ),
            "recoveryDegradationSeverityClass": str(
                fund_hold_state.get("recovery_degradation_severity_class") or "stable"
            ),
            "capitalTruthReliabilityClass": str(
                fund_hold_state.get("capital_truth_reliability_class") or "stable"
            ),
            "receiptOutcomeTruthReliabilityClass": str(
                fund_hold_state.get("receipt_outcome_truth_reliability_class") or "stable"
            ),
            "receiptOutcomeTruthReliabilityReasonCode": str(
                fund_hold_state.get("receipt_outcome_truth_reliability_reason_code") or "ok"
            ),
            "receiptOutcomeTruthReliabilityReasonCodes": list(
                fund_hold_state.get("receipt_outcome_truth_reliability_reason_codes") or []
            ),
            "receiptOutcomeTruthRecoveredFragile": bool(
                fund_hold_state.get("receipt_outcome_truth_recovered_fragile", False)
            ),
            "capitalTruthReliabilityReasonCode": str(
                fund_hold_state.get("capital_truth_reliability_reason_code") or "ok"
            ),
            "capitalTruthReliabilityReasonCodes": list(
                fund_hold_state.get("capital_truth_reliability_reason_codes") or []
            ),
            "capitalTruthRecoveredFragile": bool(
                fund_hold_state.get("capital_truth_recovered_fragile", False)
            ),
            "internalPrimeReliabilityClass": str(
                fund_hold_state.get("internal_prime_reliability_class") or "stable"
            ),
            "internalPrimeReliabilityReasonCode": str(
                fund_hold_state.get("internal_prime_reliability_reason_code") or "ok"
            ),
            "internalPrimeReliabilityReasonCodes": list(
                fund_hold_state.get("internal_prime_reliability_reason_codes") or []
            ),
            "internalPrimeRecoveredFragile": bool(
                fund_hold_state.get("internal_prime_recovered_fragile", False)
            ),
            "recoveryReliabilityClass": recovery_reliability_class,
            "recoveryReliabilityReasonCode": recovery_reliability_reason_code,
            "recoveryReliabilityReasonCodes": recovery_reliability_reason_codes,
            "recoveryReliabilityNextAction": recovery_reliability_next_action,
            "recoveryRecoveredFragile": bool(
                fund_hold_state.get("recovery_recovered_fragile", False)
            ),
            "executionAdvisoryActive": reliability_advisory_active,
            "executionAdvisorySeverity": reliability_advisory_severity,
            "executionAdvisoryClass": recovery_reliability_class,
            "executionAdvisoryReasonCode": recovery_reliability_reason_code,
            "executionAdvisoryReasonCodes": recovery_reliability_reason_codes,
            "executionAdvisoryNextAction": recovery_reliability_next_action,
            "capitalTruthRecoveryHistoryStatus": str(
                fund_hold_state.get("capital_truth_recovery_history_status") or "steady"
            ),
            "receiptOutcomeTruthRecoveryHistoryStatus": str(
                fund_hold_state.get("receipt_outcome_truth_recovery_history_status") or "steady"
            ),
            "receiptOutcomeTruthDegradedSinceTsMs": int(
                fund_hold_state.get("receipt_outcome_truth_degraded_since_ts_ms") or 0
            ),
            "receiptOutcomeTruthRecoveredAtTsMs": int(
                fund_hold_state.get("receipt_outcome_truth_recovered_at_ts_ms") or 0
            ),
            "receiptOutcomeTruthDegradedDurationMs": int(
                fund_hold_state.get("receipt_outcome_truth_degraded_duration_ms") or 0
            ),
            "receiptOutcomeTruthDegradedCount": int(
                fund_hold_state.get("receipt_outcome_truth_degraded_count") or 0
            ),
            "receiptOutcomeTruthLastHealthyTsMs": int(
                fund_hold_state.get("receipt_outcome_truth_last_healthy_ts_ms") or 0
            ),
            "receiptOutcomeTruthRecoveredRecently": bool(
                fund_hold_state.get("receipt_outcome_truth_recovered_recently", False)
            ),
            "receiptOutcomeTruthDegradationSeverityClass": str(
                fund_hold_state.get("receipt_outcome_truth_degradation_severity_class") or "stable"
            ),
            "capitalTruthDegradedSinceTsMs": int(
                fund_hold_state.get("capital_truth_degraded_since_ts_ms") or 0
            ),
            "capitalTruthRecoveredAtTsMs": int(
                fund_hold_state.get("capital_truth_recovered_at_ts_ms") or 0
            ),
            "capitalTruthDegradedDurationMs": int(
                fund_hold_state.get("capital_truth_degraded_duration_ms") or 0
            ),
            "capitalTruthDegradedCount": int(
                fund_hold_state.get("capital_truth_degraded_count") or 0
            ),
            "capitalTruthLastHealthyTsMs": int(
                fund_hold_state.get("capital_truth_last_healthy_ts_ms") or 0
            ),
            "capitalTruthRecoveredRecently": bool(
                fund_hold_state.get("capital_truth_recovered_recently", False)
            ),
            "capitalTruthDegradationSeverityClass": str(
                fund_hold_state.get("capital_truth_degradation_severity_class") or "stable"
            ),
            "internalPrimeRecoveryHistoryStatus": str(
                fund_hold_state.get("internal_prime_recovery_history_status") or "steady"
            ),
            "internalPrimeDegradedSinceTsMs": int(
                fund_hold_state.get("internal_prime_degraded_since_ts_ms") or 0
            ),
            "internalPrimeRecoveredAtTsMs": int(
                fund_hold_state.get("internal_prime_recovered_at_ts_ms") or 0
            ),
            "internalPrimeDegradedDurationMs": int(
                fund_hold_state.get("internal_prime_degraded_duration_ms") or 0
            ),
            "internalPrimeDegradedCount": int(
                fund_hold_state.get("internal_prime_degraded_count") or 0
            ),
            "internalPrimeLastHealthyTsMs": int(
                fund_hold_state.get("internal_prime_last_healthy_ts_ms") or 0
            ),
            "internalPrimeRecoveredRecently": bool(
                fund_hold_state.get("internal_prime_recovered_recently", False)
            ),
            "internalPrimeDegradationSeverityClass": str(
                fund_hold_state.get("internal_prime_degradation_severity_class") or "stable"
            ),
            "dataSource": "backend",
            "wealthGoal": wealth_goal,
            "wealthGoalDetails": wealth_goal_details,
            "governance": {
                "v1Focus": str(v1_focus_info.get("launchFamily") or ""),
                "v1FocusRuntimeFamily": str(v1_focus_info.get("runtimeFamily") or ""),
                "v1FocusCapitalFamily": str(v1_focus_info.get("capitalFamily") or ""),
                "v1FocusDisplayName": str(v1_focus_info.get("displayName") or ""),
                "v1FocusAliases": list(v1_focus_info.get("aliases") or []),
                "v1FocusIdentity": v1_focus_info,
                "aiAuthority": "bounded",
                "controlMode": control_mode,
                "governanceEnabled": (
                    bool(getattr(controls, "governance_enabled", True))
                    if controls is not None
                    else True
                ),
                "mutationEnabled": (
                    bool(getattr(controls, "mutation_enabled", False))
                    if controls is not None
                    else False
                ),
                "evolutionFrozen": (
                    bool(getattr(controls, "evolution_frozen", True))
                    if controls is not None
                    else True
                ),
                "allocationsFrozen": (
                    bool(getattr(controls, "allocations_frozen", False))
                    if controls is not None
                    else False
                ),
                "sandboxOnly": sandbox_only,
                "paused": paused,
                "metricsEnabled": (
                    bool(getattr(controls, "metrics_enabled", True))
                    if controls is not None
                    else True
                ),
                "latencyProfilingEnabled": (
                    bool(getattr(controls, "latency_profiling_enabled", True))
                    if controls is not None
                    else True
                ),
                "rewardTraceEnabled": (
                    bool(getattr(controls, "reward_trace_enabled", True))
                    if controls is not None
                    else True
                ),
                "chaosBreakersEnabled": (
                    bool(getattr(controls, "chaos_breakers_enabled", True))
                    if controls is not None
                    else True
                ),
                "rpcBatchEnabled": (
                    bool(getattr(controls, "rpc_batch_enabled", False))
                    if controls is not None
                    else False
                ),
                "rftEpisodeExportEnabled": (
                    bool(getattr(controls, "rft_episode_export_enabled", False))
                    if controls is not None
                    else False
                ),
                "kellyEnabled": (
                    bool(getattr(controls, "kelly_enabled", False))
                    if controls is not None
                    else False
                ),
                "autoReinvestEnabled": (
                    bool(getattr(controls, "auto_reinvest_enabled", False))
                    if controls is not None
                    else False
                ),
                "forceSendMode": (
                    str(getattr(controls, "force_send_mode", "") or "")
                    if controls is not None
                    else ""
                ),
                "forceGasMode": (
                    str(getattr(controls, "force_gas_mode", "") or "")
                    if controls is not None
                    else ""
                ),
                "brainMode": (
                    str(getattr(controls, "brain_mode", "") or "") if controls is not None else ""
                ),
                "aggressionMode": (
                    str(getattr(controls, "aggression_mode", "balanced") or "balanced")
                    if controls is not None
                    else "balanced"
                ),
                "fullSystemEnabled": (
                    bool(getattr(controls, "full_system_enabled", False))
                    if controls is not None
                    else False
                ),
                "storage": storage_state,
            },
            "governanceHistory": gov_hist,
            "sandbox": {
                "sandboxNavUsd": 0.0,
                "probationTradesLeft": 0,
                "proposals": meta_candidates,
            },
            "analytics": {
                "equity": equity,
                "realizedAfterGas": realized_after_gas,
                "drawdown": drawdown_series,
                "laneSuccess": list(_safe_dict(capture_analytics).get("laneSuccess") or []),
                "venueQuality": list(_safe_dict(capture_analytics).get("venueQuality") or []),
                "utilizationPct": _safe_float(metrics.get("efficiency_pct")),
                "returnPerRisk": round(
                    _safe_float(metrics.get("efficiency_pct"))
                    / max(
                        1.0,
                        _safe_float(
                            _safe_dict(market_regime.get("features")).get("volatility"), 0.5
                        )
                        * 100.0,
                    ),
                    4,
                ),
                "execSuccessPct": _safe_float(metrics.get("success_rate_pct")),
                "slippagePct": (
                    round(
                        sum(
                            _safe_float(x.get("stalePct"))
                            for x in list(_safe_dict(capture_analytics).get("laneSuccess") or [])
                        )
                        / max(1, len(list(_safe_dict(capture_analytics).get("laneSuccess") or []))),
                        4,
                    )
                    if list(_safe_dict(capture_analytics).get("laneSuccess") or [])
                    else 0.0
                ),
                "complexityCost": round(
                    _safe_float(_safe_dict(market_regime.get("features")).get("gas")) * 100.0, 4
                ),
            },
            "observability": obs,
            "chain": chain,
            "services": services,
            "capitalSummary": dict(capital_context.capital_summary or {}),
            "capitalContract": dict(capital_truth.capital_contract or {}),
            "capitalPolicy": dict(capital_truth.capital_policy or {}),
            "capitalTruthHealth": capital_truth_health,
            "capitalLedgerTruth": dict(capital_context.capital_ledger_truth or {}),
            "capital": dict(capital_context.capital or {}),
            "familyHardening": family_hardening,
            "execution": execution_quality,
        }
        payload["summaryContract"] = build_summary_read_contract(
            family="operator",
            payload=payload,
            capital_contract=capital_truth.capital_contract,
            capital_policy=capital_truth.capital_policy,
            source_contracts={
                "capitalContract": capital_truth.capital_contract,
                "capitalPolicy": capital_truth.capital_policy,
                "capitalTruth": capital_truth_health.get("stateContract"),
            },
            phase="operator_summary",
        )
        return json_safe(payload)

    async def explain(self, runtime: Any) -> Dict[str, Any]:
        base = await self._base_snapshot(runtime)
        if hasattr(runtime, "capital_explain"):
            try:
                return json_safe(runtime.capital_explain(base))
            except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
                return json_safe({"ok": False, "text": "explain_failed", "facts": {}, "causal": {}})
        cc = getattr(runtime, "_cc", None)
        if cc is None:
            return json_safe({"ok": True, "text": "Command Center not enabled.", "facts": {}})
        try:
            return json_safe(cc.explain(base))
        except _OPERATOR_SUMMARY_COMPONENT_FAILURES:
            return json_safe({"ok": False, "text": "explain_failed", "facts": {}, "causal": {}})

    def audit_tail(self, runtime: Any, *, limit: int = 200) -> Dict[str, Any]:
        items = self._audit_items(runtime, limit=limit)
        return json_safe({"ok": True, "items": items})
