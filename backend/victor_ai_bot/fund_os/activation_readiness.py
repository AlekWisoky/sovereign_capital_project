from __future__ import annotations

from typing import Any, Dict

from ..outcomes import LaunchDecision
from .family_readiness import build_family_readiness


def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        value_s = str(value or "")
        if value_s and value_s not in out:
            out.append(value_s)
    return out


def _specific_reason_codes(info: Dict[str, Any]) -> list[str]:
    return _unique(
        [
            *[str(x) for x in list(info.get("globalExecutionReasonCodes") or []) if str(x)],
            *[str(x) for x in list(info.get("familyHardeningReasonCodes") or []) if str(x)],
            *[str(x) for x in list(info.get("internalPrimeReasonCodes") or []) if str(x)],
            *[str(x) for x in list(info.get("receiptOutcomeTruthReasonCodes") or []) if str(x)],
            *[str(x) for x in list(info.get("capitalTruthReasonCodes") or []) if str(x)],
            *[str(x) for x in list(info.get("executionReasons") or []) if str(x)],
            *[str(x) for x in list(info.get("launchAccelerationReasonCodes") or []) if str(x)],
        ]
    )


def primary_readiness_reason(info: Dict[str, Any]) -> str:
    specifics = _specific_reason_codes(info)
    if specifics:
        return specifics[0]
    blockers = [str(x) for x in list(info.get("blockers") or []) if str(x)]
    if blockers:
        return blockers[0]
    reasons = [str(x) for x in list(info.get("reasons") or []) if str(x)]
    if reasons:
        return reasons[0]
    return "not_ready"


def blocked_readiness_codes(info: Dict[str, Any]) -> list[str]:
    return _unique(
        [
            *_specific_reason_codes(info),
            *[str(x) for x in list(info.get("blockers") or []) if str(x)],
            *[str(x) for x in list(info.get("reasons") or []) if str(x)],
        ]
    )


def activation_decision(
    *,
    family: str,
    stage: str,
    scorecards: Dict[str, Any],
    engine_state: Dict[str, Any],
    telemetry: Dict[str, Any],
    calibration: Dict[str, Any],
    fund_summary: Dict[str, Any],
    active_families: list[str],
    family_states: Dict[str, str] | None = None,
    exploration_budget: Dict[str, Any] | None = None,
    capital_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    info = build_family_readiness(
        family=family,
        stage=stage,
        scorecards=scorecards,
        engine_state=engine_state,
        telemetry=telemetry,
        calibration=calibration,
        fund_summary=fund_summary,
        active_families=active_families,
        family_states=family_states,
        exploration_budget=exploration_budget,
        capital_state=capital_state,
    )
    if not info["ready"]:
        blocked_by = blocked_readiness_codes(info)
        decision = LaunchDecision(
            allowed=False,
            reason_code=primary_readiness_reason(info),
            blocked_by=blocked_by,
            suggested_next_action=str(info.get("suggestedNextAction") or "continue_v1_learning"),
            degraded_mode=str(info.get("degradedState") or ""),
            details={"readiness": info},
        )
        return {
            "allowed": False,
            "reason_code": decision.reason_code,
            "blocked_by": decision.blocked_by,
            "suggested_next_action": decision.suggested_next_action,
            "degraded_mode": decision.degraded_mode,
            "capital_truth_reason_codes": list(info.get("capitalTruthReasonCodes") or []),
            "receipt_outcome_truth_reason_codes": list(
                info.get("receiptOutcomeTruthReasonCodes") or []
            ),
            "global_execution_reason_codes": list(info.get("globalExecutionReasonCodes") or []),
            "internal_prime_reason_codes": list(info.get("internalPrimeReasonCodes") or []),
            "readiness": info,
        }
    decision = LaunchDecision(
        allowed=True,
        reason_code="ready",
        blocked_by=[],
        suggested_next_action="activate_family",
        degraded_mode=str(info.get("degradedState") or ""),
        details={"readiness": info},
    )
    return {
        "allowed": True,
        "reason_code": decision.reason_code,
        "blocked_by": [],
        "suggested_next_action": decision.suggested_next_action,
        "degraded_mode": decision.degraded_mode,
        "capital_truth_reason_codes": list(info.get("capitalTruthReasonCodes") or []),
        "global_execution_reason_codes": list(info.get("globalExecutionReasonCodes") or []),
        "internal_prime_reason_codes": list(info.get("internalPrimeReasonCodes") or []),
        "readiness": info,
    }
