from __future__ import annotations

from typing import Any, Dict, List

from victor_ai_bot.capital_family_policy import (
    family_alias_candidates,
    resolve_family_target as resolve_canonical_family_target,
)
from .family_identity import (
    canonical_launch_family_id,
    family_alias_candidates as launch_family_alias_candidates,
    family_identity,
    is_core_launch_family,
)
from .health_states import HealthState, normalize_health_state
from .launch_acceleration import family_launch_acceleration_signal
from .launch_modes import DEFAULT_ACTIVATION_ORDER
from .mandate_registry import fund_mandate_registry


def _score_bool(ok: bool, weight: float) -> float:
    return weight if ok else 0.0


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_HEALTH_STATE_STRENGTH = {
    "": 0,
    HealthState.LIVE.value: 1,
    HealthState.CAPPED_LIVE.value: 2,
    HealthState.OBSERVE_ONLY.value: 3,
    HealthState.DEGRADED.value: 4,
    HealthState.DISABLED.value: 5,
    HealthState.QUARANTINED.value: 6,
}


def _prefer_stronger_health_state(current: str, candidate: str) -> str:
    current_s = normalize_health_state(current, default="") if current else ""
    candidate_s = normalize_health_state(candidate, default="") if candidate else ""
    return (
        candidate_s
        if _HEALTH_STATE_STRENGTH.get(candidate_s, 0) >= _HEALTH_STATE_STRENGTH.get(current_s, 0)
        else current_s
    )


def _resolve_family_row(family_rows: Dict[str, Any], family: str) -> Dict[str, Any]:
    for candidate in launch_family_alias_candidates(family):
        row = family_rows.get(candidate)
        if isinstance(row, dict):
            return dict(row)
    return {}


def _resolve_family_target(
    *, family: str, family_targets: Dict[str, Any]
) -> tuple[str, bool, float]:
    resolved_key, target, known = resolve_canonical_family_target(
        family_targets=family_targets,
        family=family,
    )
    return resolved_key, bool(known), float(target)


def _extend_unique(items: List[str], values: List[str]) -> None:
    for value in values:
        value_s = str(value or "")
        if value_s and value_s not in items:
            items.append(value_s)


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, dict) else {}


def _receipt_outcome_truth_rollout_gate(
    *,
    family: str,
    fund_summary: Dict[str, Any],
    freshness_class: str,
    freshness_reason_codes: List[str],
    reliability_class: str,
    reliability_reason_code: str,
    reliability_reason_codes: List[str],
) -> Dict[str, Any]:
    if is_core_launch_family(family):
        return {
            "ready": True,
            "reasonCodes": [],
            "nextAction": "",
        }
    summary = _safe_dict(fund_summary)
    explicit_freshness = bool(
        summary.get("receiptOutcomeTruthFreshnessClass")
        or summary.get("receiptOutcomeTruthFreshnessReasonCodes")
    )
    explicit_reliability = bool(
        summary.get("receiptOutcomeTruthReliabilityClass")
        or summary.get("receiptOutcomeTruthReliabilityReasonCode")
        or summary.get("receiptOutcomeTruthReliabilityReasonCodes")
    )
    if not explicit_freshness and not explicit_reliability:
        return {
            "ready": True,
            "reasonCodes": [],
            "nextAction": "",
        }
    reason_codes: List[str] = []
    if freshness_class not in {"current", "recent"}:
        _extend_unique(
            reason_codes,
            list(freshness_reason_codes)
            or [f"receipt_outcome_truth_freshness_{freshness_class or 'unknown'}"],
        )
    if reliability_class not in {"stable", "cautious"}:
        _extend_unique(
            reason_codes,
            list(reliability_reason_codes)
            or [
                reliability_reason_code
                or f"receipt_outcome_truth_reliability_{reliability_class or 'unknown'}"
            ],
        )
    return {
        "ready": not bool(reason_codes),
        "reasonCodes": reason_codes,
        "nextAction": "restore_receipt_outcome_truth" if reason_codes else "",
    }


def _global_execution_safety_info(fund_summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = _safe_dict(fund_summary)
    drawdown_state = _safe_dict(summary.get("drawdownState"))
    hard_stop_state = _safe_dict(drawdown_state.get("hardStop"))
    drawdown_hard_stop_active = bool(hard_stop_state.get("active", False))
    drawdown_reason_codes = [
        str(x) for x in list(hard_stop_state.get("reason_codes") or []) if str(x)
    ]
    if drawdown_hard_stop_active and not drawdown_reason_codes:
        drawdown_reason_codes = ["drawdown_hard_stop"]

    kill_switch = _safe_dict(summary.get("killSwitch"))
    kill_switch_reason_codes = [
        str(x) for x in list(kill_switch.get("reason_codes") or []) if str(x)
    ]
    suppressions = _safe_dict(kill_switch.get("suppressions"))
    kill_switch_active = bool(kill_switch.get("suppressed", False))
    for suppression in suppressions.values():
        suppression_dict = _safe_dict(suppression)
        suppression_reason_codes = [
            str(x) for x in list(suppression_dict.get("reason_codes") or []) if str(x)
        ]
        if suppression_reason_codes:
            kill_switch_active = True
            _extend_unique(kill_switch_reason_codes, suppression_reason_codes)
        elif suppression_dict:
            kill_switch_active = True
    if kill_switch_active and not kill_switch_reason_codes:
        kill_switch_reason_codes = ["kill_switch_active"]

    reason_codes: List[str] = []
    _extend_unique(reason_codes, drawdown_reason_codes)
    _extend_unique(reason_codes, kill_switch_reason_codes)
    return {
        "blocked": bool(reason_codes),
        "reason_codes": reason_codes,
        "drawdown_hard_stop_active": drawdown_hard_stop_active,
        "kill_switch_active": kill_switch_active,
    }


def _engine_entry_matches_family(family: str, entry: Dict[str, Any]) -> bool:
    opp = dict((entry or {}).get("opportunity") or {}) if isinstance(entry, dict) else {}
    candidates = [
        str(opp.get("strategy_family") or ""),
        str(opp.get("engine_type") or ""),
        str(opp.get("route_family") or ""),
    ]
    aliases = launch_family_alias_candidates(family)
    return any(
        candidate and any(alias and alias in candidate for alias in aliases)
        for candidate in candidates
    )


def _execution_readiness_signal(family: str, engine_state: Dict[str, Any]) -> Dict[str, Any]:
    if is_core_launch_family(family):
        return {
            "executionEvidencePresent": True,
            "actualExecutionReady": True,
            "executionMode": "live",
            "executionReasons": [],
        }
    items = list((engine_state or {}).get("items") or []) if isinstance(engine_state, dict) else []
    relevant = [
        entry
        for entry in items
        if isinstance(entry, dict) and _engine_entry_matches_family(family, entry)
    ]
    if not relevant:
        return {
            "executionEvidencePresent": False,
            "actualExecutionReady": False,
            "executionMode": "",
            "executionReasons": ["no_execution_evidence"],
        }

    def _rank(entry: Dict[str, Any]) -> tuple[int, float]:
        opp = dict(entry.get("opportunity") or {})
        admission = dict(entry.get("admission") or {})
        capture = dict(entry.get("capture") or {})
        mode = str(admission.get("mode") or "")
        action = str(capture.get("action") or "trade")
        mode_rank = {"live": 4, "capped_live": 3, "observe_only": 2, "disabled": 1}.get(mode, 0)
        action_rank = 0 if action == "drop" else 1
        edge = float(
            opp.get("expected_realized_profit_usd") or opp.get("expected_profit_usd") or 0.0
        )
        return (mode_rank * 10 + action_rank, edge)

    best = sorted(relevant, key=_rank, reverse=True)[0]
    opp = dict(best.get("opportunity") or {})
    admission = dict(best.get("admission") or {})
    capture = dict(best.get("capture") or {})
    mode = str(admission.get("mode") or opp.get("policy_eligibility") or "")
    capture_action = str(capture.get("action") or "trade")
    reasons: List[str] = []
    if not bool(admission.get("allowed", False)):
        reasons.append(str(admission.get("reason") or "admission_denied"))
    if mode not in {"live", "capped_live"}:
        reasons.append("execution_mode_not_live")
    if capture and capture_action == "drop":
        reasons.append(str(capture.get("drop_reason") or "capture_drop"))
    ready = (
        bool(admission.get("allowed", False))
        and mode in {"live", "capped_live"}
        and (not capture or capture_action != "drop")
    )
    return {
        "executionEvidencePresent": True,
        "actualExecutionReady": ready,
        "executionMode": mode,
        "executionReasons": reasons,
    }


def _engine_row(family: str, engine_state: Dict[str, Any]) -> Dict[str, Any]:
    active_engines = (
        list(((engine_state or {}).get("summary") or {}).get("engines") or [])
        if isinstance(engine_state, dict)
        else []
    )
    aliases = set(launch_family_alias_candidates(family))
    return next(
        (
            e
            for e in active_engines
            if str(e.get("engine_type") or e.get("engineId") or "") in aliases
        ),
        {},
    )


def build_family_readiness(
    *,
    family: str,
    stage: str,
    scorecards: Dict[str, Any],
    engine_state: Dict[str, Any],
    telemetry: Dict[str, Any],
    calibration: Dict[str, Any],
    fund_summary: Dict[str, Any],
    active_families: List[str],
    family_states: Dict[str, str] | None = None,
    exploration_budget: Dict[str, Any] | None = None,
    capital_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    requested_family = str(family or "")
    identity = family_identity(requested_family)
    family = str(identity.get("launchFamily") or requested_family)
    runtime_family = str(identity.get("runtimeFamily") or family)
    capital_family = str(identity.get("capitalFamily") or runtime_family or family)
    family_aliases = launch_family_alias_candidates(
        [requested_family, family, runtime_family, capital_family]
    )
    core_family = bool(identity.get("isCore", False))

    mandates = dict((fund_mandate_registry().get("families") or {}))
    mandate = mandates.get(family) or mandates.get(requested_family) or {}
    family_rows = {
        str(x.get("family")): x
        for x in list((scorecards or {}).get("families") or [])
        if isinstance(x, dict)
    }
    fam = _resolve_family_row(family_rows, family)
    count = int(fam.get("count") or 0)
    success = float(fam.get("executionSuccessRate") or 0.0)
    gas_eff = float(fam.get("gasEfficiency") or 0.0)
    drawdown = float(fam.get("drawdownPenalty") or 0.0)
    eng = _engine_row(family, engine_state)
    execution_signal = _execution_readiness_signal(family, engine_state)
    active_family_ids = [
        canonical_launch_family_id(str(x or "")) for x in list(active_families or []) if str(x)
    ]
    state_map = {
        canonical_launch_family_id(str(k or "")): v for k, v in dict(family_states or {}).items()
    }
    current_state = normalize_health_state(
        state_map.get(family),
        default=(HealthState.LIVE.value if core_family else HealthState.OBSERVE_ONLY.value),
    )

    cal_items = list((calibration or {}).get("items") or [])
    relevant = [
        i
        for i in cal_items
        if any(alias and alias in str(i.get("route_family") or "") for alias in family_aliases)
    ]
    route_reliability = (
        max(
            0.0,
            min(
                1.0,
                sum(float(x.get("calibration_factor") or 1.0) for x in relevant)
                / max(1, len(relevant)),
            ),
        )
        if relevant
        else 0.55
    )
    venue_reliability = float(
        (telemetry or {}).get("venueReliability")
        or (telemetry or {}).get("venue_reliability")
        or route_reliability
    )
    venue_reliability = _clip(venue_reliability, 0.0, 1.0)

    competition_raw = float(
        (fam.get("competitionPressure") or (telemetry or {}).get("competitionPressure") or 0.0)
        or 0.0
    )
    competition_pressure = _clip(competition_raw, 0.0, 1.0)
    telemetry_sufficient = count >= 5 or len(relevant) >= 1
    stage_ok = stage in list(mandate.get("stage_restrictions") or [stage])
    engine_mode = str(eng.get("mode") or "").lower()
    no_engine_disable = engine_mode not in {"disabled", "observe_only"}
    private_ready = family not in {"mev_search", "liquidation_capture"} or bool(
        (fund_summary or {}).get("privateRoutingReady", True)
    )
    interaction_ok = family == "funding_arb" or family not in active_family_ids or core_family
    capital_ready = bool((fund_summary or {}).get("capitalReady", True))
    internal_prime_ready = bool((fund_summary or {}).get("internalPrimeReady", True))
    capital_truth_reason_codes = [
        str(x) for x in list((fund_summary or {}).get("capitalTruthReasonCodes") or []) if str(x)
    ]
    receipt_outcome_truth_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("receiptOutcomeTruthReasonCodes") or [])
        if str(x)
    ]
    internal_prime_reason_codes = [
        str(x) for x in list((fund_summary or {}).get("internalPrimeReasonCodes") or []) if str(x)
    ]
    family_hardening_status = str((fund_summary or {}).get("familyHardeningStatus") or "ok")
    family_hardening_reason_codes = [
        str(x) for x in list((fund_summary or {}).get("familyHardeningReasonCodes") or []) if str(x)
    ]
    family_hardening_ready = family_hardening_status == "ok" and not family_hardening_reason_codes
    recovery_reason_codes = [
        str(x) for x in list((fund_summary or {}).get("recoveryReasonCodes") or []) if str(x)
    ]
    recovery_reason_code = str(
        (fund_summary or {}).get("recoveryReasonCode")
        or (recovery_reason_codes[0] if recovery_reason_codes else "")
    )
    if (
        recovery_reason_code
        and recovery_reason_code != "ok"
        and recovery_reason_code not in recovery_reason_codes
    ):
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    recovery_freshness_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("recoveryFreshnessReasonCodes") or [])
        if str(x)
    ]
    recovery_freshness_reason_code = str(
        (fund_summary or {}).get("recoveryFreshnessReasonCode")
        or (recovery_freshness_reason_codes[0] if recovery_freshness_reason_codes else "")
    )
    if (
        recovery_freshness_reason_code
        and recovery_freshness_reason_code != "ok"
        and recovery_freshness_reason_code not in recovery_freshness_reason_codes
    ):
        recovery_freshness_reason_codes = [
            recovery_freshness_reason_code,
            *recovery_freshness_reason_codes,
        ]
    family_targets = dict(
        ((capital_state or {}).get("capital_engine") or {}).get("family_targets") or {}
    )
    resolved_family_target_key, family_target_known, family_target = _resolve_family_target(
        family=family, family_targets=family_targets
    )
    family_target_required = bool(family_targets)
    capital_target_ready = (not family_target_required) or (
        family_target_known and family_target > 0.02
    )
    global_execution_safety = _global_execution_safety_info(fund_summary)
    global_execution_reason_codes = [
        str(x) for x in list(global_execution_safety.get("reason_codes") or []) if str(x)
    ]
    drawdown_hard_stop_active = bool(
        global_execution_safety.get("drawdown_hard_stop_active", False)
    )
    kill_switch_active = bool(global_execution_safety.get("kill_switch_active", False))
    drawdown_ok = drawdown <= float((mandate or {}).get("max_drawdown_pct") or 5.0)

    budget = dict(exploration_budget or {})
    exploration_open = float(budget.get("used_trades") or 0) < float(
        budget.get("max_trades") or 0 or 3
    )

    blockers: List[str] = []
    reasons: List[str] = []
    if not telemetry_sufficient:
        blockers.append("telemetry_insufficient")
        reasons.append("telemetry_insufficient")
    if not stage_ok:
        blockers.append("stage_restriction")
        reasons.append("stage_restriction")
    if not private_ready:
        blockers.append("private_routing_not_ready")
        reasons.append("private_routing_not_ready")
    if not interaction_ok:
        blockers.append("interaction_risk_gate")
        reasons.append("interaction_risk_gate")
    if family_target_required and not family_target_known:
        blockers.append("family_cap_unknown")
        reasons.append("family_cap_unknown")
    elif not capital_target_ready:
        blockers.append("family_cap_zero")
        reasons.append("family_cap_zero")
    if not capital_ready:
        blockers.append("capital_not_ready")
        reasons.append("capital_not_ready")
        _extend_unique(blockers, capital_truth_reason_codes)
        _extend_unique(reasons, capital_truth_reason_codes)
    if not internal_prime_ready:
        blockers.append("internal_prime_not_ready")
        reasons.append("internal_prime_not_ready")
        _extend_unique(blockers, internal_prime_reason_codes)
        _extend_unique(reasons, internal_prime_reason_codes)
    if not core_family and not family_hardening_ready:
        blockers.append("family_hardening_not_ready")
        reasons.append("family_hardening_not_ready")
        _extend_unique(blockers, family_hardening_reason_codes)
        _extend_unique(reasons, family_hardening_reason_codes)
    if global_execution_reason_codes:
        _extend_unique(blockers, global_execution_reason_codes)
        _extend_unique(reasons, global_execution_reason_codes)
    if not drawdown_ok:
        blockers.append("drawdown_gate")
        reasons.append("drawdown_gate")
    if competition_pressure >= 0.85 and family in {"flash_arb", "mev_search"}:
        blockers.append("competition_risk")
        reasons.append("competition_risk")
    if not core_family and not bool(execution_signal.get("executionEvidencePresent")):
        blockers.append("no_execution_evidence")
        reasons.append("no_execution_evidence")
    elif bool(execution_signal.get("executionEvidencePresent")) and not bool(
        execution_signal.get("actualExecutionReady")
    ):
        blockers.append("execution_not_ready")
        reasons.append(
            str((execution_signal.get("executionReasons") or ["execution_not_ready"])[0])
        )

    degraded_state = ""
    if current_state in {HealthState.QUARANTINED.value, HealthState.DISABLED.value}:
        blockers.append(current_state)
        reasons.append(current_state)
        degraded_state = current_state
    elif current_state in {
        HealthState.CAPPED_LIVE.value,
        HealthState.DEGRADED.value,
        HealthState.OBSERVE_ONLY.value,
    }:
        degraded_state = current_state

    if engine_mode in {"degraded", "observe_only", "disabled"} and not core_family:
        blockers.append("degraded_engine_state")
        reasons.append("degraded_engine_state")
        degraded_state = _prefer_stronger_health_state(
            degraded_state,
            normalize_health_state(engine_mode, default=HealthState.DEGRADED.value),
        )
    elif not no_engine_disable and not core_family:
        blockers.append("engine_execution_restricted")
        reasons.append("engine_execution_restricted")

    score = (
        _score_bool(stage_ok, 0.12)
        + _score_bool(telemetry_sufficient, 0.16)
        + min(0.16, success * 0.16)
        + min(0.10, max(0.0, gas_eff) * 0.03)
        + min(0.14, route_reliability * 0.14)
        + min(0.10, venue_reliability * 0.10)
        + _score_bool(private_ready, 0.06)
        + _score_bool(capital_ready, 0.06)
        + _score_bool(internal_prime_ready, 0.06)
        + max(0.0, 0.10 - competition_pressure * 0.10)
    )
    score = round(_clip(score, 0.0, 1.0), 6)

    status = "blocked"
    if current_state == HealthState.QUARANTINED.value:
        status = "quarantined"
    elif blockers:
        status = "blocked"
    elif degraded_state:
        status = "degraded"
    elif score >= 0.6:
        status = "eligible"

    ready = bool(
        not blockers
        and score >= 0.6
        and current_state not in {HealthState.QUARANTINED.value, HealthState.DISABLED.value}
    )

    suggested_next_action = "continue_v1_learning"
    if status == "eligible":
        suggested_next_action = "activate_family"
    elif drawdown_hard_stop_active:
        suggested_next_action = "reduce_drawdown_and_clear_hard_stop"
    elif kill_switch_active:
        suggested_next_action = "review_kill_switch_and_restore_execution"
    elif family_hardening_reason_codes and not family_hardening_ready:
        suggested_next_action = "restore_family_hardening"
    elif internal_prime_reason_codes and not internal_prime_ready:
        suggested_next_action = "repair_internal_prime_accounting"
    elif receipt_outcome_truth_reason_codes:
        suggested_next_action = "restore_receipt_outcome_truth"
    elif capital_truth_reason_codes and not capital_ready:
        suggested_next_action = "restore_capital_truth"
    elif "no_execution_evidence" in blockers:
        suggested_next_action = "collect_live_execution_evidence"
    elif "telemetry_insufficient" in blockers:
        suggested_next_action = "accumulate_telemetry"
    elif "family_cap_unknown" in blockers:
        suggested_next_action = "synchronize_family_capital_targets"
    elif "private_routing_not_ready" in blockers:
        suggested_next_action = "restore_private_routing"
    elif current_state == HealthState.QUARANTINED.value:
        suggested_next_action = "review_and_revert_to_observe_only"
    elif not exploration_open:
        suggested_next_action = "wait_for_exploration_budget_reset"

    inferred_recovery_status = (
        "global_execution_blocked"
        if global_execution_reason_codes
        else (
            "family_hardening_restore_required"
            if family != "flash_arb" and family_hardening_reason_codes
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
    recovery_status = str((fund_summary or {}).get("recoveryStatus") or inferred_recovery_status)
    recovery_next_action = str(
        (fund_summary or {}).get("recoveryNextAction") or suggested_next_action
    )
    recovery_ready = bool(
        (fund_summary or {}).get(
            "recoveryReady",
            recovery_status == "ready" and not recovery_reason_codes,
        )
    )
    if not recovery_reason_codes:
        if global_execution_reason_codes:
            recovery_reason_codes = list(global_execution_reason_codes)
        elif not core_family and family_hardening_reason_codes:
            recovery_reason_codes = list(family_hardening_reason_codes)
        elif internal_prime_reason_codes:
            recovery_reason_codes = list(internal_prime_reason_codes)
        elif receipt_outcome_truth_reason_codes:
            recovery_reason_codes = list(receipt_outcome_truth_reason_codes)
        elif capital_truth_reason_codes:
            recovery_reason_codes = list(capital_truth_reason_codes)
    if not recovery_reason_code:
        recovery_reason_code = recovery_reason_codes[0] if recovery_reason_codes else "ok"
    if recovery_reason_code != "ok" and recovery_reason_code not in recovery_reason_codes:
        recovery_reason_codes = [recovery_reason_code, *recovery_reason_codes]
    if not core_family and family_hardening_reason_codes:
        recovery_ready = False
        if recovery_status == "ready":
            recovery_status = "family_hardening_restore_required"
        if recovery_reason_code == "ok" or not recovery_reason_code:
            recovery_reason_code = family_hardening_reason_codes[0]
        for code in family_hardening_reason_codes:
            if code not in recovery_reason_codes:
                recovery_reason_codes.append(code)
        if not recovery_next_action or recovery_next_action in {
            "activate_family",
            "continue_v1_learning",
        }:
            recovery_next_action = "restore_family_hardening"
    elif receipt_outcome_truth_reason_codes:
        recovery_ready = False
        if recovery_status == "ready":
            recovery_status = "capital_truth_restore_required"
        if recovery_reason_code == "ok" or not recovery_reason_code:
            recovery_reason_code = receipt_outcome_truth_reason_codes[0]
        for code in receipt_outcome_truth_reason_codes:
            if code not in recovery_reason_codes:
                recovery_reason_codes.append(code)
        if not recovery_next_action or recovery_next_action in {
            "activate_family",
            "continue_v1_learning",
            "restore_capital_truth",
        }:
            recovery_next_action = "restore_receipt_outcome_truth"
    capital_truth_freshness_class = str(
        (fund_summary or {}).get("capitalTruthFreshnessClass") or ""
    )
    receipt_outcome_truth_freshness_class = str(
        (fund_summary or {}).get("receiptOutcomeTruthFreshnessClass") or ""
    )
    receipt_outcome_truth_freshness_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("receiptOutcomeTruthFreshnessReasonCodes") or [])
        if str(x)
    ]
    internal_prime_freshness_class = str(
        (fund_summary or {}).get("internalPrimeFreshnessClass") or ""
    )
    family_hardening_reliability_class = str(
        (fund_summary or {}).get("familyHardeningReliabilityClass")
        or (
            "unavailable"
            if family_hardening_status == "unavailable"
            else ("degraded" if family_hardening_reason_codes else "stable")
        )
    )
    family_hardening_reliability_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("familyHardeningReliabilityReasonCodes") or [])
        if str(x)
    ]
    family_hardening_reliability_reason_code = str(
        (fund_summary or {}).get("familyHardeningReliabilityReasonCode")
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
        (fund_summary or {}).get("familyHardeningRecoveredFragile", False)
    )
    family_hardening_recovery_history_status = str(
        (fund_summary or {}).get("familyHardeningRecoveryHistoryStatus")
        or ("degraded" if family_hardening_reason_codes else "steady")
    )
    if family_hardening_reason_codes and family_hardening_recovery_history_status in {
        "steady",
        "recovered",
        "ready",
    }:
        family_hardening_recovery_history_status = "degraded"
    family_hardening_degraded_since_ts_ms = int(
        (fund_summary or {}).get("familyHardeningDegradedSinceTsMs") or 0
    )
    family_hardening_recovered_at_ts_ms = int(
        (fund_summary or {}).get("familyHardeningRecoveredAtTsMs") or 0
    )
    family_hardening_degraded_duration_ms = int(
        (fund_summary or {}).get("familyHardeningDegradedDurationMs") or 0
    )
    family_hardening_degraded_count = int(
        (fund_summary or {}).get("familyHardeningDegradedCount") or 0
    )
    family_hardening_last_healthy_ts_ms = int(
        (fund_summary or {}).get("familyHardeningLastHealthyTsMs") or 0
    )
    family_hardening_recovered_recently = bool(
        (fund_summary or {}).get("familyHardeningRecoveredRecently", False)
    )
    family_hardening_degradation_severity_class = str(
        (fund_summary or {}).get("familyHardeningDegradationSeverityClass")
        or (
            "recovering"
            if family_hardening_recovery_history_status == "recovered"
            and family_hardening_recovered_recently
            else ("stable" if family_hardening_recovery_history_status == "steady" else "acute")
        )
    )
    recovery_freshness_class = str(
        (fund_summary or {}).get("recoveryFreshnessClass")
        or ("current" if recovery_status in {"ready", "global_execution_blocked"} else "unknown")
    )
    recovery_freshness_next_action = str(
        (fund_summary or {}).get("recoveryFreshnessNextAction") or ""
    )
    recovery_history_component = str((fund_summary or {}).get("recoveryHistoryComponent") or "")
    receipt_outcome_truth_recovery_history_status = str(
        (fund_summary or {}).get("receiptOutcomeTruthRecoveryHistoryStatus")
        or ("degraded" if receipt_outcome_truth_reason_codes else "steady")
    )
    if receipt_outcome_truth_reason_codes and receipt_outcome_truth_recovery_history_status in {
        "steady",
        "recovered",
        "ready",
    }:
        receipt_outcome_truth_recovery_history_status = "degraded"
    recovery_history_status = str(
        (fund_summary or {}).get("recoveryHistoryStatus")
        or (
            "blocked"
            if recovery_status == "global_execution_blocked"
            else ("recovered" if recovery_ready else "steady")
        )
    )
    if not core_family and family_hardening_reason_codes:
        if recovery_history_component in {"", "capital_truth", "internal_prime_reconciliation"}:
            recovery_history_component = "family_hardening"
        if recovery_history_status in {"steady", "recovered", "ready"}:
            recovery_history_status = "degraded"
    elif (
        family != "flash_arb"
        and recovery_history_component in {"", "capital_truth", "internal_prime_reconciliation"}
        and family_hardening_recovery_history_status in {"recovered", "degraded"}
    ):
        recovery_history_component = "family_hardening"
        recovery_history_status = family_hardening_recovery_history_status
    elif receipt_outcome_truth_reason_codes:
        if recovery_history_component in {"", "capital_truth"}:
            recovery_history_component = "receipt_outcome_truth"
        if recovery_history_component == "receipt_outcome_truth" and recovery_history_status in {
            "steady",
            "recovered",
            "ready",
        }:
            recovery_history_status = "degraded"
    elif recovery_history_component in {
        "",
        "capital_truth",
    } and receipt_outcome_truth_recovery_history_status in {"recovered", "degraded"}:
        recovery_history_component = "receipt_outcome_truth"
        recovery_history_status = receipt_outcome_truth_recovery_history_status
    receipt_outcome_truth_degraded_since_ts_ms = int(
        (fund_summary or {}).get("receiptOutcomeTruthDegradedSinceTsMs") or 0
    )
    receipt_outcome_truth_recovered_at_ts_ms = int(
        (fund_summary or {}).get("receiptOutcomeTruthRecoveredAtTsMs") or 0
    )
    receipt_outcome_truth_degraded_duration_ms = int(
        (fund_summary or {}).get("receiptOutcomeTruthDegradedDurationMs") or 0
    )
    recovery_degraded_since_ts_ms = int((fund_summary or {}).get("recoveryDegradedSinceTsMs") or 0)
    recovery_recovered_at_ts_ms = int((fund_summary or {}).get("recoveryRecoveredAtTsMs") or 0)
    recovery_degraded_duration_ms = int((fund_summary or {}).get("recoveryDegradedDurationMs") or 0)
    capital_truth_recovery_history_status = str(
        (fund_summary or {}).get("capitalTruthRecoveryHistoryStatus")
        or ("degraded" if capital_truth_reason_codes else "steady")
    )
    capital_truth_degraded_since_ts_ms = int(
        (fund_summary or {}).get("capitalTruthDegradedSinceTsMs") or 0
    )
    capital_truth_recovered_at_ts_ms = int(
        (fund_summary or {}).get("capitalTruthRecoveredAtTsMs") or 0
    )
    capital_truth_degraded_duration_ms = int(
        (fund_summary or {}).get("capitalTruthDegradedDurationMs") or 0
    )
    internal_prime_recovery_history_status = str(
        (fund_summary or {}).get("internalPrimeRecoveryHistoryStatus")
        or ("degraded" if internal_prime_reason_codes else "steady")
    )
    internal_prime_degraded_since_ts_ms = int(
        (fund_summary or {}).get("internalPrimeDegradedSinceTsMs") or 0
    )
    internal_prime_recovered_at_ts_ms = int(
        (fund_summary or {}).get("internalPrimeRecoveredAtTsMs") or 0
    )
    internal_prime_degraded_duration_ms = int(
        (fund_summary or {}).get("internalPrimeDegradedDurationMs") or 0
    )
    recovery_degraded_count = int((fund_summary or {}).get("recoveryDegradedCount") or 0)
    recovery_last_healthy_ts_ms = int((fund_summary or {}).get("recoveryLastHealthyTsMs") or 0)
    recovery_recovered_recently = bool((fund_summary or {}).get("recoveryRecoveredRecently", False))
    recovery_degradation_severity_class = str(
        (fund_summary or {}).get("recoveryDegradationSeverityClass")
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
    capital_truth_degraded_count = int((fund_summary or {}).get("capitalTruthDegradedCount") or 0)
    capital_truth_last_healthy_ts_ms = int(
        (fund_summary or {}).get("capitalTruthLastHealthyTsMs") or 0
    )
    capital_truth_recovered_recently = bool(
        (fund_summary or {}).get("capitalTruthRecoveredRecently", False)
    )
    capital_truth_degradation_severity_class = str(
        (fund_summary or {}).get("capitalTruthDegradationSeverityClass")
        or (
            "recovering"
            if capital_truth_recovery_history_status == "recovered"
            and capital_truth_recovered_recently
            else ("stable" if capital_truth_recovery_history_status == "steady" else "acute")
        )
    )
    receipt_outcome_truth_degraded_count = int(
        (fund_summary or {}).get("receiptOutcomeTruthDegradedCount") or 0
    )
    receipt_outcome_truth_last_healthy_ts_ms = int(
        (fund_summary or {}).get("receiptOutcomeTruthLastHealthyTsMs") or 0
    )
    receipt_outcome_truth_recovered_recently = bool(
        (fund_summary or {}).get("receiptOutcomeTruthRecoveredRecently", False)
    )
    receipt_outcome_truth_degradation_severity_class = str(
        (fund_summary or {}).get("receiptOutcomeTruthDegradationSeverityClass")
        or (
            "recovering"
            if receipt_outcome_truth_recovery_history_status == "recovered"
            and receipt_outcome_truth_recovered_recently
            else (
                "stable" if receipt_outcome_truth_recovery_history_status == "steady" else "acute"
            )
        )
    )
    internal_prime_degraded_count = int((fund_summary or {}).get("internalPrimeDegradedCount") or 0)
    internal_prime_last_healthy_ts_ms = int(
        (fund_summary or {}).get("internalPrimeLastHealthyTsMs") or 0
    )
    internal_prime_recovered_recently = bool(
        (fund_summary or {}).get("internalPrimeRecoveredRecently", False)
    )
    internal_prime_degradation_severity_class = str(
        (fund_summary or {}).get("internalPrimeDegradationSeverityClass")
        or (
            "recovering"
            if internal_prime_recovery_history_status == "recovered"
            and internal_prime_recovered_recently
            else ("stable" if internal_prime_recovery_history_status == "steady" else "acute")
        )
    )
    capital_truth_reliability_class = str(
        (fund_summary or {}).get("capitalTruthReliabilityClass")
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
        (fund_summary or {}).get("capitalTruthReliabilityReasonCode")
        or (
            f"capital_truth_reliability_{capital_truth_reliability_class}"
            if capital_truth_reliability_class != "stable"
            else "ok"
        )
    )
    capital_truth_reliability_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("capitalTruthReliabilityReasonCodes") or [])
        if str(x)
    ]
    if (
        capital_truth_reliability_reason_code != "ok"
        and capital_truth_reliability_reason_code not in capital_truth_reliability_reason_codes
    ):
        capital_truth_reliability_reason_codes = [
            capital_truth_reliability_reason_code,
            *capital_truth_reliability_reason_codes,
        ]
    capital_truth_recovered_fragile = bool(
        (fund_summary or {}).get(
            "capitalTruthRecoveredFragile",
            capital_truth_recovery_history_status == "recovered"
            and capital_truth_reliability_class == "fragile",
        )
    )
    receipt_outcome_truth_reliability_class = str(
        (fund_summary or {}).get("receiptOutcomeTruthReliabilityClass")
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
        (fund_summary or {}).get("receiptOutcomeTruthReliabilityReasonCode")
        or (
            f"receipt_outcome_truth_reliability_{receipt_outcome_truth_reliability_class}"
            if receipt_outcome_truth_reliability_class != "stable"
            else "ok"
        )
    )
    receipt_outcome_truth_reliability_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("receiptOutcomeTruthReliabilityReasonCodes") or [])
        if str(x)
    ]
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
        (fund_summary or {}).get(
            "receiptOutcomeTruthRecoveredFragile",
            receipt_outcome_truth_recovery_history_status == "recovered"
            and receipt_outcome_truth_reliability_class == "fragile",
        )
    )
    receipt_outcome_truth_rollout = _receipt_outcome_truth_rollout_gate(
        family=family,
        fund_summary=fund_summary,
        freshness_class=receipt_outcome_truth_freshness_class,
        freshness_reason_codes=receipt_outcome_truth_freshness_reason_codes,
        reliability_class=receipt_outcome_truth_reliability_class,
        reliability_reason_code=receipt_outcome_truth_reliability_reason_code,
        reliability_reason_codes=receipt_outcome_truth_reliability_reason_codes,
    )
    receipt_outcome_truth_rollout_ready = bool(receipt_outcome_truth_rollout.get("ready", True))
    receipt_outcome_truth_rollout_reason_codes = [
        str(x) for x in list(receipt_outcome_truth_rollout.get("reasonCodes") or []) if str(x)
    ]
    internal_prime_reliability_class = str(
        (fund_summary or {}).get("internalPrimeReliabilityClass")
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
        (fund_summary or {}).get("internalPrimeReliabilityReasonCode")
        or (
            f"internal_prime_reliability_{internal_prime_reliability_class}"
            if internal_prime_reliability_class != "stable"
            else "ok"
        )
    )
    internal_prime_reliability_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("internalPrimeReliabilityReasonCodes") or [])
        if str(x)
    ]
    if (
        internal_prime_reliability_reason_code != "ok"
        and internal_prime_reliability_reason_code not in internal_prime_reliability_reason_codes
    ):
        internal_prime_reliability_reason_codes = [
            internal_prime_reliability_reason_code,
            *internal_prime_reliability_reason_codes,
        ]
    internal_prime_recovered_fragile = bool(
        (fund_summary or {}).get(
            "internalPrimeRecoveredFragile",
            internal_prime_recovery_history_status == "recovered"
            and internal_prime_reliability_class == "fragile",
        )
    )
    recovery_reliability_class = str(
        (fund_summary or {}).get("recoveryReliabilityClass")
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
    if (
        family != "flash_arb"
        and family_hardening_reason_codes
        and recovery_reliability_class == "stable"
    ):
        recovery_reliability_class = family_hardening_reliability_class
    recovery_reliability_reason_code = str(
        (fund_summary or {}).get("recoveryReliabilityReasonCode")
        or (
            f"recovery_reliability_{recovery_reliability_class}"
            if recovery_reliability_class != "stable"
            else "ok"
        )
    )
    recovery_reliability_reason_codes = [
        str(x)
        for x in list((fund_summary or {}).get("recoveryReliabilityReasonCodes") or [])
        if str(x)
    ]
    if not core_family and family_hardening_reason_codes:
        if recovery_reliability_reason_code == "ok" or not recovery_reliability_reason_code:
            recovery_reliability_reason_code = family_hardening_reliability_reason_code
        for code in family_hardening_reliability_reason_codes:
            if code not in recovery_reliability_reason_codes:
                recovery_reliability_reason_codes.append(code)
    elif (
        family != "flash_arb"
        and recovery_history_component == "family_hardening"
        and family_hardening_reliability_class == "fragile"
        and recovery_reliability_class == "stable"
    ):
        recovery_reliability_class = "fragile"
        if recovery_reliability_reason_code == "ok" or not recovery_reliability_reason_code:
            recovery_reliability_reason_code = family_hardening_reliability_reason_code
        for code in family_hardening_reliability_reason_codes:
            if code not in recovery_reliability_reason_codes:
                recovery_reliability_reason_codes.append(code)
    elif receipt_outcome_truth_reason_codes and recovery_reliability_class == "stable":
        recovery_reliability_class = receipt_outcome_truth_reliability_class
        if recovery_reliability_reason_code == "ok" or not recovery_reliability_reason_code:
            recovery_reliability_reason_code = receipt_outcome_truth_reliability_reason_code
        for code in receipt_outcome_truth_reliability_reason_codes:
            if code not in recovery_reliability_reason_codes:
                recovery_reliability_reason_codes.append(code)
    elif (
        recovery_history_component == "receipt_outcome_truth"
        and receipt_outcome_truth_reliability_class == "fragile"
        and recovery_reliability_class == "stable"
    ):
        recovery_reliability_class = "fragile"
        if recovery_reliability_reason_code == "ok" or not recovery_reliability_reason_code:
            recovery_reliability_reason_code = receipt_outcome_truth_reliability_reason_code
        for code in receipt_outcome_truth_reliability_reason_codes:
            if code not in recovery_reliability_reason_codes:
                recovery_reliability_reason_codes.append(code)
    if (
        recovery_reliability_reason_code != "ok"
        and recovery_reliability_reason_code not in recovery_reliability_reason_codes
    ):
        recovery_reliability_reason_codes = [
            recovery_reliability_reason_code,
            *recovery_reliability_reason_codes,
        ]
    recovery_reliability_next_action = str(
        (fund_summary or {}).get("recoveryReliabilityNextAction")
        or recovery_next_action
        or recovery_freshness_next_action
    )
    recovery_recovered_fragile = bool(
        (fund_summary or {}).get(
            "recoveryRecoveredFragile",
            recovery_history_status == "recovered" and recovery_reliability_class == "fragile",
        )
    )
    if not core_family and receipt_outcome_truth_rollout_reason_codes:
        for code in receipt_outcome_truth_rollout_reason_codes:
            if code not in blockers:
                blockers.append(code)
            if code not in reasons:
                reasons.append(code)
        if "receipt_outcome_truth_not_rollout_ready" not in blockers:
            blockers.append("receipt_outcome_truth_not_rollout_ready")
        if status != "quarantined":
            status = "blocked"
        ready = False
        recovery_ready = False
        if recovery_status == "ready":
            recovery_status = "capital_truth_restore_required"
        if recovery_reason_code in {"", "ok"}:
            recovery_reason_code = receipt_outcome_truth_rollout_reason_codes[0]
        for code in receipt_outcome_truth_rollout_reason_codes:
            if code not in recovery_reason_codes:
                recovery_reason_codes.append(code)
        if recovery_history_component in {"", "capital_truth"}:
            recovery_history_component = "receipt_outcome_truth"
        if recovery_history_status in {"steady", "recovered", "ready"}:
            recovery_history_status = "degraded"
        if not recovery_next_action or recovery_next_action in {
            "activate_family",
            "continue_v1_learning",
            "restore_capital_truth",
        }:
            recovery_next_action = str(
                receipt_outcome_truth_rollout.get("nextAction") or "restore_receipt_outcome_truth"
            )
        if not suggested_next_action or suggested_next_action in {
            "activate_family",
            "continue_v1_learning",
        }:
            suggested_next_action = str(
                receipt_outcome_truth_rollout.get("nextAction") or "restore_receipt_outcome_truth"
            )

    recovery_reliability_rollout_ready = recovery_reliability_class in {"stable", "cautious"}
    if not core_family and not recovery_reliability_rollout_ready:
        reliability_blocker = (
            "recovery_reliability_fragile"
            if recovery_reliability_class == "fragile"
            else "recovery_reliability_not_ready"
        )
        if reliability_blocker not in blockers:
            blockers.append(reliability_blocker)
        reliability_reason = (
            recovery_reliability_reason_code
            if recovery_reliability_reason_code and recovery_reliability_reason_code != "ok"
            else f"recovery_reliability_{recovery_reliability_class or 'unknown'}"
        )
        if reliability_reason not in reasons:
            reasons.append(reliability_reason)
        if status != "quarantined":
            status = "blocked"
        ready = False
        if not suggested_next_action or suggested_next_action in {
            "activate_family",
            "continue_v1_learning",
        }:
            suggested_next_action = (
                recovery_reliability_next_action
                or recovery_next_action
                or recovery_freshness_next_action
                or "stabilize_recovery_before_rollout"
            )
    launch_acceleration = family_launch_acceleration_signal(
        {
            "family": family,
            "ready": ready,
            "count": count,
            "successRate": success,
            "executionEvidencePresent": bool(execution_signal.get("executionEvidencePresent")),
            "actualExecutionReady": bool(execution_signal.get("actualExecutionReady")),
            "executionReasons": list(execution_signal.get("executionReasons") or []),
            "telemetrySufficient": telemetry_sufficient,
            "capitalReady": capital_ready,
            "capitalTruthReasonCodes": capital_truth_reason_codes,
            "receiptOutcomeTruthRolloutReady": receipt_outcome_truth_rollout_ready,
            "receiptOutcomeTruthRolloutReasonCodes": receipt_outcome_truth_rollout_reason_codes,
            "recoveryReliabilityRolloutReady": recovery_reliability_rollout_ready,
            "recoveryReliabilityReasonCodes": recovery_reliability_reason_codes,
            "familyHardeningReady": family_hardening_ready,
            "familyHardeningReasonCodes": family_hardening_reason_codes,
            "currentHealthState": current_state,
            "active": family in active_family_ids,
            "globalExecutionBlocked": bool(global_execution_reason_codes),
            "receiptOutcomeTruthReasonCodes": receipt_outcome_truth_reason_codes,
            "suggestedNextAction": suggested_next_action,
        }
    )
    launch_acceleration_seed_ready = bool(launch_acceleration.get("seedReady", False))
    launch_acceleration_stable_ready = bool(launch_acceleration.get("stableReady", False))
    launch_acceleration_reason_codes = [
        str(x) for x in list(launch_acceleration.get("seedReasonCodes") or []) if str(x)
    ]
    launch_acceleration_stability_reason_codes = [
        str(x) for x in list(launch_acceleration.get("stableReasonCodes") or []) if str(x)
    ]
    if not core_family and launch_acceleration_reason_codes:
        if "launch_acceleration_not_ready" not in blockers:
            blockers.append("launch_acceleration_not_ready")
        _extend_unique(blockers, launch_acceleration_reason_codes)
        _extend_unique(reasons, launch_acceleration_reason_codes)
        if status != "quarantined":
            status = "blocked"
        ready = False
        if not suggested_next_action or suggested_next_action in {
            "activate_family",
            "continue_v1_learning",
            "collect_live_execution_evidence",
        }:
            suggested_next_action = str(
                launch_acceleration.get("nextAction") or "collect_live_execution_evidence"
            )

    if recovery_ready:
        recovery_status = "ready"
        recovery_reason_code = "ok"
        recovery_reason_codes = []
        recovery_next_action = ""

    risk_level = "low"
    if competition_pressure >= 0.65 or drawdown > 0.0:
        risk_level = "medium"
    if competition_pressure >= 0.85 or current_state in {
        HealthState.QUARANTINED.value,
        HealthState.DISABLED.value,
    }:
        risk_level = "high"

    effective_state = current_state
    state_alignment = "aligned"
    if (
        not core_family
        and family in active_family_ids
        and not bool(execution_signal.get("actualExecutionReady"))
    ):
        effective_state = HealthState.DEGRADED.value
        state_alignment = "execution_truth_override"
    elif not core_family and not bool(execution_signal.get("executionEvidencePresent")):
        effective_state = HealthState.OBSERVE_ONLY.value
        state_alignment = (
            "execution_truth_override"
            if current_state
            not in {
                HealthState.OBSERVE_ONLY.value,
                HealthState.QUARANTINED.value,
                HealthState.DISABLED.value,
            }
            else "aligned"
        )

    return {
        "family": family,
        "requestedFamily": requested_family,
        "launchFamily": family,
        "runtimeFamily": runtime_family,
        "capitalFamily": capital_family,
        "displayFamily": str(identity.get("displayName") or family.replace("_", " ").title()),
        "familyAliases": family_aliases,
        "familyIdentity": dict(identity),
        "profileState": current_state,
        "effectiveState": effective_state,
        "stateAlignment": state_alignment,
        "score": score,
        "ready": ready,
        "status": status,
        "reasons": reasons,
        "blockers": blockers,
        "count": count,
        "successRate": round(success, 6),
        "gasEfficiency": round(gas_eff, 6),
        "calibrationQuality": round(route_reliability, 6),
        "routeReliability": round(route_reliability, 6),
        "venueReliability": round(venue_reliability, 6),
        "competitionPressure": round(competition_pressure, 6),
        "telemetrySufficient": telemetry_sufficient,
        "capitalReady": capital_ready,
        "capitalTruthReasonCodes": capital_truth_reason_codes,
        "globalExecutionBlocked": bool(global_execution_reason_codes),
        "globalExecutionReasonCodes": global_execution_reason_codes,
        "drawdownHardStopActive": drawdown_hard_stop_active,
        "killSwitchActive": kill_switch_active,
        "recoveryReady": recovery_ready,
        "recoveryStatus": recovery_status,
        "recoveryReasonCode": recovery_reason_code,
        "recoveryReasonCodes": recovery_reason_codes,
        "recoveryNextAction": recovery_next_action,
        "recoveryFreshnessClass": recovery_freshness_class,
        "recoveryFreshnessReasonCode": recovery_freshness_reason_code
        or (recovery_freshness_reason_codes[0] if recovery_freshness_reason_codes else "ok"),
        "recoveryFreshnessReasonCodes": recovery_freshness_reason_codes,
        "recoveryFreshnessNextAction": recovery_freshness_next_action,
        "recoveryHistoryComponent": recovery_history_component,
        "recoveryHistoryStatus": recovery_history_status,
        "recoveryDegradedSinceTsMs": recovery_degraded_since_ts_ms,
        "recoveryRecoveredAtTsMs": recovery_recovered_at_ts_ms,
        "recoveryDegradedDurationMs": recovery_degraded_duration_ms,
        "recoveryDegradedCount": recovery_degraded_count,
        "recoveryLastHealthyTsMs": recovery_last_healthy_ts_ms,
        "recoveryRecoveredRecently": recovery_recovered_recently,
        "recoveryDegradationSeverityClass": recovery_degradation_severity_class,
        "capitalTruthRecoveryHistoryStatus": capital_truth_recovery_history_status,
        "receiptOutcomeTruthReasonCodes": receipt_outcome_truth_reason_codes,
        "receiptOutcomeTruthFreshnessClass": receipt_outcome_truth_freshness_class,
        "receiptOutcomeTruthFreshnessReasonCodes": receipt_outcome_truth_freshness_reason_codes,
        "receiptOutcomeTruthRecoveryHistoryStatus": receipt_outcome_truth_recovery_history_status,
        "receiptOutcomeTruthDegradedSinceTsMs": receipt_outcome_truth_degraded_since_ts_ms,
        "receiptOutcomeTruthRecoveredAtTsMs": receipt_outcome_truth_recovered_at_ts_ms,
        "receiptOutcomeTruthDegradedDurationMs": receipt_outcome_truth_degraded_duration_ms,
        "receiptOutcomeTruthDegradedCount": receipt_outcome_truth_degraded_count,
        "receiptOutcomeTruthLastHealthyTsMs": receipt_outcome_truth_last_healthy_ts_ms,
        "receiptOutcomeTruthRecoveredRecently": receipt_outcome_truth_recovered_recently,
        "receiptOutcomeTruthDegradationSeverityClass": receipt_outcome_truth_degradation_severity_class,
        "capitalTruthDegradedSinceTsMs": capital_truth_degraded_since_ts_ms,
        "capitalTruthRecoveredAtTsMs": capital_truth_recovered_at_ts_ms,
        "capitalTruthDegradedDurationMs": capital_truth_degraded_duration_ms,
        "capitalTruthDegradedCount": capital_truth_degraded_count,
        "capitalTruthLastHealthyTsMs": capital_truth_last_healthy_ts_ms,
        "capitalTruthRecoveredRecently": capital_truth_recovered_recently,
        "capitalTruthDegradationSeverityClass": capital_truth_degradation_severity_class,
        "internalPrimeRecoveryHistoryStatus": internal_prime_recovery_history_status,
        "internalPrimeDegradedSinceTsMs": internal_prime_degraded_since_ts_ms,
        "internalPrimeRecoveredAtTsMs": internal_prime_recovered_at_ts_ms,
        "internalPrimeDegradedDurationMs": internal_prime_degraded_duration_ms,
        "internalPrimeDegradedCount": internal_prime_degraded_count,
        "internalPrimeLastHealthyTsMs": internal_prime_last_healthy_ts_ms,
        "internalPrimeRecoveredRecently": internal_prime_recovered_recently,
        "internalPrimeDegradationSeverityClass": internal_prime_degradation_severity_class,
        "capitalTruthReliabilityClass": capital_truth_reliability_class,
        "capitalTruthReliabilityReasonCode": capital_truth_reliability_reason_code,
        "capitalTruthReliabilityReasonCodes": capital_truth_reliability_reason_codes,
        "capitalTruthRecoveredFragile": capital_truth_recovered_fragile,
        "receiptOutcomeTruthReliabilityClass": receipt_outcome_truth_reliability_class,
        "receiptOutcomeTruthReliabilityReasonCode": receipt_outcome_truth_reliability_reason_code,
        "receiptOutcomeTruthReliabilityReasonCodes": receipt_outcome_truth_reliability_reason_codes,
        "receiptOutcomeTruthRecoveredFragile": receipt_outcome_truth_recovered_fragile,
        "receiptOutcomeTruthRolloutReady": receipt_outcome_truth_rollout_ready,
        "receiptOutcomeTruthRolloutReasonCodes": receipt_outcome_truth_rollout_reason_codes,
        "internalPrimeReliabilityClass": internal_prime_reliability_class,
        "internalPrimeReliabilityReasonCode": internal_prime_reliability_reason_code,
        "internalPrimeReliabilityReasonCodes": internal_prime_reliability_reason_codes,
        "internalPrimeRecoveredFragile": internal_prime_recovered_fragile,
        "recoveryReliabilityClass": recovery_reliability_class,
        "recoveryReliabilityReasonCode": recovery_reliability_reason_code,
        "recoveryReliabilityReasonCodes": recovery_reliability_reason_codes,
        "recoveryReliabilityNextAction": recovery_reliability_next_action,
        "recoveryReliabilityRolloutReady": recovery_reliability_rollout_ready,
        "recoveryRecoveredFragile": recovery_recovered_fragile,
        "launchAccelerationSeedReady": launch_acceleration_seed_ready,
        "launchAccelerationStableReady": launch_acceleration_stable_ready,
        "launchAccelerationReasonCodes": launch_acceleration_reason_codes,
        "launchAccelerationStabilityReasonCodes": launch_acceleration_stability_reason_codes,
        "launchAccelerationNextAction": str(launch_acceleration.get("nextAction") or ""),
        "capitalTargetKnown": family_target_known,
        "familyTargetPct": round(family_target, 6),
        "resolvedFamilyTargetKey": resolved_family_target_key,
        "capitalTargetReady": capital_target_ready,
        "internalPrimeReady": internal_prime_ready,
        "internalPrimeReasonCodes": internal_prime_reason_codes,
        "familyHardeningReady": family_hardening_ready,
        "familyHardeningStatus": family_hardening_status,
        "familyHardeningReasonCodes": family_hardening_reason_codes,
        "familyHardeningReliabilityClass": family_hardening_reliability_class,
        "familyHardeningReliabilityReasonCode": family_hardening_reliability_reason_code,
        "familyHardeningReliabilityReasonCodes": family_hardening_reliability_reason_codes,
        "familyHardeningRecoveryHistoryStatus": family_hardening_recovery_history_status,
        "familyHardeningDegradedSinceTsMs": family_hardening_degraded_since_ts_ms,
        "familyHardeningRecoveredAtTsMs": family_hardening_recovered_at_ts_ms,
        "familyHardeningDegradedDurationMs": family_hardening_degraded_duration_ms,
        "familyHardeningDegradedCount": family_hardening_degraded_count,
        "familyHardeningLastHealthyTsMs": family_hardening_last_healthy_ts_ms,
        "familyHardeningRecoveredRecently": family_hardening_recovered_recently,
        "familyHardeningDegradationSeverityClass": family_hardening_degradation_severity_class,
        "familyHardeningRecoveredFragile": family_hardening_recovered_fragile,
        "stageAllowed": stage_ok,
        "active": family in active_families,
        "rolloutIndex": (
            DEFAULT_ACTIVATION_ORDER.index(family) if family in DEFAULT_ACTIVATION_ORDER else 999
        ),
        "degradedState": degraded_state,
        "executionEvidencePresent": bool(execution_signal.get("executionEvidencePresent")),
        "actualExecutionReady": bool(execution_signal.get("actualExecutionReady")),
        "executionMode": str(execution_signal.get("executionMode") or ""),
        "executionReasons": list(execution_signal.get("executionReasons") or []),
        "currentHealthState": current_state,
        "explorationBudgetOpen": exploration_open,
        "suggestedNextAction": suggested_next_action,
        "riskLevel": risk_level,
    }
