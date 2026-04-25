from __future__ import annotations

import time
from typing import Any, Dict

_CURRENT_FRESH_MS = 15 * 60 * 1000
_RECENT_FRESH_MS = 6 * 60 * 60 * 1000
_AGING_FRESH_MS = 24 * 60 * 60 * 1000
_RECOVERED_RECENT_MS = 24 * 60 * 60 * 1000
_CHRONIC_DEGRADE_MS = 7 * 24 * 60 * 60 * 1000
_PERSISTENT_DEGRADE_MS = 24 * 60 * 60 * 1000


def _unique_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value = str(value or "")
        if value and value not in out:
            out.append(value)
    return out


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _kill_switch_reason_codes(kill_switch: Dict[str, Any] | None) -> list[str]:
    state = dict(kill_switch or {})
    suppressions = state.get("suppressions") or {}
    if not isinstance(suppressions, dict) or not suppressions:
        return []
    detailed: list[str] = []
    for item in suppressions.values():
        if not isinstance(item, dict):
            continue
        for code in list(item.get("reason_codes") or []):
            sval = str(code or "")
            if sval and sval not in detailed:
                detailed.append(sval)
    return _unique_strings(["kill_switch_active", *detailed])


def _fund_hold_summary(
    *,
    drawdown: Dict[str, Any] | None,
    kill_switch: Dict[str, Any] | None,
    capital_truth_reason_codes: list[str],
    receipt_outcome_truth_reason_codes: list[str],
    internal_prime_reason_codes: list[str],
    family_hardening_reason_codes: list[str],
) -> Dict[str, Any]:
    drawdown_state = dict(drawdown or {})
    hard_stop = dict(drawdown_state.get("hardStop") or {})
    drawdown_reason_codes = []
    if bool(hard_stop.get("active", False)):
        drawdown_reason_codes = [
            str(x) for x in list(hard_stop.get("reason_codes") or []) if str(x)
        ] or ["drawdown_hard_stop"]
    kill_switch_reason_codes = _kill_switch_reason_codes(kill_switch)
    global_execution_reason_codes = _unique_strings(
        [*drawdown_reason_codes, *kill_switch_reason_codes]
    )
    hold_reason_codes = _unique_strings(
        [
            *global_execution_reason_codes,
            *[str(x) for x in family_hardening_reason_codes if str(x)],
            *[str(x) for x in capital_truth_reason_codes if str(x)],
            *[str(x) for x in internal_prime_reason_codes if str(x)],
        ]
    )
    hold_reason_code = hold_reason_codes[0] if hold_reason_codes else ""
    suggested_next_action = ""
    if drawdown_reason_codes:
        suggested_next_action = "reduce_drawdown_and_clear_hard_stop"
    elif kill_switch_reason_codes:
        suggested_next_action = "review_kill_switch_and_restore_execution"
    elif family_hardening_reason_codes:
        suggested_next_action = "restore_family_hardening"
    elif internal_prime_reason_codes:
        suggested_next_action = "repair_internal_prime_accounting"
    elif receipt_outcome_truth_reason_codes:
        suggested_next_action = "restore_receipt_outcome_truth"
    elif capital_truth_reason_codes:
        suggested_next_action = (
            "refresh_capital_truth_snapshot"
            if capital_truth_reason_codes
            and all(
                str(code).startswith("capital_truth_freshness_")
                for code in capital_truth_reason_codes
            )
            else "restore_capital_truth"
        )
    return {
        "globalExecutionBlocked": bool(global_execution_reason_codes),
        "globalExecutionReasonCodes": global_execution_reason_codes,
        "holdReasonCode": hold_reason_code,
        "holdReasonCodes": hold_reason_codes,
        "suggestedNextAction": suggested_next_action if hold_reason_code else "",
    }


def _fund_recovery_summary(
    *,
    drawdown: Dict[str, Any] | None,
    kill_switch: Dict[str, Any] | None,
    capital_truth_reason_codes: list[str],
    receipt_outcome_truth_reason_codes: list[str],
    internal_prime_reason_codes: list[str],
    family_hardening_reason_codes: list[str],
) -> Dict[str, Any]:
    drawdown_state = dict(drawdown or {})
    hard_stop = dict(drawdown_state.get("hardStop") or {})
    drawdown_reason_codes = []
    if bool(hard_stop.get("active", False)):
        drawdown_reason_codes = [
            str(x) for x in list(hard_stop.get("reason_codes") or []) if str(x)
        ] or ["drawdown_hard_stop"]
    kill_switch_reason_codes = _kill_switch_reason_codes(kill_switch)
    global_execution_reason_codes = _unique_strings(
        [*drawdown_reason_codes, *kill_switch_reason_codes]
    )

    recovery_status = "ready"
    recovery_reason_codes: list[str] = []
    recovery_next_action = ""
    if global_execution_reason_codes:
        recovery_status = "global_execution_blocked"
        recovery_reason_codes = global_execution_reason_codes
        recovery_next_action = (
            "reduce_drawdown_and_clear_hard_stop"
            if drawdown_reason_codes
            else "review_kill_switch_and_restore_execution"
        )
    elif family_hardening_reason_codes:
        recovery_status = "family_hardening_restore_required"
        recovery_reason_codes = _unique_strings(
            [str(x) for x in family_hardening_reason_codes if str(x)]
        )
        recovery_next_action = "restore_family_hardening"
    elif internal_prime_reason_codes:
        recovery_status = "internal_prime_reconciliation_required"
        recovery_reason_codes = _unique_strings(
            [str(x) for x in internal_prime_reason_codes if str(x)]
        )
        recovery_next_action = "repair_internal_prime_accounting"
    elif receipt_outcome_truth_reason_codes:
        recovery_status = "capital_truth_restore_required"
        recovery_reason_codes = _unique_strings(
            [str(x) for x in receipt_outcome_truth_reason_codes if str(x)]
        )
        recovery_next_action = "restore_receipt_outcome_truth"
    elif capital_truth_reason_codes:
        recovery_status = "capital_truth_restore_required"
        recovery_reason_codes = _unique_strings(
            [str(x) for x in capital_truth_reason_codes if str(x)]
        )
        recovery_next_action = (
            "refresh_capital_truth_snapshot"
            if capital_truth_reason_codes
            and all(
                str(code).startswith("capital_truth_freshness_")
                for code in capital_truth_reason_codes
            )
            else "restore_capital_truth"
        )

    recovery_reason_code = recovery_reason_codes[0] if recovery_reason_codes else "ok"
    return {
        "recoveryReady": recovery_status == "ready",
        "recoveryStatus": recovery_status,
        "recoveryReasonCode": recovery_reason_code,
        "recoveryReasonCodes": recovery_reason_codes,
        "recoveryNextAction": recovery_next_action if recovery_reason_codes else "",
    }


def _freshness_class(
    age_ms: int | None,
    *,
    unavailable: bool = False,
    idle: bool = False,
) -> str:
    if unavailable:
        return "unavailable"
    if idle:
        return "idle"
    if age_ms is None:
        return "unknown"
    if age_ms <= _CURRENT_FRESH_MS:
        return "current"
    if age_ms <= _RECENT_FRESH_MS:
        return "recent"
    if age_ms <= _AGING_FRESH_MS:
        return "aging"
    return "stale"


def _freshness_reason_codes(prefix: str, freshness_class: str) -> list[str]:
    if freshness_class in {"aging", "stale", "unknown", "unavailable"}:
        return [f"{prefix}_freshness_{freshness_class}"]
    return []


def _degradation_severity_class(
    *,
    history_status: str,
    degraded_duration_ms: int,
    degraded_count: int,
    recovered_recently: bool,
) -> str:
    status = str(history_status or "steady")
    if status == "blocked":
        return "blocked"
    if status == "recovered":
        return "recovering" if recovered_recently else "stable"
    if status != "degraded":
        return "stable"
    if int(degraded_duration_ms or 0) >= _CHRONIC_DEGRADE_MS or int(degraded_count or 0) >= 5:
        return "chronic"
    if int(degraded_duration_ms or 0) >= _PERSISTENT_DEGRADE_MS or int(degraded_count or 0) >= 3:
        return "persistent"
    return "acute"


def _component_recovery_history(
    *,
    history: Dict[str, Any] | None,
    degraded_now: bool,
    now_ms: int,
) -> Dict[str, Any]:
    payload = dict(history or {})
    degraded_since_ts_ms = _safe_int(payload.get("degraded_since_ts_ms"))
    last_recovered_ts_ms = _safe_int(payload.get("last_recovered_ts_ms"))
    degraded_count = _safe_int(payload.get("degraded_count"))
    last_healthy_ts_ms = _safe_int(payload.get("last_healthy_ts_ms"))
    if degraded_now and degraded_since_ts_ms <= 0:
        degraded_since_ts_ms = int(now_ms or 0)
    degraded_duration_ms = (
        max(0, int(now_ms or 0) - degraded_since_ts_ms)
        if degraded_now and degraded_since_ts_ms > 0
        else 0
    )
    if degraded_now and degraded_count <= 0:
        degraded_count = 1
    history_status = (
        "degraded" if degraded_now else ("recovered" if last_recovered_ts_ms > 0 else "steady")
    )
    recovered_recently = bool(
        not degraded_now
        and last_recovered_ts_ms > 0
        and int(now_ms or 0) > 0
        and max(0, int(now_ms or 0) - last_recovered_ts_ms) <= _RECOVERED_RECENT_MS
    )
    degradation_severity_class = _degradation_severity_class(
        history_status=history_status,
        degraded_duration_ms=int(degraded_duration_ms or 0),
        degraded_count=int(degraded_count or 0),
        recovered_recently=recovered_recently,
    )
    return {
        "historyStatus": history_status,
        "degradedSinceTsMs": int(degraded_since_ts_ms or 0),
        "recoveredAtTsMs": int(last_recovered_ts_ms or 0),
        "degradedDurationMs": int(degraded_duration_ms or 0),
        "degradedCount": int(degraded_count or 0),
        "lastHealthyTsMs": int(last_healthy_ts_ms or 0),
        "recoveredRecently": bool(recovered_recently),
        "degradationSeverityClass": degradation_severity_class,
    }


def apply_recovery_history(
    health: Dict[str, Any],
    *,
    histories: Dict[str, Dict[str, Any]] | None = None,
    now_ms: int | None = None,
) -> Dict[str, Any]:
    payload = dict(health or {})
    component_histories = dict(histories or {})
    observed_now_ms = (
        _safe_int(now_ms)
        or _safe_int(payload.get("capitalTruthObservedTsMs"))
        or int(time.time() * 1000)
    )

    capital_history = _component_recovery_history(
        history=component_histories.get("capital_truth"),
        degraded_now=bool(list(payload.get("capitalTruthReasonCodes") or [])),
        now_ms=observed_now_ms,
    )
    receipt_outcome_truth_history = _component_recovery_history(
        history=component_histories.get("receipt_outcome_truth"),
        degraded_now=bool(list(payload.get("receiptOutcomeTruthReasonCodes") or [])),
        now_ms=observed_now_ms,
    )
    internal_prime_history = _component_recovery_history(
        history=component_histories.get("internal_prime_reconciliation"),
        degraded_now=bool(list(payload.get("internalPrimeReasonCodes") or [])),
        now_ms=observed_now_ms,
    )
    family_hardening_history = _component_recovery_history(
        history=component_histories.get("family_hardening"),
        degraded_now=bool(list(payload.get("familyHardeningReasonCodes") or [])),
        now_ms=observed_now_ms,
    )

    payload.update(
        {
            "capitalTruthRecoveryHistoryStatus": capital_history["historyStatus"],
            "capitalTruthDegradedSinceTsMs": capital_history["degradedSinceTsMs"],
            "capitalTruthRecoveredAtTsMs": capital_history["recoveredAtTsMs"],
            "capitalTruthDegradedDurationMs": capital_history["degradedDurationMs"],
            "capitalTruthDegradedCount": capital_history["degradedCount"],
            "capitalTruthLastHealthyTsMs": capital_history["lastHealthyTsMs"],
            "capitalTruthRecoveredRecently": capital_history["recoveredRecently"],
            "capitalTruthDegradationSeverityClass": capital_history["degradationSeverityClass"],
            "receiptOutcomeTruthRecoveryHistoryStatus": receipt_outcome_truth_history[
                "historyStatus"
            ],
            "receiptOutcomeTruthDegradedSinceTsMs": receipt_outcome_truth_history[
                "degradedSinceTsMs"
            ],
            "receiptOutcomeTruthRecoveredAtTsMs": receipt_outcome_truth_history["recoveredAtTsMs"],
            "receiptOutcomeTruthDegradedDurationMs": receipt_outcome_truth_history[
                "degradedDurationMs"
            ],
            "receiptOutcomeTruthDegradedCount": receipt_outcome_truth_history["degradedCount"],
            "receiptOutcomeTruthLastHealthyTsMs": receipt_outcome_truth_history["lastHealthyTsMs"],
            "receiptOutcomeTruthRecoveredRecently": receipt_outcome_truth_history[
                "recoveredRecently"
            ],
            "receiptOutcomeTruthDegradationSeverityClass": receipt_outcome_truth_history[
                "degradationSeverityClass"
            ],
            "internalPrimeRecoveryHistoryStatus": internal_prime_history["historyStatus"],
            "internalPrimeDegradedSinceTsMs": internal_prime_history["degradedSinceTsMs"],
            "internalPrimeRecoveredAtTsMs": internal_prime_history["recoveredAtTsMs"],
            "internalPrimeDegradedDurationMs": internal_prime_history["degradedDurationMs"],
            "internalPrimeDegradedCount": internal_prime_history["degradedCount"],
            "internalPrimeLastHealthyTsMs": internal_prime_history["lastHealthyTsMs"],
            "internalPrimeRecoveredRecently": internal_prime_history["recoveredRecently"],
            "internalPrimeDegradationSeverityClass": internal_prime_history[
                "degradationSeverityClass"
            ],
            "familyHardeningRecoveryHistoryStatus": family_hardening_history["historyStatus"],
            "familyHardeningDegradedSinceTsMs": family_hardening_history["degradedSinceTsMs"],
            "familyHardeningRecoveredAtTsMs": family_hardening_history["recoveredAtTsMs"],
            "familyHardeningDegradedDurationMs": family_hardening_history["degradedDurationMs"],
            "familyHardeningDegradedCount": family_hardening_history["degradedCount"],
            "familyHardeningLastHealthyTsMs": family_hardening_history["lastHealthyTsMs"],
            "familyHardeningRecoveredRecently": family_hardening_history["recoveredRecently"],
            "familyHardeningDegradationSeverityClass": family_hardening_history[
                "degradationSeverityClass"
            ],
        }
    )

    recovery_status = str(payload.get("recoveryStatus") or "ready")
    recovery_component = ""
    selected = {
        "historyStatus": "steady",
        "degradedSinceTsMs": 0,
        "recoveredAtTsMs": 0,
        "degradedDurationMs": 0,
    }
    receipt_outcome_truth_reason_codes = [
        str(x) for x in list(payload.get("receiptOutcomeTruthReasonCodes") or []) if str(x)
    ]
    if recovery_status == "family_hardening_restore_required":
        recovery_component = "family_hardening"
        selected = family_hardening_history
    elif recovery_status == "capital_truth_restore_required":
        if receipt_outcome_truth_reason_codes:
            recovery_component = "receipt_outcome_truth"
            selected = receipt_outcome_truth_history
        else:
            recovery_component = "capital_truth"
            selected = capital_history
    elif recovery_status == "internal_prime_reconciliation_required":
        recovery_component = "internal_prime_reconciliation"
        selected = internal_prime_history
    elif recovery_status == "ready":
        recovered_candidates = [
            ("family_hardening", family_hardening_history),
            ("receipt_outcome_truth", receipt_outcome_truth_history),
            ("capital_truth", capital_history),
            ("internal_prime_reconciliation", internal_prime_history),
        ]
        recovered_candidates = [
            item for item in recovered_candidates if int(item[1].get("recoveredAtTsMs") or 0) > 0
        ]
        if recovered_candidates:
            recovery_component, selected = max(
                recovered_candidates,
                key=lambda item: int(item[1].get("recoveredAtTsMs") or 0),
            )
            if str(selected.get("historyStatus") or "") != "recovered":
                selected = {
                    **selected,
                    "historyStatus": "recovered",
                }
    elif recovery_status == "global_execution_blocked":
        selected = {
            **selected,
            "historyStatus": "blocked",
        }

    payload.update(
        {
            "recoveryHistoryComponent": recovery_component,
            "recoveryHistoryStatus": str(selected.get("historyStatus") or "steady"),
            "recoveryDegradedSinceTsMs": _safe_int(selected.get("degradedSinceTsMs")),
            "recoveryRecoveredAtTsMs": _safe_int(selected.get("recoveredAtTsMs")),
            "recoveryDegradedDurationMs": _safe_int(selected.get("degradedDurationMs")),
            "recoveryDegradedCount": _safe_int(selected.get("degradedCount")),
            "recoveryLastHealthyTsMs": _safe_int(selected.get("lastHealthyTsMs")),
            "recoveryRecoveredRecently": bool(selected.get("recoveredRecently", False)),
            "recoveryDegradationSeverityClass": str(
                selected.get("degradationSeverityClass") or "stable"
            ),
        }
    )
    return payload


def _reliability_rank(value: str) -> int:
    order = {
        "blocked": 6,
        "unavailable": 5,
        "unknown": 4,
        "degraded": 3,
        "fragile": 2,
        "cautious": 1,
        "stable": 0,
    }
    return int(order.get(str(value or "stable"), 0))


def _component_reliability_summary(
    prefix: str,
    *,
    history_status: str,
    freshness_class: str,
    degraded_count: int,
    recovered_recently: bool,
    severity_class: str,
    source_reason_codes: list[str],
) -> Dict[str, Any]:
    history = str(history_status or "steady")
    freshness = str(freshness_class or "unknown")
    severity = str(severity_class or "stable")
    count = int(degraded_count or 0)

    if history == "blocked":
        reliability_class = "blocked"
    elif freshness in {"unavailable", "unknown"}:
        reliability_class = freshness
    elif history == "degraded":
        reliability_class = "degraded"
    elif history == "recovered":
        if recovered_recently and (severity in {"persistent", "chronic"} or count >= 2):
            reliability_class = "fragile"
        elif recovered_recently or count >= 2 or freshness == "aging":
            reliability_class = "cautious"
        else:
            reliability_class = "stable"
    else:
        if freshness == "stale":
            reliability_class = "fragile"
        elif freshness == "aging":
            reliability_class = "cautious"
        elif severity in {"persistent", "chronic"} or count >= 4:
            reliability_class = "fragile"
        elif count >= 2:
            reliability_class = "cautious"
        else:
            reliability_class = "stable"

    recovered_fragile = bool(history == "recovered" and reliability_class == "fragile")
    reliability_reason_codes = _unique_strings(
        [
            *(
                [f"{prefix}_reliability_{reliability_class}"]
                if reliability_class != "stable"
                else []
            ),
            *([f"{prefix}_recovered_fragile"] if recovered_fragile else []),
            *[str(x) for x in source_reason_codes if str(x)],
        ]
    )
    return {
        "reliabilityClass": reliability_class,
        "reliabilityReasonCode": reliability_reason_codes[0] if reliability_reason_codes else "ok",
        "reliabilityReasonCodes": reliability_reason_codes,
        "recoveredFragile": recovered_fragile,
    }


def apply_recovery_reliability(health: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(health or {})

    capital_rel = _component_reliability_summary(
        "capital_truth",
        history_status=str(payload.get("capitalTruthRecoveryHistoryStatus") or "steady"),
        freshness_class=str(payload.get("capitalTruthFreshnessClass") or "unknown"),
        degraded_count=int(payload.get("capitalTruthDegradedCount") or 0),
        recovered_recently=bool(payload.get("capitalTruthRecoveredRecently", False)),
        severity_class=str(payload.get("capitalTruthDegradationSeverityClass") or "stable"),
        source_reason_codes=_unique_strings(
            [
                *[str(x) for x in list(payload.get("capitalTruthReasonCodes") or []) if str(x)],
                *[
                    str(x)
                    for x in list(payload.get("capitalTruthFreshnessReasonCodes") or [])
                    if str(x)
                ],
            ]
        ),
    )
    receipt_outcome_truth_rel = _component_reliability_summary(
        "receipt_outcome_truth",
        history_status=str(payload.get("receiptOutcomeTruthRecoveryHistoryStatus") or "steady"),
        freshness_class=str(payload.get("receiptOutcomeTruthFreshnessClass") or "unknown"),
        degraded_count=int(payload.get("receiptOutcomeTruthDegradedCount") or 0),
        recovered_recently=bool(payload.get("receiptOutcomeTruthRecoveredRecently", False)),
        severity_class=str(payload.get("receiptOutcomeTruthDegradationSeverityClass") or "stable"),
        source_reason_codes=_unique_strings(
            [
                *[
                    str(x)
                    for x in list(payload.get("receiptOutcomeTruthReasonCodes") or [])
                    if str(x)
                ],
                *[
                    str(x)
                    for x in list(payload.get("receiptOutcomeTruthFreshnessReasonCodes") or [])
                    if str(x)
                ],
            ]
        ),
    )
    internal_prime_rel = _component_reliability_summary(
        "internal_prime",
        history_status=str(payload.get("internalPrimeRecoveryHistoryStatus") or "steady"),
        freshness_class=str(payload.get("internalPrimeFreshnessClass") or "unknown"),
        degraded_count=int(payload.get("internalPrimeDegradedCount") or 0),
        recovered_recently=bool(payload.get("internalPrimeRecoveredRecently", False)),
        severity_class=str(payload.get("internalPrimeDegradationSeverityClass") or "stable"),
        source_reason_codes=_unique_strings(
            [
                *[str(x) for x in list(payload.get("internalPrimeReasonCodes") or []) if str(x)],
                *[
                    str(x)
                    for x in list(payload.get("internalPrimeFreshnessReasonCodes") or [])
                    if str(x)
                ],
            ]
        ),
    )
    family_hardening_status = str(payload.get("familyHardeningStatus") or "ok")
    family_hardening_reason_codes = _unique_strings(
        [str(x) for x in list(payload.get("familyHardeningReasonCodes") or []) if str(x)]
    )
    family_hardening_rel = _component_reliability_summary(
        "family_hardening",
        history_status=str(payload.get("familyHardeningRecoveryHistoryStatus") or "steady"),
        freshness_class=("unavailable" if family_hardening_status == "unavailable" else "current"),
        degraded_count=int(payload.get("familyHardeningDegradedCount") or 0),
        recovered_recently=bool(payload.get("familyHardeningRecoveredRecently", False)),
        severity_class=str(payload.get("familyHardeningDegradationSeverityClass") or "stable"),
        source_reason_codes=family_hardening_reason_codes,
    )

    recovery_status = str(payload.get("recoveryStatus") or "ready")
    global_execution_reason_codes = [
        str(x) for x in list(payload.get("globalExecutionReasonCodes") or []) if str(x)
    ]
    recovery_history_component = str(payload.get("recoveryHistoryComponent") or "")
    recovery_next_action = str(
        payload.get("recoveryNextAction") or payload.get("suggestedNextAction") or ""
    )
    recovery_freshness_next_action = str(payload.get("recoveryFreshnessNextAction") or "")

    selected_component = ""
    selected_rel = {
        "reliabilityClass": "stable",
        "reliabilityReasonCodes": [],
        "reliabilityReasonCode": "ok",
        "recoveredFragile": False,
    }
    recovery_reliability_class = "stable"
    recovery_reliability_reason_codes: list[str] = []
    if recovery_status == "global_execution_blocked":
        recovery_reliability_class = "blocked"
        recovery_reliability_reason_codes = _unique_strings(
            ["recovery_reliability_blocked", *global_execution_reason_codes]
        )
    else:
        if recovery_status == "family_hardening_restore_required":
            selected_component = "family_hardening"
            selected_rel = family_hardening_rel
        elif recovery_status == "capital_truth_restore_required":
            if list(payload.get("receiptOutcomeTruthReasonCodes") or []):
                selected_component = "receipt_outcome_truth"
                selected_rel = receipt_outcome_truth_rel
            else:
                selected_component = "capital_truth"
                selected_rel = capital_rel
        elif recovery_status == "internal_prime_reconciliation_required":
            selected_component = "internal_prime_reconciliation"
            selected_rel = internal_prime_rel
        elif recovery_history_component == "family_hardening":
            selected_component = "family_hardening"
            selected_rel = family_hardening_rel
        elif recovery_history_component == "receipt_outcome_truth":
            selected_component = "receipt_outcome_truth"
            selected_rel = receipt_outcome_truth_rel
        elif recovery_history_component == "capital_truth":
            selected_component = "capital_truth"
            selected_rel = capital_rel
        elif recovery_history_component == "internal_prime_reconciliation":
            selected_component = "internal_prime_reconciliation"
            selected_rel = internal_prime_rel
        else:
            candidates: list[tuple[str, Dict[str, Any]]] = [
                ("family_hardening", family_hardening_rel),
                ("receipt_outcome_truth", receipt_outcome_truth_rel),
                ("capital_truth", capital_rel),
                ("internal_prime_reconciliation", internal_prime_rel),
            ]
            selected_component, selected_rel = max(
                candidates,
                key=lambda item: _reliability_rank(
                    str(item[1].get("reliabilityClass") or "stable")
                ),
            )
        recovery_reliability_class = str(selected_rel.get("reliabilityClass") or "stable")
        selected_rel_reason_codes = selected_rel.get("reliabilityReasonCodes") or []
        if not isinstance(selected_rel_reason_codes, list):
            selected_rel_reason_codes = []
        recovery_reliability_reason_codes = _unique_strings(
            [
                *(
                    [f"recovery_reliability_{recovery_reliability_class}"]
                    if recovery_reliability_class != "stable"
                    else []
                ),
                *(
                    ["recovery_recovered_fragile"]
                    if bool(selected_rel.get("recoveredFragile", False))
                    else []
                ),
                *[str(x) for x in selected_rel_reason_codes if str(x)],
            ]
        )

    recovery_reliability_next_action = ""
    if recovery_reliability_class != "stable":
        recovery_reliability_next_action = recovery_next_action or recovery_freshness_next_action

    payload.update(
        {
            "capitalTruthReliabilityClass": str(capital_rel.get("reliabilityClass") or "stable"),
            "receiptOutcomeTruthReliabilityClass": str(
                receipt_outcome_truth_rel.get("reliabilityClass") or "stable"
            ),
            "receiptOutcomeTruthReliabilityReasonCode": str(
                receipt_outcome_truth_rel.get("reliabilityReasonCode") or "ok"
            ),
            "receiptOutcomeTruthReliabilityReasonCodes": list(
                receipt_outcome_truth_rel.get("reliabilityReasonCodes") or []
            ),
            "receiptOutcomeTruthRecoveredFragile": bool(
                receipt_outcome_truth_rel.get("recoveredFragile", False)
            ),
            "capitalTruthReliabilityReasonCode": str(
                capital_rel.get("reliabilityReasonCode") or "ok"
            ),
            "capitalTruthReliabilityReasonCodes": list(
                capital_rel.get("reliabilityReasonCodes") or []
            ),
            "capitalTruthRecoveredFragile": bool(capital_rel.get("recoveredFragile", False)),
            "internalPrimeReliabilityClass": str(
                internal_prime_rel.get("reliabilityClass") or "stable"
            ),
            "internalPrimeReliabilityReasonCode": str(
                internal_prime_rel.get("reliabilityReasonCode") or "ok"
            ),
            "internalPrimeReliabilityReasonCodes": list(
                internal_prime_rel.get("reliabilityReasonCodes") or []
            ),
            "internalPrimeRecoveredFragile": bool(
                internal_prime_rel.get("recoveredFragile", False)
            ),
            "familyHardeningReliabilityClass": str(
                family_hardening_rel.get("reliabilityClass") or "stable"
            ),
            "familyHardeningReliabilityReasonCode": str(
                family_hardening_rel.get("reliabilityReasonCode") or "ok"
            ),
            "familyHardeningReliabilityReasonCodes": [
                str(x)
                for x in list(family_hardening_rel.get("reliabilityReasonCodes") or [])
                if str(x)
            ],
            "familyHardeningRecoveredFragile": bool(
                family_hardening_rel.get("recoveredFragile", False)
            ),
            "recoveryReliabilityComponent": selected_component,
            "recoveryReliabilityClass": recovery_reliability_class,
            "recoveryReliabilityReasonCode": (
                recovery_reliability_reason_codes[0] if recovery_reliability_reason_codes else "ok"
            ),
            "recoveryReliabilityReasonCodes": recovery_reliability_reason_codes,
            "recoveryReliabilityNextAction": recovery_reliability_next_action,
            "recoveryRecoveredFragile": (
                bool(selected_rel.get("recoveredFragile", False))
                if recovery_reliability_class != "blocked"
                else False
            ),
        }
    )
    return payload


def _journal_last_ts_ms(truth: Dict[str, Any]) -> int:
    ledger = dict(truth.get("ledger") or {})
    last_ts_ms = 0
    for tx in list(ledger.get("transactions") or []):
        if not isinstance(tx, dict):
            continue
        tx_type = str(tx.get("tx_type") or "")
        if not tx_type.startswith("prime_loan_"):
            continue
        last_ts_ms = max(last_ts_ms, _safe_int(tx.get("ts_ms")))
    return last_ts_ms


def build_fund_health_summary(
    *,
    fund_os: Dict[str, Any],
    alpha: Dict[str, Any],
    research: Dict[str, Any],
    capital: Dict[str, Any],
    risk: Dict[str, Any],
    engines: Dict[str, Any],
    telemetry: Dict[str, Any],
    capital_truth: Dict[str, Any] | None = None,
    internal_prime: Dict[str, Any] | None = None,
    family_hardening: Dict[str, Any] | None = None,
    drawdown: Dict[str, Any] | None = None,
    kill_switch: Dict[str, Any] | None = None,
    endpoint_quality: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    capital_eff = dict((capital or {}).get("capital_efficiency_metrics") or {})
    throughput = dict((research or {}).get("throughput") or {})
    realization = dict((telemetry or {}).get("realization") or {})
    false_adm = float(realization.get("falseAdmissionRate") or 0.0)
    false_drop = float(realization.get("falseDropRate") or 0.0)

    truth = dict(capital_truth or {})
    truth_status = str(
        truth.get("status") or ("ok" if bool(truth.get("ok", True)) else "unavailable")
    )
    truth_reasons = [str(x) for x in list(truth.get("status_reasons") or []) if str(x)]
    if truth_status != "ok" and not truth_reasons:
        fallback_reason = str(
            truth.get("reason_code")
            or truth.get("reason")
            or ("capital_truth_unavailable" if truth_status == "unavailable" else truth_status)
        )
        if fallback_reason:
            truth_reasons = [fallback_reason]
    prime_reconciliation = dict(
        (truth.get("reconciliation") or {}).get("internal_prime_journal") or {}
    )
    prime_reasons = [str(x) for x in list(prime_reconciliation.get("reasons") or []) if str(x)]
    direct_internal_prime = dict(internal_prime or {})
    direct_internal_prime_status = (
        str(
            direct_internal_prime.get("stateStatus")
            or direct_internal_prime.get("status")
            or (
                "ok"
                if bool(
                    direct_internal_prime.get("stateReady", direct_internal_prime.get("ok", True))
                )
                else "unavailable"
            )
        )
        .strip()
        .lower()
    )
    direct_internal_prime_ready = bool(
        direct_internal_prime.get(
            "stateReady", direct_internal_prime.get("ok", direct_internal_prime_status == "ok")
        )
    )
    direct_internal_prime_reason_codes = [
        str(x)
        for x in list(
            direct_internal_prime.get("stateReasonCodes")
            or direct_internal_prime.get("reason_codes")
            or []
        )
        if str(x)
    ]
    direct_internal_prime_reason_code = str(
        direct_internal_prime.get("stateReasonCode")
        or direct_internal_prime.get("reason_code")
        or direct_internal_prime.get("stateReason")
        or direct_internal_prime.get("reason")
        or ("internal_prime_unavailable" if direct_internal_prime_status == "unavailable" else "")
    )
    if (
        not direct_internal_prime_ready or direct_internal_prime_status != "ok"
    ) and direct_internal_prime_reason_code:
        direct_internal_prime_reason_codes = [
            direct_internal_prime_reason_code,
            *[
                reason
                for reason in direct_internal_prime_reason_codes
                if reason != direct_internal_prime_reason_code
            ],
        ]
    internal_prime_truth_reasons = [
        reason
        for reason in truth_reasons
        if reason.startswith("internal_prime_") or reason.startswith("prime_state_")
    ]
    internal_prime_reason_codes = _unique_strings(
        [
            *direct_internal_prime_reason_codes,
            *internal_prime_truth_reasons,
            *[reason for reason in prime_reasons if reason not in internal_prime_truth_reasons],
        ]
    )
    family_hardening_state = dict(family_hardening or {})
    family_hardening_status = (
        str(
            family_hardening_state.get("status")
            or ("ok" if bool(family_hardening_state.get("ok", True)) else "unavailable")
        )
        .strip()
        .lower()
    )
    family_hardening_reason_codes = _unique_strings(
        [str(x) for x in list(family_hardening_state.get("reason_codes") or []) if str(x)]
    )
    family_hardening_reason_code = str(
        family_hardening_state.get("reason_code")
        or family_hardening_state.get("reason")
        or (
            "family_hardening_service_unavailable"
            if family_hardening_status == "unavailable"
            else (
                family_hardening_status
                if family_hardening_status and family_hardening_status != "ok"
                else ""
            )
        )
    )
    if family_hardening_reason_code == "family_hardening_unavailable":
        family_hardening_reason_code = "family_hardening_service_unavailable"
    if family_hardening_status != "ok" and family_hardening_reason_code:
        family_hardening_reason_codes = _unique_strings(
            [family_hardening_reason_code, *family_hardening_reason_codes]
        )
    now_ms = _safe_int(truth.get("ts_ms")) or int(time.time() * 1000)
    ledger_state = dict(truth.get("ledger") or {})
    ledger_last_ts_ms = _safe_int(ledger_state.get("last_ts_ms"))
    capital_truth_reference_ts_ms = ledger_last_ts_ms or _safe_int(truth.get("ts_ms"))
    capital_truth_age_ms = (
        max(0, now_ms - capital_truth_reference_ts_ms) if capital_truth_reference_ts_ms else None
    )
    capital_truth_freshness_class = _freshness_class(
        capital_truth_age_ms,
        unavailable=truth_status == "unavailable",
    )
    capital_truth_freshness_reason_codes = _freshness_reason_codes(
        "capital_truth",
        capital_truth_freshness_class,
    )

    capital_truth_ok = truth_status == "ok"
    effective_capital_truth_reason_codes = list(truth_reasons)
    capital_truth_freshness_blocking = capital_truth_freshness_class == "stale"
    if capital_truth_freshness_blocking:
        effective_capital_truth_reason_codes = _unique_strings(
            [*effective_capital_truth_reason_codes, *capital_truth_freshness_reason_codes]
        )
        if truth_status == "ok":
            truth_status = "degraded"
        capital_truth_ok = False

    internal_prime_truth_ok = (
        capital_truth_ok
        and direct_internal_prime_ready
        and direct_internal_prime_status == "ok"
        and not internal_prime_reason_codes
        and (not prime_reconciliation or bool(prime_reconciliation.get("ok", False)))
    )
    receipt_outcome_truth = dict(
        (truth.get("reconciliation") or {}).get("receipt_outcome_truth") or {}
    )
    receipt_outcome_truth_reason_codes = _unique_strings(
        [
            (
                str(receipt_outcome_truth.get("reason_code") or "")
                if bool(receipt_outcome_truth.get("is_degraded", False))
                else ""
            )
        ]
    )
    hold_summary = _fund_hold_summary(
        drawdown=drawdown,
        kill_switch=kill_switch,
        capital_truth_reason_codes=effective_capital_truth_reason_codes,
        receipt_outcome_truth_reason_codes=receipt_outcome_truth_reason_codes,
        internal_prime_reason_codes=internal_prime_reason_codes,
        family_hardening_reason_codes=family_hardening_reason_codes,
    )
    recovery_summary = _fund_recovery_summary(
        drawdown=drawdown,
        kill_switch=kill_switch,
        capital_truth_reason_codes=effective_capital_truth_reason_codes,
        receipt_outcome_truth_reason_codes=receipt_outcome_truth_reason_codes,
        internal_prime_reason_codes=internal_prime_reason_codes,
        family_hardening_reason_codes=family_hardening_reason_codes,
    )

    prime_observed = dict(prime_reconciliation.get("observed") or {})
    prime_open_loan_count = _safe_int(prime_observed.get("open_loan_count"))
    prime_borrowed_usd = _safe_float(prime_observed.get("borrowed_usd"))
    receipt_outcome_truth_observed_ts_ms = _safe_int(
        receipt_outcome_truth.get("updated_ts_ms")
        or receipt_outcome_truth.get("degraded_since_ts_ms")
        or receipt_outcome_truth.get("last_recovered_ts_ms")
        or receipt_outcome_truth.get("last_healthy_ts_ms")
    )
    receipt_outcome_truth_age_ms = (
        max(0, now_ms - receipt_outcome_truth_observed_ts_ms)
        if receipt_outcome_truth_observed_ts_ms
        else None
    )
    receipt_outcome_truth_freshness_class = _freshness_class(
        receipt_outcome_truth_age_ms,
        unavailable=not bool(receipt_outcome_truth_observed_ts_ms),
    )
    receipt_outcome_truth_freshness_reason_codes = _freshness_reason_codes(
        "receipt_outcome_truth",
        receipt_outcome_truth_freshness_class,
    )

    internal_prime_journal_last_ts_ms = _journal_last_ts_ms(truth)
    internal_prime_journal_age_ms = (
        max(0, now_ms - internal_prime_journal_last_ts_ms)
        if internal_prime_journal_last_ts_ms
        else None
    )
    internal_prime_idle = (
        not internal_prime_reason_codes
        and prime_open_loan_count == 0
        and abs(prime_borrowed_usd) <= 1e-6
    )
    internal_prime_freshness_class = _freshness_class(
        internal_prime_journal_age_ms,
        idle=internal_prime_idle,
    )
    internal_prime_freshness_reason_codes = _freshness_reason_codes(
        "internal_prime_reconciliation",
        internal_prime_freshness_class,
    )

    recovery_status = str(recovery_summary.get("recoveryStatus") or "ready")
    recovery_freshness_class = "current"
    recovery_freshness_reason_codes: list[str] = []
    recovery_freshness_next_action = ""
    if recovery_status == "capital_truth_restore_required":
        if receipt_outcome_truth_reason_codes:
            recovery_freshness_class = receipt_outcome_truth_freshness_class
            recovery_freshness_reason_codes = list(receipt_outcome_truth_freshness_reason_codes)
            recovery_freshness_next_action = (
                "refresh_receipt_outcome_truth" if recovery_freshness_reason_codes else ""
            )
        else:
            recovery_freshness_class = capital_truth_freshness_class
            recovery_freshness_reason_codes = list(capital_truth_freshness_reason_codes)
            recovery_freshness_next_action = (
                "refresh_capital_truth_snapshot" if recovery_freshness_reason_codes else ""
            )
    elif recovery_status == "internal_prime_reconciliation_required":
        recovery_freshness_class = internal_prime_freshness_class
        recovery_freshness_reason_codes = list(internal_prime_freshness_reason_codes)
        recovery_freshness_next_action = (
            "refresh_internal_prime_reconciliation" if recovery_freshness_reason_codes else ""
        )
    elif recovery_status == "global_execution_blocked":
        recovery_freshness_class = "current"
    recovery_freshness_reason_code = (
        recovery_freshness_reason_codes[0] if recovery_freshness_reason_codes else "ok"
    )

    return {
        "fundStage": str(
            ((fund_os or {}).get("fund_os") or {}).get("stage_policy", {}).get("stage")
            or "internal_capital"
        ),
        "riskPosture": str((risk or {}).get("posture") or "normal"),
        "riskScore": float((risk or {}).get("riskScore") or 0.0),
        "deployedCapitalWei": int(capital_eff.get("deployedCapitalWei") or 0),
        "utilizationRate": float(capital_eff.get("utilizationRate") or 0.0),
        "capitalQualityScore": round(
            float(capital_eff.get("failureAdjustedCapitalEfficiency") or 0.0)
            * max(0.2, 1.0 - float((risk or {}).get("riskScore") or 0.0)),
            6,
        ),
        "alphaFactory": throughput,
        "activeEngines": int((risk or {}).get("activeEngines") or 0),
        "engineSummary": dict((engines or {}).get("summary") or {}),
        "telemetrySummary": dict(telemetry or {}),
        "researchQualityScore": round(
            float(throughput.get("researchHitRate") or 0.0)
            * max(1, int(throughput.get("candidatesPromoted") or 0)),
            6,
        ),
        "falseAdmissionRate": false_adm,
        "falseDropRate": false_drop,
        "drawdownState": dict(drawdown or {}),
        "killSwitch": dict(kill_switch or {}),
        "endpointQuality": dict(endpoint_quality or {}),
        "privateRoutingReady": not bool((kill_switch or {}).get("suppressions")),
        "capitalTruthStatus": truth_status,
        "capitalTruthReasonCodes": effective_capital_truth_reason_codes,
        "receiptOutcomeTruthStatus": ("degraded" if receipt_outcome_truth_reason_codes else "ok"),
        "receiptOutcomeTruthReasonCodes": receipt_outcome_truth_reason_codes,
        "internalPrimeReasonCodes": internal_prime_reason_codes,
        "familyHardeningStatus": family_hardening_status,
        "familyHardeningReasonCodes": family_hardening_reason_codes,
        **hold_summary,
        **recovery_summary,
        "capitalTruthObservedTsMs": _safe_int(truth.get("ts_ms")) or 0,
        "capitalTruthLedgerLastTsMs": ledger_last_ts_ms,
        "capitalTruthAgeMs": capital_truth_age_ms,
        "capitalTruthFreshnessClass": capital_truth_freshness_class,
        "capitalTruthFreshnessReasonCodes": capital_truth_freshness_reason_codes,
        "receiptOutcomeTruthObservedTsMs": receipt_outcome_truth_observed_ts_ms,
        "receiptOutcomeTruthAgeMs": receipt_outcome_truth_age_ms,
        "receiptOutcomeTruthFreshnessClass": receipt_outcome_truth_freshness_class,
        "receiptOutcomeTruthFreshnessReasonCodes": receipt_outcome_truth_freshness_reason_codes,
        "internalPrimeJournalLastTsMs": internal_prime_journal_last_ts_ms,
        "internalPrimeJournalAgeMs": internal_prime_journal_age_ms,
        "internalPrimeFreshnessClass": internal_prime_freshness_class,
        "internalPrimeFreshnessReasonCodes": internal_prime_freshness_reason_codes,
        "recoveryFreshnessClass": recovery_freshness_class,
        "recoveryFreshnessReasonCode": recovery_freshness_reason_code,
        "recoveryFreshnessReasonCodes": recovery_freshness_reason_codes,
        "recoveryFreshnessNextAction": recovery_freshness_next_action,
        "capitalReady": float((risk or {}).get("riskScore") or 0.0) < 0.92 and capital_truth_ok,
        "internalPrimeReady": (not bool(((drawdown or {}).get("hardStop") or {}).get("active")))
        and internal_prime_truth_ok,
        "familyHardeningReady": family_hardening_status == "ok"
        and not family_hardening_reason_codes,
    }
