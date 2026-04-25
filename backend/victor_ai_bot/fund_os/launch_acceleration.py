from __future__ import annotations

from typing import Any, Dict, List

from .family_identity import canonical_launch_family_id, is_core_launch_family
from .health_states import HealthState, normalize_health_state

SEED_MIN_REALIZED_EXECUTIONS = 3
SEED_MIN_SUCCESS_RATE = 0.65
STABLE_MIN_REALIZED_EXECUTIONS = 5
STABLE_MIN_SUCCESS_RATE = 0.70


def _unique(values: List[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        value_s = str(value or "")
        if value_s and value_s not in out:
            out.append(value_s)
    return out


def family_launch_acceleration_signal(readiness: Dict[str, Any]) -> Dict[str, Any]:
    info = dict(readiness or {})
    family = canonical_launch_family_id(str(info.get("family") or ""))
    count = int(info.get("count") or 0)
    success = float(info.get("successRate") or 0.0)
    execution_evidence_present = bool(info.get("executionEvidencePresent", False))
    actual_execution_ready = bool(info.get("actualExecutionReady", False))
    telemetry_sufficient = bool(info.get("telemetrySufficient", False))
    capital_ready = bool(info.get("capitalReady", False))
    receipt_truth_rollout_ready = bool(info.get("receiptOutcomeTruthRolloutReady", True))
    recovery_rollout_ready = bool(info.get("recoveryReliabilityRolloutReady", True))
    family_hardening_ready = bool(info.get("familyHardeningReady", is_core_launch_family(family)))
    current_state = normalize_health_state(
        str(info.get("currentHealthState") or ""), default=HealthState.OBSERVE_ONLY.value
    )
    active = bool(info.get("active", False))

    seed_reason_codes: List[str] = []
    stable_reason_codes: List[str] = []

    if is_core_launch_family(family):
        core_stable = (
            current_state in {HealthState.LIVE.value, HealthState.CAPPED_LIVE.value}
            and not bool(info.get("globalExecutionBlocked", False))
            and not bool(info.get("capitalTruthReasonCodes") or [])
            and not bool(info.get("receiptOutcomeTruthReasonCodes") or [])
        )
        return {
            "seedReady": core_stable,
            "stableReady": core_stable,
            "seedReasonCodes": [] if core_stable else ["v1_core_not_stable"],
            "stableReasonCodes": [] if core_stable else ["v1_core_not_stable"],
            "nextAction": "stabilize_v1_core" if not core_stable else "",
        }

    if not execution_evidence_present:
        seed_reason_codes.append("no_execution_evidence")
    if count < SEED_MIN_REALIZED_EXECUTIONS:
        seed_reason_codes.append("insufficient_realized_execution_evidence")
    if count > 0 and success < SEED_MIN_SUCCESS_RATE:
        seed_reason_codes.append("execution_success_rate_below_seed_floor")
    if execution_evidence_present and not actual_execution_ready:
        seed_reason_codes.extend([str(x) for x in list(info.get("executionReasons") or []) if str(x)])
    if not telemetry_sufficient:
        seed_reason_codes.append("telemetry_insufficient")
    if not capital_ready:
        seed_reason_codes.extend([str(x) for x in list(info.get("capitalTruthReasonCodes") or []) if str(x)])
    if not receipt_truth_rollout_ready:
        seed_reason_codes.extend(
            [str(x) for x in list(info.get("receiptOutcomeTruthRolloutReasonCodes") or []) if str(x)]
        )
    if not family_hardening_ready:
        seed_reason_codes.extend([str(x) for x in list(info.get("familyHardeningReasonCodes") or []) if str(x)])

    seed_reason_codes = _unique(seed_reason_codes)
    seed_ready = bool(info.get("ready", False)) and not seed_reason_codes

    stable_reason_codes = list(seed_reason_codes)
    if count < STABLE_MIN_REALIZED_EXECUTIONS:
        stable_reason_codes.append("insufficient_multi_strategy_stability_evidence")
    if count > 0 and success < STABLE_MIN_SUCCESS_RATE:
        stable_reason_codes.append("execution_success_rate_below_stability_floor")
    if active and current_state not in {HealthState.LIVE.value, HealthState.CAPPED_LIVE.value}:
        stable_reason_codes.append("family_not_yet_live_for_multi_strategy")
    if not recovery_rollout_ready:
        stable_reason_codes.extend(
            [str(x) for x in list(info.get("recoveryReliabilityReasonCodes") or []) if str(x)]
        )

    stable_reason_codes = _unique(stable_reason_codes)
    stable_ready = seed_ready and not stable_reason_codes

    next_action = ""
    if seed_reason_codes:
        if "insufficient_realized_execution_evidence" in seed_reason_codes:
            next_action = "collect_live_execution_evidence"
        elif "execution_success_rate_below_seed_floor" in seed_reason_codes:
            next_action = "improve_realized_execution_quality"
        elif not receipt_truth_rollout_ready:
            next_action = "restore_receipt_outcome_truth"
        elif not capital_ready:
            next_action = "restore_capital_truth"
        else:
            next_action = str(info.get("suggestedNextAction") or "continue_v1_learning")
    elif stable_reason_codes:
        if "insufficient_multi_strategy_stability_evidence" in stable_reason_codes:
            next_action = "stabilize_active_family_before_expansion"
        elif "execution_success_rate_below_stability_floor" in stable_reason_codes:
            next_action = "improve_realized_execution_quality"
        else:
            next_action = str(info.get("suggestedNextAction") or "continue_v1_learning")

    return {
        "seedReady": seed_ready,
        "stableReady": stable_ready,
        "seedReasonCodes": seed_reason_codes,
        "stableReasonCodes": stable_reason_codes,
        "nextAction": next_action,
    }


def build_launch_acceleration_summary(
    *, profile: Dict[str, Any], readiness_items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    items = [dict(item or {}) for item in list(readiness_items or []) if isinstance(item, dict)]
    by_family = {str(item.get("family") or ""): item for item in items}
    active_families = [canonical_launch_family_id(str(x or "")) for x in list((profile or {}).get("active_families") or []) if str(x)]
    active_secondary_families = [family for family in active_families if not is_core_launch_family(family)]

    signals = {
        canonical_launch_family_id(family): family_launch_acceleration_signal(item)
        for family, item in by_family.items() if family
    }
    core_signal = signals.get("flash_arb") or family_launch_acceleration_signal(by_family.get("flash_arb") or {})
    core_stable = bool(core_signal.get("stableReady", False))

    seed_candidates = [
        family
        for family, item in by_family.items()
        if not is_core_launch_family(family)
        and not bool(item.get("active", False))
        and bool((signals.get(family) or {}).get("seedReady", False))
    ]
    stable_secondary_families = [
        family
        for family in active_secondary_families
        if bool((signals.get(family) or {}).get("stableReady", False))
    ]
    unstable_secondary_families = [
        family
        for family in active_secondary_families
        if family not in stable_secondary_families
    ]

    reason_codes: List[str] = []
    next_action = ""
    phase = "v1_learning"
    if not core_stable:
        phase = "stabilize_v1_core"
        reason_codes = list(core_signal.get("stableReasonCodes") or ["v1_core_not_stable"])
        next_action = str(core_signal.get("nextAction") or "stabilize_v1_core")
    elif unstable_secondary_families:
        phase = "stabilize_active_multi_strategy"
        for family in unstable_secondary_families:
            signal = signals.get(family) or {}
            reason_codes.extend([str(x) for x in list(signal.get("stableReasonCodes") or []) if str(x)])
        reason_codes = _unique(reason_codes)
        next_action = "stabilize_active_family_before_expansion"
    elif seed_candidates:
        phase = (
            "expand_multi_strategy" if stable_secondary_families else "seed_next_family"
        )
        next_action = "enable_next_family"
    elif stable_secondary_families:
        phase = "stable_multi_strategy"
        next_action = "continue_compounding"
    else:
        phase = "v1_learning"
        next_action = "collect_live_execution_evidence"

    return {
        "phase": phase,
        "coreStable": core_stable,
        "activeSecondaryFamilies": active_secondary_families,
        "stableSecondaryFamilies": stable_secondary_families,
        "unstableSecondaryFamilies": unstable_secondary_families,
        "seedCandidateFamilies": seed_candidates,
        "reasonCodes": reason_codes,
        "nextAction": next_action,
        "familySignals": signals,
    }
