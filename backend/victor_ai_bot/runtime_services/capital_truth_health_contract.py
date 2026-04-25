from __future__ import annotations

from typing import Any, Dict

from ..degraded_state_contract import decision_contract


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _unique_strings(values: list[Any]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _pick_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        text = str(payload.get(key) or "").strip()
        if text:
            return text
    return ""


def build_capital_truth_health_view(
    health: Dict[str, Any] | None,
    *,
    capital_truth: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source = _safe_dict(health)
    truth = _safe_dict(capital_truth)

    reason_codes = _unique_strings(
        list(
            source.get("capitalTruthReasonCodes")
            or source.get("capital_truth_reason_codes")
            or truth.get("status_reasons")
            or []
        )
    )
    status = _pick_text(source, "capitalTruthStatus", "capital_truth_status") or _pick_text(
        truth, "status"
    )
    if not status:
        status = "ok" if not reason_codes and bool(truth.get("ok", True)) else "degraded"
    reason_code = _pick_text(
        source, "capitalTruthReasonCode", "capital_truth_reason_code"
    ) or _pick_text(truth, "reason_code", "reason")
    if not reason_code:
        reason_code = (
            reason_codes[0]
            if reason_codes
            else ("ok" if status == "ok" else "capital_truth_degraded")
        )
    if reason_code != "ok" and reason_code not in reason_codes:
        reason_codes = [reason_code, *reason_codes]

    freshness_class = _pick_text(
        source, "capitalTruthFreshnessClass", "capital_truth_freshness_class"
    )
    if not freshness_class:
        freshness_class = "unavailable" if status == "unavailable" else "unknown"
    freshness_reason_codes = _unique_strings(
        list(
            source.get("capitalTruthFreshnessReasonCodes")
            or source.get("capital_truth_freshness_reason_codes")
            or []
        )
    )
    freshness_reason_code = _pick_text(
        source, "capitalTruthFreshnessReasonCode", "capital_truth_freshness_reason_code"
    )
    if not freshness_reason_code:
        freshness_reason_code = (
            freshness_reason_codes[0]
            if freshness_reason_codes
            else (
                f"capital_truth_freshness_{freshness_class}"
                if freshness_class in {"aging", "stale", "unknown", "unavailable"}
                else "ok"
            )
        )
    if freshness_reason_code != "ok" and freshness_reason_code not in freshness_reason_codes:
        freshness_reason_codes = [freshness_reason_code, *freshness_reason_codes]

    observed_ts_ms = _safe_int(
        source.get("capitalTruthObservedTsMs")
        or source.get("capital_truth_observed_ts_ms")
        or truth.get("ts_ms")
    )
    ledger_last_ts_ms = _safe_int(
        source.get("capitalTruthLedgerLastTsMs")
        or source.get("capital_truth_ledger_last_ts_ms")
        or _safe_dict(truth.get("ledger")).get("last_ts_ms")
    )
    age_ms = _safe_int(source.get("capitalTruthAgeMs") or source.get("capital_truth_age_ms"))

    recovery_status = _pick_text(source, "recoveryStatus", "recovery_status")
    if not recovery_status:
        recovery_status = (
            "capital_truth_restore_required"
            if reason_codes or freshness_class == "stale"
            else "ready"
        )
    recovery_ready = bool(
        source.get(
            "recoveryReady",
            source.get(
                "recovery_ready",
                recovery_status == "ready" and not reason_codes and freshness_class != "stale",
            ),
        )
    )
    recovery_reason_codes = _unique_strings(
        list(source.get("recoveryReasonCodes") or source.get("recovery_reason_codes") or [])
    )
    if not recovery_reason_codes and recovery_status != "ready":
        recovery_reason_codes = list(reason_codes) if reason_codes else list(freshness_reason_codes)
    recovery_reason_code = _pick_text(source, "recoveryReasonCode", "recovery_reason_code")
    if not recovery_reason_code:
        recovery_reason_code = recovery_reason_codes[0] if recovery_reason_codes else "ok"
    if recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    recovery_next_action = _pick_text(source, "recoveryNextAction", "recovery_next_action")
    if not recovery_next_action:
        if freshness_reason_codes and not reason_codes:
            recovery_next_action = "refresh_capital_truth_snapshot"
        elif recovery_reason_codes:
            recovery_next_action = "restore_capital_truth"

    recovery_freshness_class = _pick_text(
        source, "recoveryFreshnessClass", "recovery_freshness_class"
    )
    if not recovery_freshness_class:
        recovery_freshness_class = freshness_class if recovery_status != "ready" else "current"
    recovery_freshness_reason_codes = _unique_strings(
        list(
            source.get("recoveryFreshnessReasonCodes")
            or source.get("recovery_freshness_reason_codes")
            or []
        )
    )
    if not recovery_freshness_reason_codes and recovery_status != "ready":
        recovery_freshness_reason_codes = list(freshness_reason_codes)
    recovery_freshness_reason_code = _pick_text(
        source, "recoveryFreshnessReasonCode", "recovery_freshness_reason_code"
    )
    if not recovery_freshness_reason_code:
        recovery_freshness_reason_code = (
            recovery_freshness_reason_codes[0] if recovery_freshness_reason_codes else "ok"
        )
    if (
        recovery_freshness_reason_code != "ok"
        and recovery_freshness_reason_code not in recovery_freshness_reason_codes
    ):
        recovery_freshness_reason_codes = [
            recovery_freshness_reason_code,
            *recovery_freshness_reason_codes,
        ]
    recovery_freshness_next_action = _pick_text(
        source, "recoveryFreshnessNextAction", "recovery_freshness_next_action"
    )
    if not recovery_freshness_next_action and recovery_freshness_reason_codes:
        recovery_freshness_next_action = "refresh_capital_truth_snapshot"

    recovery_history_status = _pick_text(
        source,
        "capitalTruthRecoveryHistoryStatus",
        "capital_truth_recovery_history_status",
    )
    if not recovery_history_status:
        recovery_history_status = (
            "degraded" if reason_codes or freshness_class == "stale" else "steady"
        )
    degraded_since_ts_ms = _safe_int(
        source.get("capitalTruthDegradedSinceTsMs")
        or source.get("capital_truth_degraded_since_ts_ms")
    )
    recovered_at_ts_ms = _safe_int(
        source.get("capitalTruthRecoveredAtTsMs") or source.get("capital_truth_recovered_at_ts_ms")
    )
    degraded_duration_ms = _safe_int(
        source.get("capitalTruthDegradedDurationMs")
        or source.get("capital_truth_degraded_duration_ms")
    )
    degraded_count = _safe_int(
        source.get("capitalTruthDegradedCount") or source.get("capital_truth_degraded_count")
    )
    last_healthy_ts_ms = _safe_int(
        source.get("capitalTruthLastHealthyTsMs") or source.get("capital_truth_last_healthy_ts_ms")
    )
    recovered_recently = bool(
        source.get(
            "capitalTruthRecoveredRecently",
            source.get("capital_truth_recovered_recently", False),
        )
    )
    degradation_severity_class = _pick_text(
        source,
        "capitalTruthDegradationSeverityClass",
        "capital_truth_degradation_severity_class",
    )
    if not degradation_severity_class:
        degradation_severity_class = "stable" if recovery_history_status == "steady" else "acute"

    reliability_class = _pick_text(
        source,
        "capitalTruthReliabilityClass",
        "capital_truth_reliability_class",
    )
    if not reliability_class:
        if freshness_class == "unavailable":
            reliability_class = "unavailable"
        elif freshness_class == "unknown":
            reliability_class = "unknown"
        elif reason_codes or recovery_history_status == "degraded":
            reliability_class = "degraded"
        elif freshness_class == "stale":
            reliability_class = "fragile"
        elif freshness_class == "aging":
            reliability_class = "cautious"
        else:
            reliability_class = "stable"
    reliability_reason_codes = _unique_strings(
        list(
            source.get("capitalTruthReliabilityReasonCodes")
            or source.get("capital_truth_reliability_reason_codes")
            or []
        )
    )
    if not reliability_reason_codes:
        reliability_reason_codes = _unique_strings(
            [
                *(
                    [f"capital_truth_reliability_{reliability_class}"]
                    if reliability_class != "stable"
                    else []
                ),
                *reason_codes,
                *freshness_reason_codes,
            ]
        )
    reliability_reason_code = _pick_text(
        source,
        "capitalTruthReliabilityReasonCode",
        "capital_truth_reliability_reason_code",
    )
    if not reliability_reason_code:
        reliability_reason_code = reliability_reason_codes[0] if reliability_reason_codes else "ok"
    if reliability_reason_code != "ok" and reliability_reason_code not in reliability_reason_codes:
        reliability_reason_codes = [reliability_reason_code, *reliability_reason_codes]
    recovered_fragile = bool(
        source.get(
            "capitalTruthRecoveredFragile",
            source.get("capital_truth_recovered_fragile", False),
        )
    )

    next_action = _pick_text(source, "suggestedNextAction", "suggested_next_action")
    if not next_action:
        if freshness_reason_codes and not reason_codes:
            next_action = "refresh_capital_truth_snapshot"
        elif reason_codes:
            next_action = "restore_capital_truth"

    blocked = bool(reason_codes or recovery_status != "ready" or freshness_class == "stale")
    degraded = bool(
        blocked
        or freshness_class == "aging"
        or reliability_class not in {"stable", "ok"}
        or recovery_history_status in {"degraded", "blocked", "recovered"}
    )

    contract_reason_code = (
        reason_code
        if reason_code != "ok"
        else (
            recovery_reason_code
            if recovery_reason_code != "ok"
            else (
                freshness_reason_code
                if freshness_reason_code != "ok"
                else (reliability_reason_code if reliability_reason_code != "ok" else "ok")
            )
        )
    )

    return {
        "status": status,
        "reasonCode": reason_code,
        "reasonCodes": reason_codes,
        "freshnessClass": freshness_class,
        "freshnessReasonCode": freshness_reason_code,
        "freshnessReasonCodes": freshness_reason_codes,
        "observedTsMs": observed_ts_ms,
        "ledgerLastTsMs": ledger_last_ts_ms,
        "ageMs": age_ms,
        "recoveryStatus": recovery_status,
        "recoveryReady": recovery_ready,
        "recoveryReasonCode": recovery_reason_code,
        "recoveryReasonCodes": recovery_reason_codes,
        "recoveryNextAction": recovery_next_action,
        "recoveryFreshnessClass": recovery_freshness_class,
        "recoveryFreshnessReasonCode": recovery_freshness_reason_code,
        "recoveryFreshnessReasonCodes": recovery_freshness_reason_codes,
        "recoveryFreshnessNextAction": recovery_freshness_next_action,
        "recoveryHistoryStatus": recovery_history_status,
        "degradedSinceTsMs": degraded_since_ts_ms,
        "recoveredAtTsMs": recovered_at_ts_ms,
        "degradedDurationMs": degraded_duration_ms,
        "degradedCount": degraded_count,
        "lastHealthyTsMs": last_healthy_ts_ms,
        "recoveredRecently": recovered_recently,
        "degradationSeverityClass": degradation_severity_class,
        "reliabilityClass": reliability_class,
        "reliabilityReasonCode": reliability_reason_code,
        "reliabilityReasonCodes": reliability_reason_codes,
        "recoveredFragile": recovered_fragile,
        "nextAction": next_action,
        "blocked": blocked,
        "degraded": degraded,
        "stateContract": decision_contract(
            phase="capital_truth_summary",
            reason_code=contract_reason_code,
            degraded=bool(degraded and not blocked),
            blocked=blocked,
            denied=False,
            sticky_cycle=True,
            details={
                "status": status,
                "freshnessClass": freshness_class,
                "recoveryStatus": recovery_status,
                "reliabilityClass": reliability_class,
            },
        ),
    }


def runtime_capital_truth_health(
    runtime: Any,
    *,
    capital_truth: Dict[str, Any] | None = None,
    fund_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    summary = _safe_dict(fund_summary)
    if not summary:
        getter = getattr(runtime, "fund_summary_state", None)
        if callable(getter):
            try:
                summary = _safe_dict(getter())
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                summary = {}
        if not summary:
            service = getattr(runtime, "_fund_service", None)
            getter = getattr(service, "summary", None) if service is not None else None
            if callable(getter):
                try:
                    summary = _safe_dict(getter(runtime))
                except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                    summary = {}

    health = _safe_dict(summary.get("health") or summary)
    for src_key, dst_key in (
        ("capitalTruthStatus", "capitalTruthStatus"),
        ("capitalTruthReasonCode", "capitalTruthReasonCode"),
        ("capitalTruthReasonCodes", "capitalTruthReasonCodes"),
        ("capitalTruthFreshnessClass", "capitalTruthFreshnessClass"),
        ("capitalTruthFreshnessReasonCode", "capitalTruthFreshnessReasonCode"),
        ("capitalTruthFreshnessReasonCodes", "capitalTruthFreshnessReasonCodes"),
        ("suggestedNextAction", "suggestedNextAction"),
        ("recoveryReady", "recoveryReady"),
        ("recoveryStatus", "recoveryStatus"),
        ("recoveryReasonCode", "recoveryReasonCode"),
        ("recoveryReasonCodes", "recoveryReasonCodes"),
        ("recoveryNextAction", "recoveryNextAction"),
        ("capitalTruthRecoveryHistoryStatus", "capitalTruthRecoveryHistoryStatus"),
        ("capitalTruthReliabilityClass", "capitalTruthReliabilityClass"),
        ("capitalTruthReliabilityReasonCode", "capitalTruthReliabilityReasonCode"),
        ("capitalTruthReliabilityReasonCodes", "capitalTruthReliabilityReasonCodes"),
    ):
        if dst_key not in health and summary.get(src_key) not in (None, ""):
            health[dst_key] = summary.get(src_key)

    truth = _safe_dict(capital_truth)
    needs_canonical_truth = not truth or not any(
        key in truth for key in ("status", "reason_code", "reason_codes", "ledger", "ts_ms")
    )
    canonical_truth: Dict[str, Any] = {}
    if needs_canonical_truth:
        getter = getattr(runtime, "capital_truth_state", None)
        if callable(getter):
            try:
                canonical_truth = _safe_dict(getter())
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                canonical_truth = {}
        if not canonical_truth:
            getter = getattr(runtime, "capital_truth", None)
            if callable(getter):
                try:
                    candidate = getter()
                    canonical_truth = _safe_dict(
                        candidate
                        if isinstance(candidate, dict)
                        else getattr(candidate, "capital_summary", None)
                    )
                    if isinstance(candidate, dict) and candidate:
                        canonical_truth = _safe_dict(candidate)
                except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                    canonical_truth = {}
    if canonical_truth:
        merged_truth = dict(canonical_truth)
        merged_truth.update(truth)
        truth = merged_truth

    return build_capital_truth_health_view(health, capital_truth=truth)
