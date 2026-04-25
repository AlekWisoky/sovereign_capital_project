from __future__ import annotations

from typing import Any, Dict, List

from ..fund_os.family_readiness import build_family_readiness
from ..fund_os.launch_modes import DEFAULT_ACTIVATION_ORDER
from ..strategies.families import CATALOG
from ..jsonsafe import to_json_safe
from .control_state import unavailable_state


def family_hardening_unavailable_summary(family: str | None = None) -> Dict[str, Any]:
    reason_code = "family_hardening_service_unavailable"
    if family:
        payload = unavailable_state(reason_code, extra={"family": str(family)})
    else:
        payload = unavailable_state(reason_code, extra={"items": []})
    reliability_reason = "family_hardening_reliability_unavailable"
    payload.update(
        {
            "reason_codes": [reason_code],
            "recovery_ready": False,
            "recovery_status": "family_hardening_restore_required",
            "recovery_reason_code": reason_code,
            "recovery_reason_codes": [reason_code],
            "recovery_next_action": "restore_family_hardening",
            "recovery_history_component": "family_hardening",
            "recovery_history_status": "degraded",
            "recovery_degraded_since_ts_ms": 0,
            "recovery_recovered_at_ts_ms": 0,
            "recovery_degraded_duration_ms": 0,
            "recovery_degraded_count": 0,
            "recovery_last_healthy_ts_ms": 0,
            "recovery_recovered_recently": False,
            "recovery_degradation_severity_class": "unavailable",
            "recovery_reliability_class": "unavailable",
            "recovery_reliability_reason_code": reliability_reason,
            "recovery_reliability_reason_codes": [reliability_reason],
            "recovery_recovered_fragile": False,
            "family_hardening_reason_codes": [reason_code],
            "family_hardening_recovery_history_status": "degraded",
            "family_hardening_degraded_since_ts_ms": 0,
            "family_hardening_recovered_at_ts_ms": 0,
            "family_hardening_degraded_duration_ms": 0,
            "family_hardening_degraded_count": 0,
            "family_hardening_last_healthy_ts_ms": 0,
            "family_hardening_recovered_recently": False,
            "family_hardening_degradation_severity_class": "unavailable",
            "family_hardening_reliability_class": "unavailable",
            "family_hardening_reliability_reason_code": reliability_reason,
            "family_hardening_reliability_reason_codes": [reliability_reason],
            "family_hardening_recovered_fragile": False,
            "blocked_non_core_family_count": 0,
            "degraded_non_core_family_count": 0,
        }
    )
    return payload


class FamilyHardeningService:
    """Uniform institutional hardening view for non-core families."""

    _CAPITAL_REASON_CODES = {
        "family_cap_zero",
        "family_cap_unknown",
        "capital_not_ready",
        "drawdown_gate",
    }
    _TREASURY_REASON_CODES = _CAPITAL_REASON_CODES | {"internal_prime_not_ready"}
    _GOVERNANCE_BLOCKING_STATES = {"quarantined", "disabled"}

    @staticmethod
    def _context(runtime: Any) -> Dict[str, Any]:
        stage = "internal_capital"
        launch = getattr(runtime, "_launch_service", None)
        if launch is not None and hasattr(launch, "summary"):
            try:
                summary = launch.summary(runtime) or {}
                stage = str((summary.get("profile") or {}).get("mode") or stage)
            except (AttributeError, KeyError, TypeError, ValueError):
                stage = "internal_capital"
        fund_summary = (
            runtime.fund_summary_state() if hasattr(runtime, "fund_summary_state") else {}
        )
        return {
            "stage": str(
                (
                    (fund_summary.get("health") or fund_summary).get("fundStage")
                    if isinstance(fund_summary, dict)
                    else "internal_capital"
                )
                or "internal_capital"
            ),
            "scorecards": (
                runtime.strategy_scorecards_state()
                if hasattr(runtime, "strategy_scorecards_state")
                else {"families": []}
            ),
            "engine_state": runtime.engine_state() if hasattr(runtime, "engine_state") else {},
            "telemetry": (
                runtime.telemetry_summary() if hasattr(runtime, "telemetry_summary") else {}
            ),
            "calibration": (
                runtime.execution_calibration_state()
                if hasattr(runtime, "execution_calibration_state")
                else {}
            ),
            "fund_summary": (
                fund_summary.get("health")
                if isinstance(fund_summary, dict) and isinstance(fund_summary.get("health"), dict)
                else fund_summary
            ),
            "active_families": list(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "active_families",
                    [],
                )
                or []
            ),
            "family_states": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "family_states",
                    {},
                )
                or {}
            ),
            "exploration_budget": dict(
                getattr(
                    getattr(getattr(runtime, "_launch_rollout", None), "profile", None),
                    "exploration_budget",
                    {},
                )
                or {}
            ),
            "capital_state": (
                runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
            ),
        }

    @staticmethod
    def _explanation(readiness: Dict[str, Any]) -> Dict[str, Any]:
        reasons = list(readiness.get("blockers") or readiness.get("reasons") or [])
        execution_reasons = list(readiness.get("executionReasons") or [])
        capital_truth_reason_codes = [
            str(x) for x in list(readiness.get("capitalTruthReasonCodes") or []) if str(x)
        ]
        internal_prime_reason_codes = [
            str(x) for x in list(readiness.get("internalPrimeReasonCodes") or []) if str(x)
        ]
        receipt_outcome_truth_reason_codes = [
            str(x) for x in list(readiness.get("receiptOutcomeTruthReasonCodes") or []) if str(x)
        ]
        global_execution_reason_codes = [
            str(x) for x in list(readiness.get("globalExecutionReasonCodes") or []) if str(x)
        ]
        recovery_reason_codes = [
            str(x) for x in list(readiness.get("recoveryReasonCodes") or []) if str(x)
        ]
        recovery_reason_code = str(
            readiness.get("recoveryReasonCode")
            or (recovery_reason_codes[0] if recovery_reason_codes else "ok")
        )
        if recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
            recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
        return {
            "status": str(readiness.get("status") or "blocked"),
            "reason_code": str(
                reasons[0] if reasons else ("eligible" if readiness.get("ready") else "not_ready")
            ),
            "reasons": reasons,
            "capital_truth_reason_codes": capital_truth_reason_codes,
            "receipt_outcome_truth_reason_codes": receipt_outcome_truth_reason_codes,
            "global_execution_reason_codes": global_execution_reason_codes,
            "internal_prime_reason_codes": internal_prime_reason_codes,
            "execution_reason_codes": execution_reasons,
            "recovery_ready": bool(
                readiness.get(
                    "recoveryReady", recovery_reason_code == "ok" and not recovery_reason_codes
                )
            ),
            "recovery_status": str(
                readiness.get("recoveryStatus")
                or ("ready" if recovery_reason_code == "ok" else "degraded")
            ),
            "recovery_reason_code": recovery_reason_code,
            "recovery_reason_codes": recovery_reason_codes,
            "recovery_next_action": str(
                readiness.get("recoveryNextAction") or readiness.get("suggestedNextAction") or ""
            ),
            "recovery_history_component": str(readiness.get("recoveryHistoryComponent") or ""),
            "recovery_history_status": str(
                readiness.get("recoveryHistoryStatus")
                or ("ready" if recovery_reason_code == "ok" else "degraded")
            ),
            "recovery_degraded_since_ts_ms": int(readiness.get("recoveryDegradedSinceTsMs") or 0),
            "recovery_recovered_at_ts_ms": int(readiness.get("recoveryRecoveredAtTsMs") or 0),
            "recovery_degraded_duration_ms": int(readiness.get("recoveryDegradedDurationMs") or 0),
            "recovery_degraded_count": int(readiness.get("recoveryDegradedCount") or 0),
            "recovery_last_healthy_ts_ms": int(readiness.get("recoveryLastHealthyTsMs") or 0),
            "recovery_recovered_recently": bool(readiness.get("recoveryRecoveredRecently", False)),
            "recovery_degradation_severity_class": str(
                readiness.get("recoveryDegradationSeverityClass") or "stable"
            ),
            "capital_truth_reliability_class": str(
                readiness.get("capitalTruthReliabilityClass") or "stable"
            ),
            "capital_truth_reliability_reason_code": str(
                readiness.get("capitalTruthReliabilityReasonCode") or "ok"
            ),
            "capital_truth_reliability_reason_codes": list(
                readiness.get("capitalTruthReliabilityReasonCodes") or []
            ),
            "capital_truth_recovered_fragile": bool(
                readiness.get("capitalTruthRecoveredFragile", False)
            ),
            "receipt_outcome_truth_freshness_class": str(
                readiness.get("receiptOutcomeTruthFreshnessClass") or ""
            ),
            "receipt_outcome_truth_freshness_reason_codes": list(
                readiness.get("receiptOutcomeTruthFreshnessReasonCodes") or []
            ),
            "receipt_outcome_truth_recovery_history_status": str(
                readiness.get("receiptOutcomeTruthRecoveryHistoryStatus")
                or ("degraded" if receipt_outcome_truth_reason_codes else "steady")
            ),
            "receipt_outcome_truth_degraded_since_ts_ms": int(
                readiness.get("receiptOutcomeTruthDegradedSinceTsMs") or 0
            ),
            "receipt_outcome_truth_recovered_at_ts_ms": int(
                readiness.get("receiptOutcomeTruthRecoveredAtTsMs") or 0
            ),
            "receipt_outcome_truth_degraded_duration_ms": int(
                readiness.get("receiptOutcomeTruthDegradedDurationMs") or 0
            ),
            "receipt_outcome_truth_degraded_count": int(
                readiness.get("receiptOutcomeTruthDegradedCount") or 0
            ),
            "receipt_outcome_truth_last_healthy_ts_ms": int(
                readiness.get("receiptOutcomeTruthLastHealthyTsMs") or 0
            ),
            "receipt_outcome_truth_recovered_recently": bool(
                readiness.get("receiptOutcomeTruthRecoveredRecently", False)
            ),
            "receipt_outcome_truth_degradation_severity_class": str(
                readiness.get("receiptOutcomeTruthDegradationSeverityClass") or "stable"
            ),
            "receipt_outcome_truth_reliability_class": str(
                readiness.get("receiptOutcomeTruthReliabilityClass") or "stable"
            ),
            "receipt_outcome_truth_reliability_reason_code": str(
                readiness.get("receiptOutcomeTruthReliabilityReasonCode") or "ok"
            ),
            "receipt_outcome_truth_reliability_reason_codes": list(
                readiness.get("receiptOutcomeTruthReliabilityReasonCodes") or []
            ),
            "receipt_outcome_truth_recovered_fragile": bool(
                readiness.get("receiptOutcomeTruthRecoveredFragile", False)
            ),
            "internal_prime_reliability_class": str(
                readiness.get("internalPrimeReliabilityClass") or "stable"
            ),
            "internal_prime_reliability_reason_code": str(
                readiness.get("internalPrimeReliabilityReasonCode") or "ok"
            ),
            "internal_prime_reliability_reason_codes": list(
                readiness.get("internalPrimeReliabilityReasonCodes") or []
            ),
            "internal_prime_recovered_fragile": bool(
                readiness.get("internalPrimeRecoveredFragile", False)
            ),
            "recovery_reliability_class": str(
                readiness.get("recoveryReliabilityClass") or "stable"
            ),
            "recovery_reliability_reason_code": str(
                readiness.get("recoveryReliabilityReasonCode") or "ok"
            ),
            "recovery_reliability_reason_codes": list(
                readiness.get("recoveryReliabilityReasonCodes") or []
            ),
            "recovery_reliability_next_action": str(
                readiness.get("recoveryReliabilityNextAction")
                or readiness.get("recoveryNextAction")
                or ""
            ),
            "recovery_recovered_fragile": bool(readiness.get("recoveryRecoveredFragile", False)),
            "degraded_state": str(readiness.get("degradedState") or ""),
            "execution_mode": str(readiness.get("executionMode") or ""),
            "suggested_next_action": str(
                readiness.get("suggestedNextAction") or "continue_v1_learning"
            ),
        }

    def _controls(
        self,
        *,
        family: str,
        readiness: Dict[str, Any],
        explanation: Dict[str, Any],
        withdraw_guard_active: bool,
    ) -> Dict[str, Any]:
        reasons = [str(x) for x in list(explanation.get("reasons") or []) if str(x)]
        execution_reasons = [
            str(x) for x in list(explanation.get("execution_reason_codes") or []) if str(x)
        ]
        capital_truth_reason_codes = [
            str(x) for x in list(explanation.get("capital_truth_reason_codes") or []) if str(x)
        ]
        internal_prime_reason_codes = [
            str(x) for x in list(explanation.get("internal_prime_reason_codes") or []) if str(x)
        ]
        receipt_outcome_truth_reason_codes = [
            str(x)
            for x in list(explanation.get("receipt_outcome_truth_reason_codes") or [])
            if str(x)
        ]
        global_execution_reason_codes = [
            str(x) for x in list(explanation.get("global_execution_reason_codes") or []) if str(x)
        ]
        recovery_reason_codes = [
            str(x) for x in list(explanation.get("recovery_reason_codes") or []) if str(x)
        ]
        capital_reason_codes = [x for x in reasons if x in self._CAPITAL_REASON_CODES]
        for code in capital_truth_reason_codes + receipt_outcome_truth_reason_codes:
            if code not in capital_reason_codes:
                capital_reason_codes.append(code)
        treasury_reason_codes = [x for x in reasons if x in self._TREASURY_REASON_CODES]
        for code in (
            capital_truth_reason_codes
            + receipt_outcome_truth_reason_codes
            + internal_prime_reason_codes
        ):
            if code not in treasury_reason_codes:
                treasury_reason_codes.append(code)
        if withdraw_guard_active and family != "flash_arb":
            treasury_reason_codes.append("withdraw_guard_active")
        governance_reason_codes = []
        degraded_state = str(explanation.get("degraded_state") or "")
        if degraded_state in self._GOVERNANCE_BLOCKING_STATES:
            governance_reason_codes.append(degraded_state)
        no_trade_reason_codes = (
            reasons
            if (reasons or str(explanation.get("status") or "") in {"blocked", "quarantined"})
            else []
        )
        return {
            "admission_ready": bool(readiness.get("ready")),
            "admission_reason_codes": [] if readiness.get("ready") else reasons,
            "execution_eligible": bool(readiness.get("actualExecutionReady")),
            "execution_reason_codes": execution_reasons,
            "capital_eligible": not capital_reason_codes,
            "capital_reason_codes": capital_reason_codes,
            "family_target_pct": float(readiness.get("familyTargetPct") or 0.0),
            "treasury_eligible": not treasury_reason_codes,
            "treasury_reason_codes": treasury_reason_codes,
            "capital_truth_reason_codes": capital_truth_reason_codes,
            "receipt_outcome_truth_reason_codes": receipt_outcome_truth_reason_codes,
            "global_execution_reason_codes": global_execution_reason_codes,
            "internal_prime_reason_codes": internal_prime_reason_codes,
            "recovery_ready": bool(explanation.get("recovery_ready", not recovery_reason_codes)),
            "recovery_status": str(
                explanation.get("recovery_status")
                or ("ready" if not recovery_reason_codes else "degraded")
            ),
            "recovery_reason_code": str(
                explanation.get("recovery_reason_code")
                or (recovery_reason_codes[0] if recovery_reason_codes else "ok")
            ),
            "recovery_reason_codes": recovery_reason_codes,
            "recovery_next_action": str(
                explanation.get("recovery_next_action")
                or explanation.get("suggested_next_action")
                or ""
            ),
            "recovery_history_component": str(explanation.get("recovery_history_component") or ""),
            "recovery_history_status": str(
                explanation.get("recovery_history_status")
                or ("ready" if not recovery_reason_codes else "degraded")
            ),
            "recovery_degraded_since_ts_ms": int(
                explanation.get("recovery_degraded_since_ts_ms") or 0
            ),
            "recovery_recovered_at_ts_ms": int(explanation.get("recovery_recovered_at_ts_ms") or 0),
            "recovery_degraded_duration_ms": int(
                explanation.get("recovery_degraded_duration_ms") or 0
            ),
            "recovery_degraded_count": int(explanation.get("recovery_degraded_count") or 0),
            "recovery_last_healthy_ts_ms": int(explanation.get("recovery_last_healthy_ts_ms") or 0),
            "recovery_recovered_recently": bool(
                explanation.get("recovery_recovered_recently", False)
            ),
            "recovery_degradation_severity_class": str(
                explanation.get("recovery_degradation_severity_class") or "stable"
            ),
            "capital_truth_reliability_class": str(
                explanation.get("capital_truth_reliability_class") or "stable"
            ),
            "capital_truth_reliability_reason_code": str(
                explanation.get("capital_truth_reliability_reason_code") or "ok"
            ),
            "capital_truth_reliability_reason_codes": list(
                explanation.get("capital_truth_reliability_reason_codes") or []
            ),
            "capital_truth_recovered_fragile": bool(
                explanation.get("capital_truth_recovered_fragile", False)
            ),
            "receipt_outcome_truth_freshness_class": str(
                explanation.get("receipt_outcome_truth_freshness_class") or ""
            ),
            "receipt_outcome_truth_freshness_reason_codes": list(
                explanation.get("receipt_outcome_truth_freshness_reason_codes") or []
            ),
            "receipt_outcome_truth_recovery_history_status": str(
                explanation.get("receipt_outcome_truth_recovery_history_status")
                or ("degraded" if receipt_outcome_truth_reason_codes else "steady")
            ),
            "receipt_outcome_truth_degraded_since_ts_ms": int(
                explanation.get("receipt_outcome_truth_degraded_since_ts_ms") or 0
            ),
            "receipt_outcome_truth_recovered_at_ts_ms": int(
                explanation.get("receipt_outcome_truth_recovered_at_ts_ms") or 0
            ),
            "receipt_outcome_truth_degraded_duration_ms": int(
                explanation.get("receipt_outcome_truth_degraded_duration_ms") or 0
            ),
            "receipt_outcome_truth_degraded_count": int(
                explanation.get("receipt_outcome_truth_degraded_count") or 0
            ),
            "receipt_outcome_truth_last_healthy_ts_ms": int(
                explanation.get("receipt_outcome_truth_last_healthy_ts_ms") or 0
            ),
            "receipt_outcome_truth_recovered_recently": bool(
                explanation.get("receipt_outcome_truth_recovered_recently", False)
            ),
            "receipt_outcome_truth_degradation_severity_class": str(
                explanation.get("receipt_outcome_truth_degradation_severity_class") or "stable"
            ),
            "receipt_outcome_truth_reliability_class": str(
                explanation.get("receipt_outcome_truth_reliability_class") or "stable"
            ),
            "receipt_outcome_truth_reliability_reason_code": str(
                explanation.get("receipt_outcome_truth_reliability_reason_code") or "ok"
            ),
            "receipt_outcome_truth_reliability_reason_codes": list(
                explanation.get("receipt_outcome_truth_reliability_reason_codes") or []
            ),
            "receipt_outcome_truth_recovered_fragile": bool(
                explanation.get("receipt_outcome_truth_recovered_fragile", False)
            ),
            "internal_prime_reliability_class": str(
                explanation.get("internal_prime_reliability_class") or "stable"
            ),
            "internal_prime_reliability_reason_code": str(
                explanation.get("internal_prime_reliability_reason_code") or "ok"
            ),
            "internal_prime_reliability_reason_codes": list(
                explanation.get("internal_prime_reliability_reason_codes") or []
            ),
            "internal_prime_recovered_fragile": bool(
                explanation.get("internal_prime_recovered_fragile", False)
            ),
            "recovery_reliability_class": str(
                explanation.get("recovery_reliability_class") or "stable"
            ),
            "recovery_reliability_reason_code": str(
                explanation.get("recovery_reliability_reason_code") or "ok"
            ),
            "recovery_reliability_reason_codes": list(
                explanation.get("recovery_reliability_reason_codes") or []
            ),
            "recovery_reliability_next_action": str(
                explanation.get("recovery_reliability_next_action")
                or explanation.get("recovery_next_action")
                or ""
            ),
            "recovery_recovered_fragile": bool(
                explanation.get("recovery_recovered_fragile", False)
            ),
            "governance_eligible": not governance_reason_codes,
            "governance_reason_codes": governance_reason_codes,
            "degraded": str(explanation.get("status") or "") in {"degraded", "quarantined"},
            "no_trade": bool(no_trade_reason_codes),
            "no_trade_reason_codes": no_trade_reason_codes,
            "operator_visible": True,
            "withdraw_guard_active": bool(withdraw_guard_active and family != "flash_arb"),
        }

    @staticmethod
    def _unique_strings(values: List[str]) -> List[str]:
        out: List[str] = []
        for value in values:
            value_s = str(value or "")
            if value_s and value_s not in out:
                out.append(value_s)
        return out

    @classmethod
    def _summary_payload(cls, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        non_core = [item for item in items if not bool(item.get("core"))]
        blocked = [
            item for item in non_core if bool(((item.get("controls") or {}).get("no_trade")))
        ]
        degraded = [
            item for item in non_core if bool(((item.get("controls") or {}).get("degraded")))
        ]

        affected: List[Dict[str, Any]] = []
        reason_codes: List[str] = []
        reliability_reason_codes: List[str] = []
        reliability_rank = {"stable": 0, "fragile": 1, "degraded": 2, "unavailable": 3}
        selected_reliability_class = "stable"
        selected_recovery: Dict[str, Any] = {}
        recovered_fragile = False

        for item in non_core:
            readiness = dict(item.get("readiness") or {})
            controls = dict(item.get("controls") or {})
            status = str(readiness.get("familyHardeningStatus") or "ok")
            codes = cls._unique_strings(
                [str(x) for x in list(readiness.get("familyHardeningReasonCodes") or []) if str(x)]
            )
            if status != "ok" and not codes:
                codes = [
                    (
                        "family_hardening_service_unavailable"
                        if status == "unavailable"
                        else "family_hardening_rebuild_required"
                    )
                ]
            rel_class = str(
                readiness.get("familyHardeningReliabilityClass")
                or controls.get("recovery_reliability_class")
                or (
                    "unavailable"
                    if status == "unavailable"
                    else ("degraded" if codes else "stable")
                )
            )
            rel_codes = cls._unique_strings(
                [
                    str(x)
                    for x in list(readiness.get("familyHardeningReliabilityReasonCodes") or [])
                    if str(x)
                ]
                + [
                    str(x)
                    for x in list(controls.get("recovery_reliability_reason_codes") or [])
                    if str(x)
                ]
            )
            rel_code = str(
                readiness.get("familyHardeningReliabilityReasonCode")
                or controls.get("recovery_reliability_reason_code")
                or (f"family_hardening_reliability_{rel_class}" if rel_class != "stable" else "ok")
            )
            if rel_code != "ok" and rel_code not in rel_codes:
                rel_codes = [rel_code, *rel_codes]
            history_status = str(
                readiness.get("familyHardeningRecoveryHistoryStatus")
                or controls.get("recovery_history_status")
                or ("degraded" if codes else "ready")
            )
            history_degraded_since_ts_ms = int(
                readiness.get("familyHardeningDegradedSinceTsMs")
                or controls.get("recovery_degraded_since_ts_ms")
                or 0
            )
            history_recovered_at_ts_ms = int(
                readiness.get("familyHardeningRecoveredAtTsMs")
                or controls.get("recovery_recovered_at_ts_ms")
                or 0
            )
            history_degraded_duration_ms = int(
                readiness.get("familyHardeningDegradedDurationMs")
                or controls.get("recovery_degraded_duration_ms")
                or 0
            )
            history_degraded_count = int(
                readiness.get("familyHardeningDegradedCount")
                or controls.get("recovery_degraded_count")
                or 0
            )
            history_last_healthy_ts_ms = int(
                readiness.get("familyHardeningLastHealthyTsMs")
                or controls.get("recovery_last_healthy_ts_ms")
                or 0
            )
            history_recovered_recently = bool(
                readiness.get("familyHardeningRecoveredRecently", False)
                or controls.get("recovery_recovered_recently", False)
            )
            history_degradation_severity_class = str(
                readiness.get("familyHardeningDegradationSeverityClass")
                or controls.get("recovery_degradation_severity_class")
                or (
                    "recovering"
                    if history_status == "recovered" and history_recovered_recently
                    else ("stable" if history_status in {"steady", "ready"} else "acute")
                )
            )
            recovered_fragile = recovered_fragile or bool(
                readiness.get("familyHardeningRecoveredFragile", False)
                or controls.get("recovery_recovered_fragile", False)
            )
            receipt_codes = cls._unique_strings(
                [
                    str(x)
                    for x in list(readiness.get("receiptOutcomeTruthReasonCodes") or [])
                    if str(x)
                ]
                + [
                    str(x)
                    for x in list(controls.get("receipt_outcome_truth_reason_codes") or [])
                    if str(x)
                ]
            )
            include_entry = bool(
                status != "ok"
                or codes
                or receipt_codes
                or rel_class != "stable"
                or recovered_fragile
                or history_status in {"degraded", "recovered"}
                or str(controls.get("recovery_history_component") or "") == "receipt_outcome_truth"
                or str(readiness.get("recoveryHistoryComponent") or "") == "receipt_outcome_truth"
                or str(controls.get("recovery_status") or readiness.get("recoveryStatus") or "")
                == "capital_truth_restore_required"
            )
            if not include_entry:
                continue
            summary_codes = list(codes)
            if not summary_codes and receipt_codes:
                summary_codes = list(receipt_codes)
            if not summary_codes and rel_class != "stable":
                summary_codes = list(rel_codes)
            for code in summary_codes:
                if code not in reason_codes:
                    reason_codes.append(code)
            affected.append(
                {
                    "item": item,
                    "readiness": readiness,
                    "controls": controls,
                    "status": status,
                    "codes": summary_codes,
                    "raw_codes": codes,
                    "receipt_codes": receipt_codes,
                    "rel_class": rel_class,
                    "rel_codes": rel_codes,
                    "history_status": history_status,
                    "history_degraded_since_ts_ms": history_degraded_since_ts_ms,
                    "history_recovered_at_ts_ms": history_recovered_at_ts_ms,
                    "history_degraded_duration_ms": history_degraded_duration_ms,
                    "history_degraded_count": history_degraded_count,
                    "history_last_healthy_ts_ms": history_last_healthy_ts_ms,
                    "history_recovered_recently": history_recovered_recently,
                    "history_degradation_severity_class": history_degradation_severity_class,
                    "recovered_fragile": recovered_fragile,
                }
            )
            for code in rel_codes:
                if code not in reliability_reason_codes:
                    reliability_reason_codes.append(code)
            if reliability_rank.get(rel_class, 0) > reliability_rank.get(
                selected_reliability_class, 0
            ):
                selected_reliability_class = rel_class
            if (
                not selected_recovery
                or status == "unavailable"
                or rel_class == "unavailable"
                or (
                    selected_recovery.get("history_status") not in {"degraded", "recovered"}
                    and history_status in {"degraded", "recovered"}
                )
            ):
                selected_recovery = {
                    "status": str(
                        controls.get("recovery_status")
                        or readiness.get("recoveryStatus")
                        or (
                            "family_hardening_restore_required"
                            if summary_codes
                            else ("degraded" if rel_class != "stable" else "ready")
                        )
                    ),
                    "reason_code": str(
                        controls.get("recovery_reason_code")
                        or readiness.get("recoveryReasonCode")
                        or (summary_codes[0] if summary_codes else rel_code)
                    ),
                    "reason_codes": cls._unique_strings(
                        [
                            str(x)
                            for x in list(controls.get("recovery_reason_codes") or [])
                            if str(x)
                        ]
                        + [
                            str(x)
                            for x in list(readiness.get("recoveryReasonCodes") or [])
                            if str(x)
                        ]
                        + summary_codes
                        + rel_codes
                    ),
                    "next_action": str(
                        controls.get("recovery_next_action")
                        or readiness.get("recoveryNextAction")
                        or readiness.get("suggestedNextAction")
                        or (
                            "restore_family_hardening"
                            if summary_codes
                            else (
                                "stabilize_recovery_before_rollout"
                                if rel_class != "stable" or recovered_fragile
                                else ""
                            )
                        )
                    ),
                    "history_component": str(
                        controls.get("recovery_history_component")
                        or readiness.get("recoveryHistoryComponent")
                        or "family_hardening"
                    ),
                    "history_status": history_status,
                    "history_degraded_since_ts_ms": history_degraded_since_ts_ms,
                    "history_recovered_at_ts_ms": history_recovered_at_ts_ms,
                    "history_degraded_duration_ms": history_degraded_duration_ms,
                    "history_degraded_count": history_degraded_count,
                    "history_last_healthy_ts_ms": history_last_healthy_ts_ms,
                    "history_recovered_recently": history_recovered_recently,
                    "history_degradation_severity_class": history_degradation_severity_class,
                    "ready": bool(
                        controls.get(
                            "recovery_ready", readiness.get("recoveryReady", not summary_codes)
                        )
                    )
                    and rel_class == "stable"
                    and not recovered_fragile,
                }

        if not affected:
            return {
                "ok": True,
                "status": "ok",
                "reason_code": "ok",
                "reason_codes": [],
                "recovery_ready": True,
                "recovery_status": "ready",
                "recovery_reason_code": "ok",
                "recovery_reason_codes": [],
                "recovery_next_action": "",
                "recovery_history_component": "",
                "recovery_history_status": "ready",
                "recovery_degraded_since_ts_ms": 0,
                "recovery_recovered_at_ts_ms": 0,
                "recovery_degraded_duration_ms": 0,
                "recovery_degraded_count": 0,
                "recovery_last_healthy_ts_ms": 0,
                "recovery_recovered_recently": False,
                "recovery_degradation_severity_class": "stable",
                "recovery_reliability_class": "stable",
                "recovery_reliability_reason_code": "ok",
                "recovery_reliability_reason_codes": [],
                "recovery_recovered_fragile": False,
                "family_hardening_reason_codes": [],
                "receipt_outcome_truth_reason_codes": [],
                "receipt_outcome_truth_recovery_history_status": "ready",
                "receipt_outcome_truth_degraded_since_ts_ms": 0,
                "receipt_outcome_truth_recovered_at_ts_ms": 0,
                "receipt_outcome_truth_degraded_duration_ms": 0,
                "receipt_outcome_truth_degraded_count": 0,
                "receipt_outcome_truth_last_healthy_ts_ms": 0,
                "receipt_outcome_truth_recovered_recently": False,
                "receipt_outcome_truth_degradation_severity_class": "stable",
                "receipt_outcome_truth_reliability_class": "stable",
                "receipt_outcome_truth_reliability_reason_code": "ok",
                "receipt_outcome_truth_reliability_reason_codes": [],
                "receipt_outcome_truth_recovered_fragile": False,
                "family_hardening_recovery_history_status": "ready",
                "family_hardening_degraded_since_ts_ms": 0,
                "family_hardening_recovered_at_ts_ms": 0,
                "family_hardening_degraded_duration_ms": 0,
                "family_hardening_degraded_count": 0,
                "family_hardening_last_healthy_ts_ms": 0,
                "family_hardening_recovered_recently": False,
                "family_hardening_degradation_severity_class": "stable",
                "family_hardening_reliability_class": "stable",
                "family_hardening_reliability_reason_code": "ok",
                "family_hardening_reliability_reason_codes": [],
                "family_hardening_recovered_fragile": False,
                "blocked_non_core_family_count": len(blocked),
                "degraded_non_core_family_count": len(degraded),
            }

        receipt_reason_codes = cls._unique_strings(
            [
                str(code)
                for entry in affected
                for code in list(entry.get("receipt_codes") or [])
                if str(code)
            ]
        )
        receipt_history_source = next(
            (
                entry
                for entry in affected
                if entry.get("receipt_codes")
                or str(
                    entry.get("item", {}).get("controls", {}).get("recovery_history_component")
                    or ""
                )
                == "receipt_outcome_truth"
                or str(
                    entry.get("item", {}).get("readiness", {}).get("recoveryHistoryComponent") or ""
                )
                == "receipt_outcome_truth"
            ),
            {},
        )
        receipt_controls = dict((receipt_history_source.get("item") or {}).get("controls") or {})
        receipt_readiness = dict((receipt_history_source.get("item") or {}).get("readiness") or {})
        receipt_rel_codes = cls._unique_strings(
            [
                str(x)
                for x in list(
                    receipt_controls.get("receipt_outcome_truth_reliability_reason_codes") or []
                )
                if str(x)
            ]
            + [
                str(x)
                for x in list(
                    receipt_readiness.get("receiptOutcomeTruthReliabilityReasonCodes") or []
                )
                if str(x)
            ]
        )
        receipt_rel_code = str(
            receipt_controls.get("receipt_outcome_truth_reliability_reason_code")
            or receipt_readiness.get("receiptOutcomeTruthReliabilityReasonCode")
            or (receipt_rel_codes[0] if receipt_rel_codes else "ok")
        )
        if receipt_rel_code != "ok" and receipt_rel_code not in receipt_rel_codes:
            receipt_rel_codes = [receipt_rel_code, *receipt_rel_codes]
        receipt_rel_class = str(
            receipt_controls.get("receipt_outcome_truth_reliability_class")
            or receipt_readiness.get("receiptOutcomeTruthReliabilityClass")
            or ("degraded" if receipt_reason_codes else "stable")
        )
        receipt_history_status = str(
            receipt_controls.get("receipt_outcome_truth_recovery_history_status")
            or receipt_readiness.get("receiptOutcomeTruthRecoveryHistoryStatus")
            or ("degraded" if receipt_reason_codes else "ready")
        )
        receipt_degraded_since_ts_ms = int(
            receipt_controls.get("receipt_outcome_truth_degraded_since_ts_ms")
            or receipt_readiness.get("receiptOutcomeTruthDegradedSinceTsMs")
            or 0
        )
        receipt_recovered_at_ts_ms = int(
            receipt_controls.get("receipt_outcome_truth_recovered_at_ts_ms")
            or receipt_readiness.get("receiptOutcomeTruthRecoveredAtTsMs")
            or 0
        )
        receipt_degraded_duration_ms = int(
            receipt_controls.get("receipt_outcome_truth_degraded_duration_ms")
            or receipt_readiness.get("receiptOutcomeTruthDegradedDurationMs")
            or 0
        )
        receipt_degraded_count = int(
            receipt_controls.get("receipt_outcome_truth_degraded_count")
            or receipt_readiness.get("receiptOutcomeTruthDegradedCount")
            or 0
        )
        receipt_last_healthy_ts_ms = int(
            receipt_controls.get("receipt_outcome_truth_last_healthy_ts_ms")
            or receipt_readiness.get("receiptOutcomeTruthLastHealthyTsMs")
            or 0
        )
        receipt_recovered_recently = bool(
            receipt_controls.get("receipt_outcome_truth_recovered_recently", False)
            or receipt_readiness.get("receiptOutcomeTruthRecoveredRecently", False)
        )
        receipt_degradation_severity_class = str(
            receipt_controls.get("receipt_outcome_truth_degradation_severity_class")
            or receipt_readiness.get("receiptOutcomeTruthDegradationSeverityClass")
            or (
                "recovering"
                if receipt_history_status == "recovered" and receipt_recovered_recently
                else ("stable" if receipt_history_status in {"ready", "steady"} else "acute")
            )
        )
        receipt_recovered_fragile = bool(
            receipt_controls.get("receipt_outcome_truth_recovered_fragile", False)
            or receipt_readiness.get("receiptOutcomeTruthRecoveredFragile", False)
        )

        status = (
            "unavailable"
            if any(
                entry["status"] == "unavailable"
                or "family_hardening_service_unavailable" in set(entry.get("codes") or [])
                or "family_hardening_reliability_unavailable" in set(entry.get("rel_codes") or [])
                for entry in affected
            )
            else "degraded"
        )
        reason_code = (
            reason_codes[0]
            if reason_codes
            else (
                "family_hardening_service_unavailable"
                if status == "unavailable"
                else "family_hardening_rebuild_required"
            )
        )
        if reason_code != "ok" and reason_code not in reason_codes:
            reason_codes = [reason_code, *reason_codes]
        recovery_reason_code = str(selected_recovery.get("reason_code") or reason_code)
        recovery_reason_codes = cls._unique_strings(
            [
                recovery_reason_code,
                *list(selected_recovery.get("reason_codes") or []),
                *reason_codes,
            ]
        )
        recovery_status = str(
            selected_recovery.get("status")
            or (
                "family_hardening_restore_required"
                if reason_codes
                else ("degraded" if selected_reliability_class != "stable" else "ready")
            )
        )
        fragility_only = bool(
            selected_reliability_class != "stable"
            and not any(affected_entry.get("raw_codes") for affected_entry in affected)
        )
        if recovery_status == "ready" and reason_codes:
            recovery_status = "family_hardening_restore_required"
        elif recovery_status == "ready" and selected_reliability_class != "stable":
            recovery_status = "degraded"
        if fragility_only and recovery_status == "family_hardening_restore_required":
            recovery_status = "degraded"
        recovery_next_action = str(
            selected_recovery.get("next_action")
            or (
                "restore_family_hardening"
                if reason_codes
                else (
                    "stabilize_recovery_before_rollout"
                    if selected_reliability_class != "stable" or recovered_fragile
                    else ""
                )
            )
        )
        recovery_history_component = str(
            selected_recovery.get("history_component") or ("family_hardening" if affected else "")
        )
        recovery_history_status = str(
            selected_recovery.get("history_status")
            or ("degraded" if reason_codes else ("recovered" if recovered_fragile else "ready"))
        )
        recovery_ready = bool(selected_recovery.get("ready", not reason_codes)) and not bool(
            reason_codes or selected_reliability_class != "stable" or recovered_fragile
        )
        recovery_degraded_since_ts_ms = int(
            selected_recovery.get("history_degraded_since_ts_ms") or 0
        )
        recovery_recovered_at_ts_ms = int(selected_recovery.get("history_recovered_at_ts_ms") or 0)
        recovery_degraded_duration_ms = int(
            selected_recovery.get("history_degraded_duration_ms") or 0
        )
        recovery_degraded_count = int(selected_recovery.get("history_degraded_count") or 0)
        recovery_last_healthy_ts_ms = int(selected_recovery.get("history_last_healthy_ts_ms") or 0)
        recovery_recovered_recently = bool(
            selected_recovery.get("history_recovered_recently", False)
        )
        recovery_degradation_severity_class = str(
            selected_recovery.get("history_degradation_severity_class")
            or (
                "recovering"
                if recovery_history_status == "recovered" and recovery_recovered_recently
                else ("stable" if recovery_history_status in {"ready", "steady"} else "acute")
            )
        )
        reliability_reason_code = (
            reliability_reason_codes[0]
            if reliability_reason_codes
            else (
                f"family_hardening_reliability_{selected_reliability_class}"
                if selected_reliability_class != "stable"
                else "ok"
            )
        )
        if (
            reliability_reason_code != "ok"
            and reliability_reason_code not in reliability_reason_codes
        ):
            reliability_reason_codes = [reliability_reason_code, *reliability_reason_codes]
        if fragility_only:
            if recovery_reason_code in {"", "ok"}:
                recovery_reason_code = reliability_reason_code
            recovery_reason_codes = cls._unique_strings(
                [recovery_reason_code, *recovery_reason_codes, *reliability_reason_codes]
            )
            if recovery_next_action in {
                "",
                "continue_v1_learning",
                "activate_family",
                "accumulate_telemetry",
            }:
                recovery_next_action = "stabilize_recovery_before_rollout"
        return {
            "ok": status != "unavailable",
            "status": status,
            "reason_code": reason_code,
            "reason_codes": reason_codes,
            "recovery_ready": recovery_ready,
            "recovery_status": recovery_status,
            "recovery_reason_code": recovery_reason_code,
            "recovery_reason_codes": recovery_reason_codes,
            "recovery_next_action": recovery_next_action,
            "recovery_history_component": recovery_history_component,
            "recovery_history_status": recovery_history_status,
            "recovery_degraded_since_ts_ms": recovery_degraded_since_ts_ms,
            "recovery_recovered_at_ts_ms": recovery_recovered_at_ts_ms,
            "recovery_degraded_duration_ms": recovery_degraded_duration_ms,
            "recovery_degraded_count": recovery_degraded_count,
            "recovery_last_healthy_ts_ms": recovery_last_healthy_ts_ms,
            "recovery_recovered_recently": recovery_recovered_recently,
            "recovery_degradation_severity_class": recovery_degradation_severity_class,
            "recovery_reliability_class": selected_reliability_class,
            "recovery_reliability_reason_code": reliability_reason_code,
            "recovery_reliability_reason_codes": reliability_reason_codes,
            "recovery_recovered_fragile": recovered_fragile,
            "family_hardening_reason_codes": reason_codes,
            "receipt_outcome_truth_reason_codes": receipt_reason_codes,
            "receipt_outcome_truth_recovery_history_status": receipt_history_status,
            "receipt_outcome_truth_degraded_since_ts_ms": receipt_degraded_since_ts_ms,
            "receipt_outcome_truth_recovered_at_ts_ms": receipt_recovered_at_ts_ms,
            "receipt_outcome_truth_degraded_duration_ms": receipt_degraded_duration_ms,
            "receipt_outcome_truth_degraded_count": receipt_degraded_count,
            "receipt_outcome_truth_last_healthy_ts_ms": receipt_last_healthy_ts_ms,
            "receipt_outcome_truth_recovered_recently": receipt_recovered_recently,
            "receipt_outcome_truth_degradation_severity_class": receipt_degradation_severity_class,
            "receipt_outcome_truth_reliability_class": receipt_rel_class,
            "receipt_outcome_truth_reliability_reason_code": receipt_rel_code,
            "receipt_outcome_truth_reliability_reason_codes": receipt_rel_codes,
            "receipt_outcome_truth_recovered_fragile": receipt_recovered_fragile,
            "family_hardening_recovery_history_status": recovery_history_status,
            "family_hardening_degraded_since_ts_ms": recovery_degraded_since_ts_ms,
            "family_hardening_recovered_at_ts_ms": recovery_recovered_at_ts_ms,
            "family_hardening_degraded_duration_ms": recovery_degraded_duration_ms,
            "family_hardening_degraded_count": recovery_degraded_count,
            "family_hardening_last_healthy_ts_ms": recovery_last_healthy_ts_ms,
            "family_hardening_recovered_recently": recovery_recovered_recently,
            "family_hardening_degradation_severity_class": recovery_degradation_severity_class,
            "family_hardening_reliability_class": selected_reliability_class,
            "family_hardening_reliability_reason_code": reliability_reason_code,
            "family_hardening_reliability_reason_codes": reliability_reason_codes,
            "family_hardening_recovered_fragile": recovered_fragile,
            "blocked_non_core_family_count": len(blocked),
            "degraded_non_core_family_count": len(degraded),
        }

    def family_state(self, runtime: Any, family: str) -> Dict[str, Any]:
        ctx = self._context(runtime)
        fam = CATALOG.get(str(family))
        readiness = build_family_readiness(
            family=str(family),
            stage=str(ctx["stage"]),
            scorecards=dict(ctx["scorecards"]),
            engine_state=dict(ctx["engine_state"]),
            telemetry=dict(ctx["telemetry"]),
            calibration=dict(ctx["calibration"]),
            fund_summary=dict(ctx["fund_summary"]),
            active_families=list(ctx["active_families"]),
            family_states=dict(ctx["family_states"]),
            exploration_budget=dict(ctx["exploration_budget"]),
            capital_state=dict(ctx["capital_state"]),
        )
        explanation = self._explanation(readiness)
        capital_truth = (
            runtime.capital_truth_state() if hasattr(runtime, "capital_truth_state") else {}
        )
        withdraw_available = bool(((capital_truth.get("withdrawal") or {}).get("available")))
        controls = self._controls(
            family=str(family),
            readiness=readiness,
            explanation=explanation,
            withdraw_guard_active=withdraw_available,
        )
        return to_json_safe(
            {
                "family": str(family),
                "core": bool(str(family) == "flash_arb"),
                "risk_profile": str(getattr(fam, "risk_profile", "")),
                "capital_cap_pct": float(getattr(fam, "capital_cap_pct", 0.0) or 0.0),
                "enabled": str(family) in set(ctx["active_families"]),
                "readiness": readiness,
                "controls": controls,
                "explanation": explanation,
            }
        )

    @staticmethod
    def _ordered_families() -> List[str]:
        ordered: List[str] = []
        for family in list(DEFAULT_ACTIVATION_ORDER) + list(CATALOG.keys()):
            family_name = str(family or "")
            if family_name and family_name not in ordered:
                ordered.append(family_name)
        return ordered

    def summary(self, runtime: Any) -> Dict[str, Any]:
        ordered_families = self._ordered_families()
        items: List[Dict[str, Any]] = [
            self.family_state(runtime, family) for family in ordered_families
        ]
        summary = self._summary_payload(items)
        covered_families = {
            str(item.get("family") or "") for item in items if str(item.get("family") or "")
        }
        uncovered_families = [
            family for family in ordered_families if family not in covered_families
        ]
        return to_json_safe(
            {
                "canonical": True,
                "service": "family_hardening_service",
                "items": items,
                "family_catalog": ordered_families,
                "family_catalog_count": len(ordered_families),
                "covered_family_count": len(covered_families),
                "uncovered_family_count": len(uncovered_families),
                "uncovered_families": uncovered_families,
                "non_core_family_count": len(
                    [item for item in items if not bool(item.get("core"))]
                ),
                **summary,
            }
        )
