from __future__ import annotations

from typing import Any, Dict

from ..fund_os.family_identity import canonical_launch_family_id
from ..fund_os.health_states import HealthState
from ..outcomes import GovernanceOutcome
from ..runtime_services.auxiliary_state_service import AuxiliaryStateService


_LAUNCH_CONTEXT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _safe_runtime_mapping(runtime: Any, method_name: str) -> Dict[str, Any]:
    method = getattr(runtime, method_name, None)
    if not callable(method):
        return {}
    try:
        payload = method()
    except _LAUNCH_CONTEXT_FAILURES:
        return {}
    return dict(payload or {}) if isinstance(payload, dict) else {}


def build_launch_context(runtime: Any) -> Dict[str, Any]:
    state = getattr(runtime, "fund_summary_state", lambda: {})() or {}
    stage = (
        str(
            (state.get("health") or state).get("fundStage")
            if isinstance(state, dict)
            else "internal_capital"
        )
        or "internal_capital"
    )
    return {
        "stage": stage,
        "scorecards": _safe_runtime_mapping(runtime, "strategy_scorecards_state"),
        "engine_state": _safe_runtime_mapping(runtime, "engine_state"),
        "telemetry": _safe_runtime_mapping(runtime, "telemetry_summary"),
        "calibration": _safe_runtime_mapping(runtime, "execution_calibration_state"),
        "fund_summary": (
            state.get("health")
            if isinstance(state, dict) and isinstance(state.get("health"), dict)
            else state
        ),
        "capital_state": _safe_runtime_mapping(runtime, "capital_engine_state"),
    }


def guard_launch_mutation(*, runtime: Any, family: str, action: str) -> GovernanceOutcome:
    family = canonical_launch_family_id(str(family or ""))
    aux = AuxiliaryStateService()
    capital_policy = aux.capital_policy(runtime)
    rollout = getattr(runtime, "_launch_rollout", None)
    if rollout is None:
        return GovernanceOutcome(
            allowed=False, reason_code="launch_rollout_unavailable", review_required=False
        )
    if not family and action not in {"set_mode", "enable_next"}:
        return GovernanceOutcome(
            allowed=False, reason_code="family_required", review_required=False
        )

    known_families = {canonical_launch_family_id(str(x or "")) for x in (getattr(getattr(rollout, "profile", None), "rollout_order", []) or [])}
    known_families.update(
        {canonical_launch_family_id(str(x or "")) for x in (getattr(getattr(rollout, "profile", None), "family_states", {}).keys() or [])}
    )
    if family and known_families and family not in known_families:
        return GovernanceOutcome(allowed=False, reason_code="unknown_family", review_required=False)

    controls = getattr(getattr(runtime, "_cc", None), "controls", None)
    if action == "enable_next":
        launch_policy = dict((capital_policy or {}).get("launch") or {}) if isinstance(capital_policy, dict) else {}
        if launch_policy and not bool(launch_policy.get("enableAllowed", True)):
            blockers = list(launch_policy.get("enableBlockers") or [])
            return GovernanceOutcome(allowed=False, reason_code=str(blockers[0] if blockers else "capital_nav_unavailable"), review_required=False)
        if controls is not None and bool(getattr(controls, "paused", False)):
            return GovernanceOutcome(
                allowed=False, reason_code="command_center_paused", review_required=False
            )
        if controls is not None and bool(getattr(controls, "allocations_frozen", False)):
            return GovernanceOutcome(
                allowed=False, reason_code="allocations_frozen", review_required=False
            )
        family_states = {canonical_launch_family_id(str(k or "")): v for k, v in (getattr(getattr(rollout, "profile", None), "family_states", {}) or {}).items()}
        if family and str(family_states.get(family) or "") == HealthState.QUARANTINED.value:
            return GovernanceOutcome(
                allowed=False, reason_code="family_quarantined", review_required=True
            )

    if action == "set_mode":
        launch_policy = dict((capital_policy or {}).get("launch") or {}) if isinstance(capital_policy, dict) else {}
        if launch_policy and not bool(launch_policy.get("modeChangeAllowed", True)):
            blockers = list(launch_policy.get("modeChangeBlockers") or [])
            return GovernanceOutcome(allowed=False, reason_code=str(blockers[0] if blockers else "capital_nav_unavailable"), review_required=False)
    return GovernanceOutcome(allowed=True, reason_code="allowed", review_required=False)


def format_launch_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return dict(summary or {})
