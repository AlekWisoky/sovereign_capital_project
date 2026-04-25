from __future__ import annotations

import os
import time
from types import SimpleNamespace
from typing import Any, Dict

from ..deploy_mode import is_public_mode, public_broadcast_override_enabled
from ..persistence.repositories.auto_trade_recovery_repository import AutoTradeRecoveryRepository
from ..models import RuntimeState
from ..jsonsafe import to_json_safe
from .profitability_truth import inspect_profit_after_costs_truth
from .auxiliary_state_service import AuxiliaryStateService
from .summary_read_contract import build_summary_read_contract
from .route_runtime_truth import execution_route_truth
from .capital_truth_read_context import build_capital_truth_read_context


def _safe_mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _runtime_snapshot(
    runtime: Any, attr_name: str, default: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    store = getattr(runtime, attr_name, None)
    if store is None or not hasattr(store, "snapshot"):
        return dict(default or {})
    try:
        value = store.snapshot()
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return dict(default or {})
    return dict(value or {}) if isinstance(value, dict) else dict(default or {})


def _unique_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        s = str(value or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def execution_gate_info(runtime: Any) -> Dict[str, Any]:
    drawdown = _runtime_snapshot(runtime, "_drawdown_state", default={})
    if not drawdown and hasattr(runtime, "drawdown_state"):
        try:
            candidate = runtime.drawdown_state()
            drawdown = dict(candidate or {}) if isinstance(candidate, dict) else {}
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            drawdown = {}
    if not drawdown:
        drawdown = {"hardStop": {"active": False, "reason_codes": []}}
    kill_switch = _runtime_snapshot(runtime, "_kill_switch", default={})
    if not kill_switch and hasattr(runtime, "kill_switch_state"):
        try:
            candidate = runtime.kill_switch_state()
            kill_switch = dict(candidate or {}) if isinstance(candidate, dict) else {}
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            kill_switch = {}
    if not kill_switch:
        kill_switch = {"metrics": {}, "suppressions": {}, "history": []}
    hard_stop_state = _safe_mapping(drawdown.get("hardStop"))
    suppressions = _safe_mapping(kill_switch.get("suppressions"))
    reason_codes: list[str] = []
    if bool(hard_stop_state.get("active", False)):
        raw = [str(x) for x in list(hard_stop_state.get("reason_codes") or []) if str(x)]
        reason_codes.extend(raw or ["drawdown_hard_stop"])
    if suppressions:
        reason_codes.append("kill_switch_active")
    deduped: list[str] = []
    for code in reason_codes:
        if code not in deduped:
            deduped.append(code)
    blocked = bool(deduped)
    return {
        "blocked": blocked,
        "reason_code": str(deduped[0] if deduped else "ok"),
        "reason_codes": deduped,
        "drawdown_hard_stop_active": bool(hard_stop_state.get("active", False)),
        "kill_switch_active": bool(suppressions),
    }


def _fund_summary_payload(runtime: Any) -> Dict[str, Any]:
    if hasattr(runtime, "fund_summary_state"):
        try:
            payload = runtime.fund_summary_state()
            return dict(payload or {}) if isinstance(payload, dict) else {}
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            return {}
    svc = getattr(runtime, "_fund_service", None)
    if svc is None or not hasattr(svc, "summary"):
        return {}
    try:
        payload = svc.summary(runtime)
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def summary_hold_info(runtime: Any, execution_gate: Dict[str, Any] | None = None) -> Dict[str, Any]:
    gate = dict(execution_gate or execution_gate_info(runtime) or {})
    fund_summary = _fund_summary_payload(runtime)
    health = dict((fund_summary.get("health") or {})) if isinstance(fund_summary, dict) else {}
    global_execution_reason_codes = _unique_strings(
        list(gate.get("reason_codes") or []) + list(health.get("globalExecutionReasonCodes") or [])
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
    hold_reason_codes = _unique_strings(
        global_execution_reason_codes
        + family_hardening_reason_codes
        + receipt_outcome_truth_reason_codes
        + capital_truth_reason_codes
        + internal_prime_reason_codes
    )
    hold_reason_code = str(hold_reason_codes[0] if hold_reason_codes else "ok")
    suggested_next_action = (
        str(health.get("suggestedNextAction") or "") if hold_reason_codes else ""
    )
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
        or (
            recovery_reason_codes[0]
            if recovery_reason_codes
            else (hold_reason_code if hold_reason_code != "ok" else "ok")
        )
    )
    if recovery_reason_code == "ok" and recovery_reason_codes:
        recovery_reason_code = recovery_reason_codes[0]
    elif recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    recovery_status = str(health.get("recoveryStatus") or inferred_recovery_status)
    if recovery_status == "ready" and family_hardening_reason_codes:
        recovery_status = "family_hardening_restore_required"
    recovery_next_action = (
        str(health.get("recoveryNextAction") or suggested_next_action)
        if recovery_reason_codes
        else ""
    )
    recovery_ready = bool(
        health.get("recoveryReady", recovery_status == "ready" and not recovery_reason_codes)
    )
    if recovery_ready and family_hardening_reason_codes:
        recovery_ready = False
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
        "blocked": bool(hold_reason_codes),
        "reason_code": hold_reason_code,
        "reason_codes": hold_reason_codes,
        "global_execution_reason_codes": global_execution_reason_codes,
        "family_hardening_reason_codes": family_hardening_reason_codes,
        "capital_truth_reason_codes": capital_truth_reason_codes,
        "receipt_outcome_truth_reason_codes": receipt_outcome_truth_reason_codes,
        "internal_prime_reason_codes": internal_prime_reason_codes,
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


def apply_execution_gate_to_top_opportunity(
    top_info: Dict[str, Any] | None,
    execution_gate: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if top_info is None:
        return None
    gate = dict(execution_gate or {}) if isinstance(execution_gate, dict) else {}
    blocked = bool(gate.get("blocked", False))
    out = dict(top_info)
    out["execution_allowed"] = not blocked and bool(top_info.get("can_execute_after_costs", False))
    out["execution_gate_reason_code"] = str(gate.get("reason_code") or "ok")
    out["execution_gate_reason_codes"] = [
        str(x) for x in list(gate.get("reason_codes") or []) if str(x)
    ]
    if blocked:
        out["can_execute_after_costs"] = False
    return out


def execution_advisory_info(hold: Dict[str, Any] | None) -> Dict[str, Any]:
    hold_info = dict(hold or {}) if isinstance(hold, dict) else {}
    reliability_class = str(hold_info.get("recovery_reliability_class") or "stable")
    reason_codes = [
        str(x) for x in list(hold_info.get("recovery_reliability_reason_codes") or []) if str(x)
    ]
    reason_code = str(
        hold_info.get("recovery_reliability_reason_code")
        or (reason_codes[0] if reason_codes else "ok")
    )
    if reason_code != "ok" and reason_code not in reason_codes:
        reason_codes = [reason_code, *reason_codes]
    next_action = str(hold_info.get("recovery_reliability_next_action") or "")
    active = reliability_class not in {"", "stable"}
    severity = (
        "warning"
        if reliability_class in {"blocked", "unavailable", "unknown", "degraded", "fragile"}
        else ("caution" if reliability_class == "cautious" else "normal")
    )
    return {
        "active": active,
        "severity": severity,
        "class": reliability_class,
        "reason_code": reason_code,
        "reason_codes": reason_codes,
        "next_action": next_action,
    }


def apply_hold_to_top_opportunity(
    top_info: Dict[str, Any] | None,
    hold: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if top_info is None:
        return None
    hold_info = dict(hold or {}) if isinstance(hold, dict) else {}
    blocked = bool(hold_info.get("blocked", False))
    advisory = execution_advisory_info(hold_info)
    out = dict(top_info)
    out["execution_allowed"] = not blocked and bool(top_info.get("can_execute_after_costs", False))
    out["hold_reason_code"] = str(hold_info.get("reason_code") or "ok")
    out["hold_reason_codes"] = [str(x) for x in list(hold_info.get("reason_codes") or []) if str(x)]
    out["execution_advisory_active"] = bool(advisory.get("active", False))
    out["execution_advisory_severity"] = str(advisory.get("severity") or "normal")
    out["execution_advisory_class"] = str(advisory.get("class") or "stable")
    out["execution_advisory_reason_code"] = str(advisory.get("reason_code") or "ok")
    out["execution_advisory_reason_codes"] = [
        str(x) for x in list(advisory.get("reason_codes") or []) if str(x)
    ]
    out["execution_advisory_next_action"] = str(advisory.get("next_action") or "")
    if blocked:
        out["can_execute_after_costs"] = False
    return out


def _opp_field(opp: Any, field: str, default: Any = None) -> Any:
    if isinstance(opp, dict):
        return opp.get(field, default)
    return getattr(opp, field, default)


def _profit_after_costs_info(opp: Any) -> tuple[int, bool, str]:
    truth = inspect_profit_after_costs_truth(_safe_mapping(_opp_field(opp, "meta", {})))
    return int(max(0, truth.value_wei)), bool(truth.verified), str(truth.reason_code)


def _route_execution_info(opp: Any) -> Dict[str, Any]:
    meta = _safe_mapping(_opp_field(opp, "meta", {}))
    route_truth = execution_route_truth(meta)
    return {
        "ready": bool(route_truth.get("ready", False)),
        "reason": str(route_truth.get("reason") or "execution_route_not_ready"),
        "reason_codes": list(route_truth.get("reason_codes") or []),
        "plan_executable": bool(route_truth.get("plan_executable", True)),
        "invalid_causes": list(route_truth.get("invalid_causes") or []),
        "runtime_degraded": bool(route_truth.get("runtime_degraded", False)),
        "runtime_reason_codes": list(route_truth.get("runtime_reason_codes") or []),
    }


def _execution_eligibility_info(opp: Any) -> tuple[bool, bool, str]:
    can_execute = bool(_opp_field(opp, "can_execute", False))
    meta = _safe_mapping(_opp_field(opp, "meta", {}))
    safety = _safe_mapping(meta.get("safety"))
    route_info = _route_execution_info(opp)
    if not can_execute:
        exec_ready = bool(safety.get("exec_ready", False)) if "exec_ready" in safety else False
        return False, exec_ready, str(safety.get("reason") or "simulation_not_ok")
    if not bool(route_info.get("ready", True)):
        return True, False, str(route_info.get("reason") or "execution_route_not_ready")
    if "exec_ready" not in safety:
        return True, False, "exec_ready_unavailable"
    exec_ready = bool(safety.get("exec_ready", False))
    if not exec_ready:
        return True, False, str(safety.get("reason") or "execution_not_ready")
    return True, True, "ok"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or isinstance(value, bool):
            return int(default)
        return int(str(value))
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _opportunity_rank(opp: Any) -> tuple[int, int, str]:
    profit_after, verified, _reason = _profit_after_costs_info(opp)
    can_execute, exec_ready, _eligibility_reason = _execution_eligibility_info(opp)
    meta = _safe_mapping(_opp_field(opp, "meta", {}))
    fallback_profit = _coerce_int(
        meta.get("profit_after_gas_estimate_wei"),
        _coerce_int(_opp_field(opp, "expected_profit_raw", 0), 0),
    )
    route_id = str(_opp_field(opp, "route_id") or _opp_field(opp, "id") or "")
    if can_execute and exec_ready and verified and profit_after > 0:
        return (5, int(profit_after), route_id)
    if verified and profit_after > 0:
        return (4, int(profit_after), route_id)
    if can_execute and exec_ready and verified:
        return (3, int(profit_after), route_id)
    if verified:
        return (2, int(profit_after), route_id)
    if can_execute and exec_ready:
        return (1, int(max(0, fallback_profit)), route_id)
    return (0, int(max(0, fallback_profit)), route_id)


_AUTO_TRADE_RECOVERY_STATUS = {
    "fund_hold": "fund_hold_active",
    "family_hold": "family_readiness_restore_required",
    "route_hold": "execution_route_restore_required",
    "flashloan_hold": "flashloan_eligibility_restore_required",
    "treasury_hold": "treasury_alignment_required",
    "admission_hold": "auto_trade_admission_restore_required",
}

_AUTO_TRADE_RECOVERY_COMPONENT = {
    "fund_hold": "fund_health",
    "family_hold": "family_hardening",
    "route_hold": "execution_route",
    "flashloan_hold": "flashloan_eligibility",
    "treasury_hold": "treasury_governance",
    "admission_hold": "auto_trade_admission",
}


def auto_trade_recovery_info(admission: Any) -> Dict[str, Any]:
    if admission is None:
        return {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
        }
    gate = dict(getattr(admission, "gate", {}) or {})
    stage = str(getattr(admission, "stage", "ok") or "ok")
    reason = str(getattr(admission, "reason", "ok") or "ok")
    allowed = bool(getattr(admission, "allowed", True))
    gate_reason_codes = [str(x) for x in list(gate.get("reason_codes") or []) if str(x)]
    if reason != "ok" and reason not in gate_reason_codes:
        gate_reason_codes = [reason, *gate_reason_codes]
    suggested_next_action = str(
        gate.get("recovery_next_action")
        or gate.get("suggested_next_action")
        or gate.get("recoveryNextAction")
        or gate.get("suggestedNextAction")
        or ""
    )
    if allowed and stage == "ok":
        return {
            "blocked": False,
            "ready": True,
            "stage": "ok",
            "status": "ready",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
            "component": "",
            "history_status": "steady",
            "reliability_class": "stable",
            "reliability_reason_code": "ok",
            "reliability_reason_codes": [],
            "reliability_next_action": "",
            "component_reliability_class": "stable",
            "component_reliability_reason_code": "ok",
            "component_reliability_reason_codes": [],
            "component_reliability_next_action": "",
            "component_recovered_fragile": False,
        }

    recovery_reason_code = str(
        gate.get("recovery_reason_code") or gate.get("recoveryReasonCode") or reason
    )
    recovery_reason_codes = [
        str(x)
        for x in list(gate.get("recovery_reason_codes") or gate.get("recoveryReasonCodes") or [])
        if str(x)
    ]
    if recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    if not recovery_reason_codes:
        recovery_reason_codes = list(gate_reason_codes)

    status = str(
        gate.get("recovery_status")
        or gate.get("recoveryStatus")
        or _AUTO_TRADE_RECOVERY_STATUS.get(stage, "auto_trade_recovery_required")
    )
    component = str(
        gate.get("recovery_history_component")
        or gate.get("recoveryHistoryComponent")
        or _AUTO_TRADE_RECOVERY_COMPONENT.get(stage, "auto_trade_admission")
    )
    history_status = str(
        gate.get("recovery_history_status") or gate.get("recoveryHistoryStatus") or "blocked"
    )
    reliability_class = str(
        gate.get("recovery_reliability_class") or gate.get("recoveryReliabilityClass") or "blocked"
    )
    reliability_reason_code = str(
        gate.get("recovery_reliability_reason_code")
        or gate.get("recoveryReliabilityReasonCode")
        or recovery_reason_code
    )
    reliability_reason_codes = [
        str(x)
        for x in list(
            gate.get("recovery_reliability_reason_codes")
            or gate.get("recoveryReliabilityReasonCodes")
            or []
        )
        if str(x)
    ]
    if reliability_reason_code != "ok" and reliability_reason_code not in reliability_reason_codes:
        reliability_reason_codes = [reliability_reason_code, *reliability_reason_codes]
    if not reliability_reason_codes:
        reliability_reason_codes = list(recovery_reason_codes)

    out = {
        "blocked": True,
        "ready": False,
        "stage": stage,
        "status": status,
        "reason_code": recovery_reason_code,
        "reason_codes": recovery_reason_codes,
        "next_action": suggested_next_action,
        "component": component,
        "history_status": history_status,
        "reliability_class": reliability_class,
        "reliability_reason_code": reliability_reason_code,
        "reliability_reason_codes": reliability_reason_codes,
        "reliability_next_action": str(
            gate.get("recovery_reliability_next_action")
            or gate.get("recoveryReliabilityNextAction")
            or suggested_next_action
        ),
        "component_reliability_class": reliability_class,
        "component_reliability_reason_code": reliability_reason_code,
        "component_reliability_reason_codes": list(reliability_reason_codes),
        "component_reliability_next_action": str(
            gate.get("recovery_reliability_next_action")
            or gate.get("recoveryReliabilityNextAction")
            or suggested_next_action
        ),
        "component_recovered_fragile": False,
    }
    family_hardening_reason_codes = [
        str(x)
        for x in list(
            gate.get("family_hardening_reason_codes")
            or gate.get("familyHardeningReasonCodes")
            or []
        )
        if str(x)
    ]
    if family_hardening_reason_codes:
        out["family_hardening_reason_codes"] = family_hardening_reason_codes
    receipt_outcome_truth_reason_codes = [
        str(x)
        for x in list(
            gate.get("receipt_outcome_truth_reason_codes")
            or gate.get("receiptOutcomeTruthReasonCodes")
            or []
        )
        if str(x)
    ]
    if receipt_outcome_truth_reason_codes:
        out["receipt_outcome_truth_reason_codes"] = receipt_outcome_truth_reason_codes
    return out


def _auto_trade_recovery_repo(runtime: Any) -> AutoTradeRecoveryRepository | None:
    repo = getattr(runtime, "_auto_trade_recovery_repo", None)
    if repo is not None:
        return repo
    db = getattr(runtime, "_db", None)
    if db is None:
        return None
    try:
        chain_cfg = getattr(getattr(runtime, "cfg", None), "chain", None)
        chain = str(getattr(chain_cfg, "name", None) or "default")
        repo = AutoTradeRecoveryRepository(db, chain=chain)
        runtime._auto_trade_recovery_repo = repo
        return repo
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return None


def _auto_trade_recovery_severity(
    *, degraded: bool, degraded_count: int, degraded_duration_ms: int, history_status: str
) -> str:
    if degraded:
        if degraded_count >= 5 or degraded_duration_ms >= 86_400_000:
            return "chronic"
        if degraded_count >= 3 or degraded_duration_ms >= 3_600_000:
            return "persistent"
        return "acute"
    if history_status == "recovered":
        return "recovering"
    return "stable"


def _materialize_auto_trade_recovery_history(
    recovery: Dict[str, Any],
    observed: Dict[str, Any],
    *,
    now_ms: int,
    repo: AutoTradeRecoveryRepository | None,
) -> Dict[str, Any]:
    if not observed:
        return recovery
    is_degraded = bool(observed.get("is_degraded", False))
    degraded_since_ts_ms = int(observed.get("degraded_since_ts_ms") or 0)
    recovered_at_ts_ms = int(observed.get("last_recovered_ts_ms") or 0)
    degraded_count = int(observed.get("degraded_count") or 0)
    last_healthy_ts_ms = int(observed.get("last_healthy_ts_ms") or 0)
    history_status = (
        "blocked" if is_degraded else ("recovered" if recovered_at_ts_ms > 0 else "steady")
    )
    degraded_duration_ms = (
        max(0, now_ms - degraded_since_ts_ms) if is_degraded and degraded_since_ts_ms > 0 else 0
    )
    recovered_recently = bool(
        not is_degraded and recovered_at_ts_ms > 0 and (now_ms - recovered_at_ts_ms) <= 900_000
    )
    severity = _auto_trade_recovery_severity(
        degraded=is_degraded,
        degraded_count=degraded_count,
        degraded_duration_ms=degraded_duration_ms,
        history_status=history_status,
    )
    recovery["history_status"] = history_status
    recovery["degraded_since_ts_ms"] = degraded_since_ts_ms
    recovery["recovered_at_ts_ms"] = recovered_at_ts_ms
    recovery["degraded_duration_ms"] = degraded_duration_ms
    recovery["degraded_count"] = degraded_count
    recovery["last_healthy_ts_ms"] = last_healthy_ts_ms
    recovery["recovered_recently"] = recovered_recently
    recovery["degradation_severity_class"] = severity
    history_component = str(
        observed.get("history_component")
        or observed.get("last_blocker_component")
        or recovery.get("history_component")
        or recovery.get("component")
        or ""
    )
    history_stage = str(
        observed.get("history_stage")
        or observed.get("last_stage")
        or recovery.get("history_stage")
        or recovery.get("stage")
        or "ok"
    )
    history_reason_code = str(
        observed.get("history_reason_code")
        or observed.get("last_reason_code")
        or recovery.get("history_reason_code")
        or recovery.get("reason_code")
        or ("blocked" if is_degraded else "ok")
    )
    history_reason_codes = [
        str(x)
        for x in list(
            observed.get("history_reason_codes")
            or observed.get("last_reason_codes")
            or recovery.get("history_reason_codes")
            or recovery.get("reason_codes")
            or []
        )
        if str(x)
    ]
    history_next_action = str(
        observed.get("history_next_action")
        or observed.get("last_next_action")
        or recovery.get("history_next_action")
        or recovery.get("next_action")
        or ""
    )
    family_hardening_reason_codes = [
        str(x)
        for x in list(
            observed.get("family_hardening_reason_codes")
            or recovery.get("family_hardening_reason_codes")
            or []
        )
        if str(x)
    ]
    receipt_outcome_truth_reason_codes = [
        str(x)
        for x in list(
            observed.get("receipt_outcome_truth_reason_codes")
            or recovery.get("receipt_outcome_truth_reason_codes")
            or []
        )
        if str(x)
    ]
    persisted_reliability_class = str(
        observed.get("component_reliability_class")
        or observed.get("reliability_class")
        or recovery.get("component_reliability_class")
        or recovery.get("reliability_class")
        or ""
    )
    persisted_reliability_reason_code = str(
        observed.get("component_reliability_reason_code")
        or observed.get("reliability_reason_code")
        or recovery.get("component_reliability_reason_code")
        or recovery.get("reliability_reason_code")
        or ""
    )
    persisted_reliability_reason_codes = [
        str(x)
        for x in list(
            observed.get("component_reliability_reason_codes")
            or observed.get("reliability_reason_codes")
            or recovery.get("component_reliability_reason_codes")
            or recovery.get("reliability_reason_codes")
            or []
        )
        if str(x)
    ]
    persisted_reliability_next_action = str(
        observed.get("component_reliability_next_action")
        or observed.get("reliability_next_action")
        or recovery.get("component_reliability_next_action")
        or recovery.get("reliability_next_action")
        or ""
    )
    persisted_component_recovered_fragile = bool(
        observed.get(
            "component_recovered_fragile",
            recovery.get(
                "component_recovered_fragile",
                str(observed.get("history_status") or history_status) == "recovered"
                and persisted_reliability_class == "fragile",
            ),
        )
    )
    recovery["history_component"] = history_component
    recovery["history_stage"] = history_stage
    recovery["history_reason_code"] = history_reason_code
    recovery["history_reason_codes"] = list(history_reason_codes)
    recovery["history_next_action"] = history_next_action
    if family_hardening_reason_codes:
        recovery["family_hardening_reason_codes"] = family_hardening_reason_codes
    if receipt_outcome_truth_reason_codes:
        recovery["receipt_outcome_truth_reason_codes"] = receipt_outcome_truth_reason_codes
    if is_degraded:
        current_status = str(recovery.get("status") or "")
        current_history_status = str(recovery.get("history_status") or "")
        current_reliability_class = str(recovery.get("reliability_class") or "")
        current_reliability_reason_code = str(recovery.get("reliability_reason_code") or "")
        current_reliability_reason_codes = [
            str(x) for x in list(recovery.get("reliability_reason_codes") or []) if str(x)
        ]
        family_hardening_unavailable = bool(
            history_stage == "family_hold"
            and (
                history_reason_code
                in {"family_hardening_service_unavailable", "family_hardening_unavailable"}
                or history_next_action == "restore_family_hardening"
                or "family_hardening_service_unavailable" in history_reason_codes
            )
        )
        receipt_outcome_truth_degraded = bool(
            history_stage == "fund_hold"
            and history_component == "receipt_outcome_truth"
            and (
                history_reason_code == "settled_profit_truth_unavailable"
                or history_next_action == "restore_receipt_outcome_truth"
                or "settled_profit_truth_unavailable" in history_reason_codes
            )
        )
        recovery["blocked"] = True
        recovery["ready"] = False
        recovery["stage"] = history_stage
        recovery["status"] = (
            "family_hardening_restore_required"
            if family_hardening_unavailable
            else (
                "capital_truth_restore_required"
                if receipt_outcome_truth_degraded
                else (
                    current_status
                    if current_status not in {"", "ready"}
                    else _AUTO_TRADE_RECOVERY_STATUS.get(
                        history_stage, "auto_trade_recovery_required"
                    )
                )
            )
        )
        recovery["reason_code"] = history_reason_code
        recovery["reason_codes"] = history_reason_codes
        recovery["next_action"] = history_next_action
        recovery["component"] = history_component
        recovery["history_status"] = (
            "degraded"
            if (family_hardening_unavailable or receipt_outcome_truth_degraded)
            else (current_history_status or history_status)
        )
        recovery["reliability_class"] = (
            "unavailable"
            if family_hardening_unavailable
            else (
                "degraded"
                if receipt_outcome_truth_degraded
                else (
                    current_reliability_class
                    if current_reliability_class not in {"", "stable"}
                    else "blocked"
                )
            )
        )
        recovery["reliability_reason_code"] = (
            "family_hardening_reliability_unavailable"
            if family_hardening_unavailable
            else (
                "receipt_outcome_truth_reliability_degraded"
                if receipt_outcome_truth_degraded
                else (
                    current_reliability_reason_code
                    if current_reliability_reason_code not in {"", "ok"}
                    else history_reason_code
                )
            )
        )
        recovery["reliability_reason_codes"] = (
            ["family_hardening_reliability_unavailable"]
            if family_hardening_unavailable
            else (
                [
                    "receipt_outcome_truth_reliability_degraded",
                    *[
                        code
                        for code in history_reason_codes
                        if code != "receipt_outcome_truth_reliability_degraded"
                    ],
                ]
                if receipt_outcome_truth_degraded
                else (
                    current_reliability_reason_codes
                    if current_reliability_reason_codes
                    and current_reliability_reason_codes != ["ok"]
                    else list(history_reason_codes)
                )
            )
        )
        recovery["reliability_next_action"] = str(
            recovery.get("reliability_next_action") or history_next_action
        )
        if family_hardening_unavailable:
            recovery["family_hardening_reason_codes"] = ["family_hardening_service_unavailable"]
        if receipt_outcome_truth_degraded:
            recovery["receipt_outcome_truth_reason_codes"] = list(
                receipt_outcome_truth_reason_codes or history_reason_codes
            )
    elif recovered_recently:
        recovery["reliability_class"] = "fragile"
        recovery["reliability_reason_code"] = "auto_trade_recovery_fragile"
        recovery["reliability_reason_codes"] = ["auto_trade_recovery_fragile"]
        recovery["reliability_next_action"] = "monitor_auto_trade_reentry"
    else:
        recovery["reliability_class"] = "stable"
        recovery["reliability_reason_code"] = "ok"
        recovery["reliability_reason_codes"] = []
        recovery["reliability_next_action"] = ""
    if (
        recovered_recently
        and history_component == "receipt_outcome_truth"
        and receipt_outcome_truth_reason_codes
    ):
        recovery["receipt_outcome_truth_reason_codes"] = list(receipt_outcome_truth_reason_codes)
    if (
        recovered_recently
        and history_component == "family_hardening"
        and family_hardening_reason_codes
    ):
        recovery["family_hardening_reason_codes"] = list(family_hardening_reason_codes)
    if persisted_reliability_class and recovery.get("reliability_class") in {"stable", "fragile"}:
        recovery["component_reliability_class"] = persisted_reliability_class
    if persisted_reliability_reason_code:
        recovery["component_reliability_reason_code"] = persisted_reliability_reason_code
    if persisted_reliability_reason_codes:
        recovery["component_reliability_reason_codes"] = persisted_reliability_reason_codes
    if persisted_reliability_next_action:
        recovery["component_reliability_next_action"] = persisted_reliability_next_action
    recovery["component_recovered_fragile"] = bool(
        persisted_component_recovered_fragile
        or (
            str(recovery.get("history_status") or "") == "recovered"
            and str(recovery.get("component_reliability_class") or "") == "fragile"
        )
    )
    try:
        recent_events = (
            repo.recent_events(component="auto_trade_admission", limit=10)
            if repo is not None
            else []
        )
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        recent_events = []
    recovery["recent_events"] = [
        dict(item) for item in list(recent_events or []) if isinstance(item, dict)
    ]
    return recovery


def current_auto_trade_recovery_info(runtime: Any) -> Dict[str, Any]:
    recovery = dict(auto_trade_recovery_info(None))
    repo = _auto_trade_recovery_repo(runtime)
    if repo is None:
        return recovery
    try:
        observed = repo.load("auto_trade_admission")
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return recovery
    return _materialize_auto_trade_recovery_history(
        recovery,
        observed,
        now_ms=int(time.time() * 1000),
        repo=repo,
    )


def observed_auto_trade_recovery_info(runtime: Any, admission: Any) -> Dict[str, Any]:
    recovery = dict(auto_trade_recovery_info(admission))
    repo = _auto_trade_recovery_repo(runtime)
    if repo is None:
        return recovery
    now_ms = int(time.time() * 1000)
    try:
        observed = repo.observe(
            component="auto_trade_admission",
            degraded=bool(recovery.get("blocked", False)),
            ts_ms=now_ms,
            reason_code=str(recovery.get("reason_code") or "ok"),
            stage=str(recovery.get("stage") or "ok"),
            blocker_component=str(recovery.get("component") or ""),
            next_action=str(recovery.get("next_action") or ""),
            reason_codes=[str(x) for x in list(recovery.get("reason_codes") or []) if str(x)],
            payload_extras={
                "history_component": str(
                    recovery.get("history_component") or recovery.get("component") or ""
                ),
                "history_stage": str(
                    recovery.get("history_stage") or recovery.get("stage") or "ok"
                ),
                "history_reason_code": str(
                    recovery.get("history_reason_code") or recovery.get("reason_code") or "ok"
                ),
                "history_reason_codes": [
                    str(x)
                    for x in list(
                        recovery.get("history_reason_codes") or recovery.get("reason_codes") or []
                    )
                    if str(x)
                ],
                "history_next_action": str(
                    recovery.get("history_next_action") or recovery.get("next_action") or ""
                ),
                "reliability_class": str(recovery.get("reliability_class") or "stable"),
                "reliability_reason_code": str(recovery.get("reliability_reason_code") or "ok"),
                "reliability_reason_codes": [
                    str(x) for x in list(recovery.get("reliability_reason_codes") or []) if str(x)
                ],
                "reliability_next_action": str(
                    recovery.get("reliability_next_action") or recovery.get("next_action") or ""
                ),
                "family_hardening_reason_codes": [
                    str(x)
                    for x in list(recovery.get("family_hardening_reason_codes") or [])
                    if str(x)
                ],
                "receipt_outcome_truth_reason_codes": [
                    str(x)
                    for x in list(recovery.get("receipt_outcome_truth_reason_codes") or [])
                    if str(x)
                ],
                "component_reliability_class": str(
                    recovery.get("component_reliability_class")
                    or recovery.get("reliability_class")
                    or "stable"
                ),
                "component_reliability_reason_code": str(
                    recovery.get("component_reliability_reason_code")
                    or recovery.get("reliability_reason_code")
                    or "ok"
                ),
                "component_reliability_reason_codes": [
                    str(x)
                    for x in list(
                        recovery.get("component_reliability_reason_codes")
                        or recovery.get("reliability_reason_codes")
                        or []
                    )
                    if str(x)
                ],
                "component_reliability_next_action": str(
                    recovery.get("component_reliability_next_action")
                    or recovery.get("reliability_next_action")
                    or recovery.get("next_action")
                    or ""
                ),
                "component_recovered_fragile": bool(
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
            },
        )
    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return recovery
    return _materialize_auto_trade_recovery_history(
        recovery,
        observed,
        now_ms=now_ms,
        repo=repo,
    )


def _apply_auto_trade_recovery_projection(
    out: Dict[str, Any],
    recovery: Dict[str, Any],
) -> Dict[str, Any]:
    recovery_history_status = str(recovery.get("history_status") or "steady")
    recovery_stage = str(recovery.get("stage") or "")
    if recovery_history_status == "recovered" and (not recovery_stage or recovery_stage == "ok"):
        recovery_stage = str(recovery.get("history_stage") or recovery_stage or "ok")
    if not recovery_stage:
        recovery_stage = "ok"
    recovery_reason_codes = [str(x) for x in list(recovery.get("reason_codes") or []) if str(x)]
    recovery_reason_code = str(recovery.get("reason_code") or "")
    if recovery_history_status == "recovered" and (
        not recovery_reason_code or recovery_reason_code == "ok"
    ):
        history_reason_codes = [
            str(x) for x in list(recovery.get("history_reason_codes") or []) if str(x)
        ]
        recovery_reason_code = str(
            recovery.get("history_reason_code")
            or (history_reason_codes[0] if history_reason_codes else "")
            or (recovery_reason_codes[0] if recovery_reason_codes else "")
            or recovery_reason_code
            or "ok"
        )
        if history_reason_codes:
            recovery_reason_codes = history_reason_codes
    if not recovery_reason_code:
        recovery_reason_code = "ok"
    out["auto_trade_recovery_status"] = str(recovery.get("status") or "ready")
    out["auto_trade_recovery_reason_code"] = recovery_reason_code
    out["auto_trade_recovery_reason_codes"] = recovery_reason_codes
    out["auto_trade_recovery_next_action"] = str(
        recovery.get("next_action")
        or recovery.get("component_reliability_next_action")
        or recovery.get("reliability_next_action")
        or ""
    )
    out["auto_trade_recovery_ready"] = bool(recovery.get("ready", True))
    out["auto_trade_recovery_component"] = str(
        recovery.get("component") or recovery.get("history_component") or ""
    )
    out["auto_trade_recovery_history_status"] = recovery_history_status
    out["auto_trade_recovery_history_component"] = str(
        recovery.get("history_component") or recovery.get("component") or ""
    )
    out["auto_trade_recovery_history_stage"] = str(
        recovery.get("history_stage") or recovery.get("stage") or "ok"
    )
    out["auto_trade_recovery_degraded_since_ts_ms"] = int(recovery.get("degraded_since_ts_ms") or 0)
    out["auto_trade_recovery_recovered_at_ts_ms"] = int(recovery.get("recovered_at_ts_ms") or 0)
    out["auto_trade_recovery_degraded_duration_ms"] = int(recovery.get("degraded_duration_ms") or 0)
    out["auto_trade_recovery_degraded_count"] = int(recovery.get("degraded_count") or 0)
    out["auto_trade_recovery_last_healthy_ts_ms"] = int(recovery.get("last_healthy_ts_ms") or 0)
    out["auto_trade_recovery_recovered_recently"] = bool(recovery.get("recovered_recently", False))
    out["auto_trade_recovery_degradation_severity_class"] = str(
        recovery.get("degradation_severity_class") or "stable"
    )
    out["auto_trade_recovery_reliability_class"] = str(
        recovery.get("reliability_class") or "stable"
    )
    out["auto_trade_recovery_reliability_reason_code"] = str(
        recovery.get("reliability_reason_code") or "ok"
    )
    out["auto_trade_recovery_reliability_reason_codes"] = [
        str(x) for x in list(recovery.get("reliability_reason_codes") or []) if str(x)
    ]
    out["auto_trade_recovery_reliability_next_action"] = str(
        recovery.get("reliability_next_action") or ""
    )
    out["auto_trade_recovery_component_reliability_class"] = str(
        recovery.get("component_reliability_class") or recovery.get("reliability_class") or "stable"
    )
    out["auto_trade_recovery_component_reliability_reason_code"] = str(
        recovery.get("component_reliability_reason_code")
        or recovery.get("reliability_reason_code")
        or "ok"
    )
    out["auto_trade_recovery_component_reliability_reason_codes"] = [
        str(x)
        for x in list(
            recovery.get("component_reliability_reason_codes")
            or recovery.get("reliability_reason_codes")
            or []
        )
        if str(x)
    ]
    out["auto_trade_recovery_component_reliability_next_action"] = str(
        recovery.get("component_reliability_next_action")
        or recovery.get("reliability_next_action")
        or ""
    )
    out["auto_trade_recovery_component_recovered_fragile"] = bool(
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
    )
    family_hardening_reason_codes = [
        str(x) for x in list(recovery.get("family_hardening_reason_codes") or []) if str(x)
    ]
    if family_hardening_reason_codes:
        out["auto_trade_recovery_family_hardening_reason_codes"] = family_hardening_reason_codes
    receipt_outcome_truth_reason_codes = [
        str(x) for x in list(recovery.get("receipt_outcome_truth_reason_codes") or []) if str(x)
    ]
    if receipt_outcome_truth_reason_codes:
        out["auto_trade_recovery_receipt_outcome_truth_reason_codes"] = (
            receipt_outcome_truth_reason_codes
        )
    return out


def apply_auto_trade_recovery_projection(
    top_info: Dict[str, Any] | None,
    recovery: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if top_info is None:
        return None
    out = dict(top_info)
    return _apply_auto_trade_recovery_projection(
        out,
        dict(recovery or {}) if isinstance(recovery, dict) else {},
    )


def auto_trade_gate_info_from_recovery(recovery: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(recovery or {}) if isinstance(recovery, dict) else {}
    blocked = bool(payload.get("blocked", False))
    ready = bool(payload.get("ready", True))
    allowed = not blocked and ready
    if allowed:
        return {
            "allowed": True,
            "stage": "ok",
            "reason_code": "ok",
            "reason_codes": [],
            "next_action": "",
        }

    stage = str(payload.get("stage") or payload.get("history_stage") or "admission_hold")
    reason_codes = [str(x) for x in list(payload.get("reason_codes") or []) if str(x)]
    history_reason_codes = [
        str(x) for x in list(payload.get("history_reason_codes") or []) if str(x)
    ]
    reason_code = str(
        payload.get("reason_code")
        or (reason_codes[0] if reason_codes else "")
        or payload.get("history_reason_code")
        or (history_reason_codes[0] if history_reason_codes else "")
        or "auto_trade_recovery_required"
    )
    if not reason_codes and history_reason_codes:
        reason_codes = history_reason_codes
    if reason_code not in reason_codes:
        reason_codes = [reason_code, *reason_codes]
    next_action = str(
        payload.get("next_action")
        or payload.get("history_next_action")
        or payload.get("component_reliability_next_action")
        or payload.get("reliability_next_action")
        or ""
    )
    return {
        "allowed": False,
        "stage": stage,
        "reason_code": reason_code,
        "reason_codes": reason_codes,
        "next_action": next_action,
    }


def synthetic_auto_trade_admission_from_recovery(recovery: Dict[str, Any] | None) -> Any:
    gate = auto_trade_gate_info_from_recovery(recovery)
    return SimpleNamespace(
        allowed=bool(gate.get("allowed", True)),
        stage=str(gate.get("stage") or "ok"),
        reason=str(gate.get("reason_code") or "ok"),
        gate={
            "blocked": not bool(gate.get("allowed", True)),
            "reason_code": str(gate.get("reason_code") or "ok"),
            "reason_codes": [str(x) for x in list(gate.get("reason_codes") or []) if str(x)],
            "suggested_next_action": str(gate.get("next_action") or ""),
        },
    )


def apply_auto_trade_gate_to_top_opportunity(
    top_info: Dict[str, Any] | None,
    admission: Any,
) -> Dict[str, Any] | None:
    if top_info is None:
        return None
    out = dict(top_info)
    stage = str(getattr(admission, "stage", "ok") or "ok") if admission is not None else "ok"
    reason = str(getattr(admission, "reason", "ok") or "ok") if admission is not None else "ok"
    gate = dict(getattr(admission, "gate", {}) or {}) if admission is not None else {}
    allowed = bool(getattr(admission, "allowed", True)) if admission is not None else True
    reason_codes = [str(x) for x in list(gate.get("reason_codes") or []) if str(x)]
    if reason != "ok" and reason not in reason_codes:
        reason_codes = [reason, *reason_codes]
    out["auto_trade_allowed"] = allowed
    out["auto_trade_gate_stage"] = stage
    out["auto_trade_gate_reason_code"] = reason
    out["auto_trade_gate_reason_codes"] = reason_codes
    out["auto_trade_gate_next_action"] = str(gate.get("suggested_next_action") or "")
    recovery = dict(auto_trade_recovery_info(admission))
    _apply_auto_trade_recovery_projection(out, recovery)
    if not allowed:
        out["execution_allowed"] = False
        out["can_execute_after_costs"] = False
    return out


def _admission_gate_failed_recovery() -> Dict[str, Any]:
    return {
        "blocked": True,
        "ready": False,
        "stage": "admission_hold",
        "status": "auto_trade_admission_restore_required",
        "reason_code": "admission_gate_failed",
        "reason_codes": ["admission_gate_failed"],
        "next_action": "restore_auto_trade_admission_state",
        "component": "auto_trade_admission",
    }


def resolve_auto_trade_gate_and_recovery(
    runtime: Any,
    top_candidate: Any | None,
) -> tuple[Any | None, Dict[str, Any], Dict[str, Any]]:
    execution_service = getattr(runtime, "_execution_service", None)
    auto_trade_recovery = current_auto_trade_recovery_info(runtime)
    auto_trade_gate = auto_trade_gate_info_from_recovery(auto_trade_recovery)
    admission = None
    if (
        top_candidate is not None
        and execution_service is not None
        and hasattr(execution_service, "auto_trade_admission_gate")
    ):
        try:
            admission = execution_service.auto_trade_admission_gate(runtime, top_candidate, None)
        except (
            AttributeError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ):
            failed_recovery = _admission_gate_failed_recovery()
            admission = synthetic_auto_trade_admission_from_recovery(failed_recovery)
    if admission is not None:
        gate = dict(getattr(admission, "gate", {}) or {})
        reason = str(getattr(admission, "reason", "ok") or "ok")
        reason_codes = [str(x) for x in list(gate.get("reason_codes") or []) if str(x)]
        if reason != "ok" and reason not in reason_codes:
            reason_codes = [reason, *reason_codes]
        auto_trade_gate = {
            "allowed": bool(getattr(admission, "allowed", False)),
            "stage": str(getattr(admission, "stage", "ok") or "ok"),
            "reason_code": reason,
            "reason_codes": reason_codes,
            "next_action": str(gate.get("suggested_next_action") or ""),
        }
        auto_trade_recovery = observed_auto_trade_recovery_info(runtime, admission)
    return admission, auto_trade_gate, auto_trade_recovery


def auto_trade_summary_projection(
    runtime: Any,
    top_info: Dict[str, Any] | None,
    top_candidate: Any | None,
) -> tuple[Dict[str, Any] | None, Dict[str, Any], Dict[str, Any]]:
    admission, auto_trade_gate, auto_trade_recovery = resolve_auto_trade_gate_and_recovery(
        runtime,
        top_candidate,
    )
    if admission is not None:
        top_info = apply_auto_trade_gate_to_top_opportunity(top_info, admission)
        if top_info is not None:
            _apply_auto_trade_recovery_projection(top_info, auto_trade_recovery)
    elif top_info is not None and not bool(auto_trade_gate.get("allowed", True)):
        fallback_admission = synthetic_auto_trade_admission_from_recovery(auto_trade_recovery)
        top_info = apply_auto_trade_gate_to_top_opportunity(top_info, fallback_admission)
        if top_info is not None:
            _apply_auto_trade_recovery_projection(top_info, auto_trade_recovery)
    return top_info, auto_trade_gate, auto_trade_recovery


def select_top_opportunity(opps: list[Any]) -> Any | None:
    if not opps:
        return None
    ranked = sorted(opps, key=_opportunity_rank, reverse=True)
    return ranked[0] if ranked else None


def build_top_opportunity_view(opps: list[Any]) -> Dict[str, Any] | None:
    top = select_top_opportunity(opps)
    if top is None:
        return None
    best_executable = None
    best_after_cost = None
    best_executable_profit = -1
    best_after_cost_profit = -1
    for opp in opps:
        profit_after_candidate, verified_candidate, _reason = _profit_after_costs_info(opp)
        can_execute_candidate, exec_ready_candidate, _eligibility_reason = (
            _execution_eligibility_info(opp)
        )
        if verified_candidate and profit_after_candidate > 0:
            if profit_after_candidate > best_after_cost_profit:
                best_after_cost = opp
                best_after_cost_profit = profit_after_candidate
            if (
                can_execute_candidate
                and exec_ready_candidate
                and profit_after_candidate > best_executable_profit
            ):
                best_executable = opp
                best_executable_profit = profit_after_candidate
    profit_after, verified, reason = _profit_after_costs_info(top)
    meta = _safe_mapping(_opp_field(top, "meta", {}))
    route_info = _route_execution_info(top)
    can_execute, exec_ready, execution_ready_reason = _execution_eligibility_info(top)
    return {
        "id": _opp_field(top, "id"),
        "strategy": _opp_field(top, "strategy"),
        "expected_profit_raw": str(_opp_field(top, "expected_profit_raw", "0") or "0"),
        "expected_profit_after_costs_wei": str(int(max(0, profit_after))),
        "profit_after_costs_verified": bool(verified),
        "profit_after_costs_reason": str(reason or "profit_after_costs_unavailable"),
        "can_execute": can_execute,
        "execution_ready": bool(exec_ready),
        "execution_ready_reason": str(execution_ready_reason or "exec_ready_unavailable"),
        "can_execute_after_costs": bool(
            can_execute and exec_ready and verified and profit_after > 0
        ),
        "route_id": _opp_field(top, "route_id"),
        "selected_on_after_costs": bool(best_after_cost is not None or best_executable is not None),
        "selected_on_execution_eligibility": bool(best_executable is not None),
        "meta": {
            "venues": meta.get("venues"),
            "route_type": meta.get("route_type"),
            "brain": meta.get("brain"),
            "profit_after_gas_estimate_wei": str(meta.get("profit_after_gas_estimate_wei") or "0"),
            "route_plan_executable": bool(route_info.get("plan_executable", True)),
            "route_invalid_causes": list(route_info.get("invalid_causes") or []),
            "route_runtime_degraded": bool(route_info.get("runtime_degraded", False)),
            "route_runtime_reason_codes": list(route_info.get("runtime_reason_codes") or []),
        },
    }


class StateService:
    def __init__(self, *, auxiliary_state: AuxiliaryStateService | None = None) -> None:
        self.auxiliary_state = auxiliary_state or AuxiliaryStateService()

    """Build runtime state payloads used by API routes.

    This keeps snapshot/summary/admin views in one bounded place instead of
    spreading response assembly across the runtime shell.
    """

    def _executor_state(self, runtime: Any) -> Dict[str, Any]:
        return {
            "address": str(getattr(runtime.cfg.execution, "executor_address", "") or ""),
            "abi_version": (
                int(runtime._executor_abi_version)
                if getattr(runtime, "_executor_abi_version", None) is not None
                else None
            ),
            "impl_version": (
                int(runtime._executor_impl_version)
                if getattr(runtime, "_executor_impl_version", None) is not None
                else None
            ),
            "version_error": getattr(runtime, "_executor_version_error", None),
            "enforced": bool(getattr(runtime.cfg.execution, "enforce_executor_version", False)),
            "expected_abi_version": int(
                getattr(runtime.cfg.execution, "expected_executor_abi_version", 0) or 0
            ),
        }

    def _refresh_metrics(self, runtime: Any) -> None:
        runtime.metrics.realized_profit_raw = str(runtime._bankroll.state.realized_profit_wei)
        eff = runtime._eff.snapshot()
        runtime.metrics.efficiency_pct = float(eff.get("efficiency_pct", 0.0))
        runtime.metrics.success_rate_pct = float(eff.get("success_rate_pct", 0.0))

    async def snapshot(self, runtime: Any) -> Dict[str, Any]:
        opps = list(runtime._opps[:200])
        if (
            runtime.cfg.execution.redact_routes_when_private
            and runtime.cfg.execution.send_mode != "public"
        ):
            redacted = []
            for o in opps:
                od = o.model_copy(deep=True)
                od.route.legs = []
                od.min_outs = []
                redacted.append(od)
            opps = redacted
        self._refresh_metrics(runtime)
        st = RuntimeState(
            chain=runtime.cfg.chain.name,
            opportunities=opps,
            metrics=runtime.metrics,
            rpc=runtime.rpc_manager.snapshot(),
        )
        data = to_json_safe(st.model_dump())
        data["executor"] = self._executor_state(runtime)
        try:
            if os.environ.get("VICTOR_VALIDATE_CONTRACT", "").strip() == "1":
                from ..contract import validate_runtime_state

                validate_runtime_state(data)
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as e:  # pragma: no cover - best effort validation hook
            runtime._errors.append(f"contract_validation_failed:{e}")
        return data

    async def summary(self, runtime: Any) -> Dict[str, Any]:
        execution_gate = execution_gate_info(runtime)
        hold = summary_hold_info(runtime, execution_gate)
        execution_advisory = execution_advisory_info(hold)
        top_candidate = select_top_opportunity(list(runtime._opps))
        top_info = apply_hold_to_top_opportunity(
            apply_execution_gate_to_top_opportunity(
                build_top_opportunity_view(list(runtime._opps)),
                execution_gate,
            ),
            hold,
        )
        top_info, auto_trade_gate, auto_trade_recovery = auto_trade_summary_projection(
            runtime,
            top_info,
            top_candidate,
        )
        self._refresh_metrics(runtime)
        capital_context = build_capital_truth_read_context(
            runtime,
            auxiliary_state=self.auxiliary_state,
        )
        capital_truth = capital_context.capital_truth
        capital_truth_health = dict(capital_context.capital_truth_health or {})
        capital_surface = dict(capital_context.capital_surface or {})
        treasury_state = self.auxiliary_state.treasury_state(runtime, capital_truth=capital_truth)
        payload = {
            "ok": True,
            "chain": runtime.cfg.chain.name,
            "metrics": runtime.metrics.model_dump(),
            "opp_count": int(len(runtime._opps)),
            "top_opportunity": top_info,
            "execution_gate": execution_gate,
            "auto_trade_gate": auto_trade_gate,
            "auto_trade_recovery": auto_trade_recovery,
            "hold": hold,
            "execution_advisory": execution_advisory,
            "settings": {
                "auto_trading": bool(runtime._auto_trading),
                "gas_mode": str(runtime.cfg.execution.gas_mode),
                "send_mode": str(runtime.cfg.execution.send_mode),
                "brain_mode": str(getattr(runtime.cfg.execution, "brain_mode", "off") or "off"),
                "dry_run": bool(getattr(runtime.cfg.execution, "dry_run", True)),
                "withdraw_mode": str(
                    getattr(runtime.cfg.execution, "withdraw_mode", "txdata") or "txdata"
                ),
            },
            "deploy": {
                "mode": "public" if is_public_mode() else "private",
                "public_allow_broadcast": bool(public_broadcast_override_enabled()),
            },
            "bankroll": {
                "base_borrow_amount_wei": str(int(runtime._bankroll.cfg.base_borrow_amount_wei)),
                "max_borrow_amount_wei": str(int(runtime._bankroll.cfg.max_borrow_amount_wei)),
                "realized_profit_wei": str(int(runtime._bankroll.state.realized_profit_wei)),
                "last_amount_in_wei": str(int(runtime._bankroll.state.last_amount_in_wei)),
                "success_streak": int(runtime._bankroll.state.success_streak),
                "fail_streak": int(runtime._bankroll.state.fail_streak),
                "success_rate_pct": float(runtime._bankroll.success_rate_pct()),
                "updated_ts_ms": int(getattr(runtime._bankroll.state, "updated_ts_ms", 0) or 0),
                "profit_updated_ts_ms": int(
                    getattr(runtime._bankroll.state, "profit_updated_ts_ms", 0) or 0
                ),
                "sizing_updated_ts_ms": int(
                    getattr(runtime._bankroll.state, "sizing_updated_ts_ms", 0) or 0
                ),
            },
            "rpc": runtime.rpc_manager.snapshot(),
            **capital_surface,
            "treasury": {
                "ok": treasury_state.get("ok", True),
                "enabled": treasury_state.get("enabled", False),
                "capitalSummary": dict(capital_surface.get("capitalSummary") or {}),
                "capitalContract": dict(capital_surface.get("capitalContract") or {}),
                "capitalPolicy": dict(capital_surface.get("capitalPolicy") or {}),
                "capitalTruthHealth": dict(
                    treasury_state.get("capitalTruthHealth") or capital_truth_health
                ),
                "capitalLedgerTruth": dict(capital_surface.get("capitalLedgerTruth") or {}),
                "capital": dict(capital_surface.get("capital") or {}),
            },
            "executor": self._executor_state(runtime),
        }
        payload["summaryContract"] = build_summary_read_contract(
            family="runtime_operator",
            payload=payload,
            capital_contract=capital_truth.capital_contract,
            capital_policy=capital_truth.capital_policy,
            source_contracts={
                "capitalTruth": capital_truth_health,
                "autoTradeRecovery": auto_trade_recovery,
                "executionGate": execution_gate,
            },
            phase="runtime_operator_summary",
            read_model="runtime_operator_summary_projection_v1",
        )
        return to_json_safe(payload)

    async def admin_snapshot(self, runtime: Any) -> Dict[str, Any]:
        snap = await self.snapshot(runtime)
        snap["errors"] = list(runtime._errors)[-10:]
        snap["exec_log"] = to_json_safe(list(runtime._exec_log)[-50:])
        snap["efficiency"] = runtime._eff.snapshot()
        snap["deploy"] = {
            "mode": "public" if is_public_mode() else "private",
            "public_allow_broadcast": bool(public_broadcast_override_enabled()),
        }
        snap["settings"] = {
            "auto_trading": bool(runtime._auto_trading),
            "gas_mode": str(runtime.cfg.execution.gas_mode),
            "send_mode": str(runtime.cfg.execution.send_mode),
            "brain_mode": str(getattr(runtime.cfg.execution, "brain_mode", "off") or "off"),
            "dry_run": bool(getattr(runtime.cfg.execution, "dry_run", True)),
            "withdraw_mode": str(
                getattr(runtime.cfg.execution, "withdraw_mode", "txdata") or "txdata"
            ),
        }
        snap["bankroll"] = to_json_safe(
            {
                "auto_reinvest_enabled": runtime._bankroll.cfg.auto_reinvest_enabled,
                "reinvest_rate_pct": runtime._bankroll.cfg.reinvest_rate_pct,
                "base_borrow_amount_wei": runtime._bankroll.cfg.base_borrow_amount_wei,
                "max_borrow_amount_wei": runtime._bankroll.cfg.max_borrow_amount_wei,
                "state": {
                    "realized_profit_wei": runtime._bankroll.state.realized_profit_wei,
                    "last_amount_in_wei": runtime._bankroll.state.last_amount_in_wei,
                    "success_streak": runtime._bankroll.state.success_streak,
                    "fail_streak": runtime._bankroll.state.fail_streak,
                    "success_rate_pct": runtime._bankroll.success_rate_pct(),
                    "updated_ts_ms": getattr(runtime._bankroll.state, "updated_ts_ms", 0),
                    "profit_updated_ts_ms": getattr(
                        runtime._bankroll.state, "profit_updated_ts_ms", 0
                    ),
                    "sizing_updated_ts_ms": getattr(
                        runtime._bankroll.state, "sizing_updated_ts_ms", 0
                    ),
                },
            }
        )
        snap["pnl_summary"] = await runtime._pnl.summary(window=50)
        snap["circuit_breaker"] = runtime._cb.snapshot()
        snap["brain"] = runtime._decision.brain_state()
        snap["engine_summary"] = runtime.engine_state()
        snap["capital"] = runtime.capital_engine_state()
        return snap
