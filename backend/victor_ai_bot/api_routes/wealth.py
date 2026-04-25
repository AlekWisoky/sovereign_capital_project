from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime import MultiRuntimeBundle
from ..runtime_services.control_state import unavailable_state
from ..wealth_goals import (
    goal_patch_changes_state,
    goal_patch_requested,
    recommend_goal,
    resolve_goal_patch_payload,
)
from ._route_helpers import (
    append_optional_audit,
    coerce_non_empty_string,
    coerce_non_negative_float,
    coerce_positive_int,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
    attach_summary_contract,
)

router = APIRouter(prefix="/api/wealth", tags=["wealth"])

_GOAL_ALLOWED_FIELDS = frozenset(
    {
        "target_return_percentage",
        "target_return_pct",
        "time_horizon_seconds",
        "timeframe_days",
        "risk_tolerance",
        "max_drawdown_pct",
        "capital_commitment_pct",
        "reason",
    }
)


def _treasury_unavailable(*, include_goal: bool = False):
    payload = unavailable_state(
        "treasury_disabled",
        include_error=True,
        extra={"enabled": False},
    )
    if include_goal:
        payload.setdefault("goal", None)
    return payload


def _goal_unavailable(reason_code: str) -> Dict[str, Any]:
    return unavailable_state(
        str(reason_code),
        include_error=True,
        extra={
            "goal": None,
            "state": {},
            "recommendation": {},
            "explanation": {},
            "history": [],
            "service": "wealth_goal_fallback",
            "canonical": True,
        },
    )


def _active_runtime(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


def _reject_unknown_goal_fields(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    unknown_fields = unexpected_request_fields(payload, allowed_fields=_GOAL_ALLOWED_FIELDS)
    if not unknown_fields:
        return None
    return invalid_request_payload(
        "unknown_request_fields",
        details={"fields": unknown_fields},
    )


def _validate_goal_patch_payload(payload: Dict[str, Any]) -> Dict[str, Any] | None:
    rejected = _reject_unknown_goal_fields(payload)
    if rejected is not None:
        return rejected

    if not goal_patch_requested(payload):
        return invalid_request_payload("empty_goal_patch")

    for field in (
        "target_return_percentage",
        "target_return_pct",
        "max_drawdown_pct",
        "capital_commitment_pct",
    ):
        if field not in payload:
            continue
        ok, _ = coerce_non_negative_float(payload[field])
        if not ok:
            return invalid_request_payload("invalid_float_value", field=field, value=payload[field])

    for field in ("time_horizon_seconds", "timeframe_days"):
        if field not in payload:
            continue
        ok, _ = coerce_positive_int(payload[field])
        if not ok:
            return invalid_request_payload(
                "invalid_integer_value", field=field, value=payload[field]
            )

    if "risk_tolerance" in payload:
        ok, _ = coerce_non_empty_string(payload["risk_tolerance"])
        if not ok:
            return invalid_request_payload(
                "invalid_string_value",
                field="risk_tolerance",
                value=payload["risk_tolerance"],
            )

    return None


def _normalized_goal_payload(goal: Any) -> Dict[str, Any]:
    current_goal = dict(getattr(goal, "__dict__", {}) or {}) if goal is not None else {}
    if not current_goal:
        return {}
    return resolve_goal_patch_payload({}, current_goal=current_goal)


def _wealth_goal_failed_payload(runtime: Any | None = None) -> Dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "wealth_goal_failed",
            extra={
                "goal": None,
                "state": {},
                "recommendation": {},
                "explanation": {},
                "history": [],
                "service": "wealth_goal_route",
            },
        ),
        runtime=runtime,
    )


def _build_fallback_goal_read_payload(rt: Any, goal: Any) -> Dict[str, Any]:
    goal_payload = _normalized_goal_payload(goal)
    if not goal_payload:
        return _goal_unavailable("treasury_goal_unavailable")

    snap = rt._treasury.snapshot() if hasattr(rt._treasury, "snapshot") else {}
    ag = (snap.get("aggressiveness") or {}) if isinstance(snap, dict) else {}
    current_return_pct = float(ag.get("current_return_pct") or 0.0)
    target_return_pct = float(goal_payload.get("target_return_percentage") or 0.0)
    timeframe_days = int(goal_payload.get("timeframe_days") or 30)
    progress_pct = (
        0.0
        if target_return_pct <= 0.0
        else max(
            0.0,
            min(200.0, (current_return_pct / max(target_return_pct, 0.001)) * 100.0),
        )
    )
    goal_status = (
        "achieved"
        if target_return_pct > 0.0 and current_return_pct >= target_return_pct
        else "active"
    )
    rec = recommend_goal(
        current_return_pct=current_return_pct,
        risk_tolerance=str(goal_payload.get("risk_tolerance") or "moderate"),
        previous_target_pct=target_return_pct,
    )
    goal_view = dict(goal_payload)
    goal_view["goal_status"] = goal_status
    return {
        "ok": True,
        "status": "available",
        "canonical": True,
        "service": "wealth_goal_fallback",
        "goal": goal_view,
        "state": {
            "currentReturnPct": current_return_pct,
            "progressPct": round(progress_pct, 2),
            "goalAchieved": goal_status == "achieved",
            "goalStatus": goal_status,
            "targetReturnPct": target_return_pct,
            "timeframeDays": timeframe_days,
            "riskTolerance": str(goal_payload.get("risk_tolerance") or "moderate"),
            "maxDrawdownPct": float(goal_payload.get("max_drawdown_pct") or 10.0),
            "capitalCommitmentPct": float(goal_payload.get("capital_commitment_pct") or 25.0),
            "suggestedNextTargetPct": float(rec.get("target_return_pct") or target_return_pct),
            "nextGoalAllowed": True,
            "goalUrgency": "steady" if goal_status == "active" else "unlock_next_goal",
        },
        "current_return_pct": current_return_pct,
        "recommendation": rec,
        "explanation": {
            "why_active_goal": (
                f"Active goal targets {target_return_pct:.2f}% over {timeframe_days} days "
                f"with {str(goal_payload.get('risk_tolerance') or 'moderate')} risk tolerance."
            ),
            "why_posture": (
                f"Current return is {current_return_pct:.2f}% and progress is {progress_pct:.2f}% "
                "against the active wealth goal."
            ),
            "why_next_goal": (
                f"Next-goal suggestion is {float(rec.get('target_return_pct') or target_return_pct):.2f}% "
                "based on current return and configured risk tolerance."
            ),
            "why_not_larger": "Fallback wealth goal view does not widen targets beyond bounded recommendation logic.",
        },
        "history": [],
    }


@router.get("/goal")
def get_goal(request: Request):
    rt = _active_runtime(request)

    def _payload() -> Dict[str, Any]:
        if getattr(rt, "_treasury", None) is None:
            return with_auto_trade_route_projection(
                attach_summary_contract(
                    _treasury_unavailable(include_goal=True),
                    family="wealth_goal",
                    read_model="wealth_goal_projection_v1",
                    runtime=rt,
                ),
                runtime=rt,
            )
        if getattr(rt, "_wealth_goal_service", None) is not None:
            state = rt._wealth_goal_service.state(rt)
            if not isinstance(state, dict):
                raise TypeError("wealth_goal_state_invalid")
            state.setdefault("canonical", True)
            state.setdefault("service", "wealth_goal_service")
            if bool(state.get("ok", False)):
                state.setdefault("status", "available")
            return with_auto_trade_route_projection(
                attach_summary_contract(
                    state,
                    family="wealth_goal",
                    read_model="wealth_goal_projection_v1",
                    runtime=rt,
                ),
                runtime=rt,
            )
        goal = getattr(getattr(rt._treasury, "cfg", None), "goal", None)
        return with_auto_trade_route_projection(
            attach_summary_contract(
                _build_fallback_goal_read_payload(rt, goal),
                family="wealth_goal",
                read_model="wealth_goal_projection_v1",
                runtime=rt,
            ),
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda exc: _wealth_goal_failed_payload(rt),
    )


@router.post("/goal", dependencies=[Depends(require_admin)])
def set_goal(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = _active_runtime(request)
    if getattr(rt, "_treasury", None) is None:
        return json_safe(_treasury_unavailable(include_goal=True))

    rejected = _validate_goal_patch_payload(payload)
    if rejected is not None:
        return json_safe(rejected)

    if getattr(rt, "_wealth_goal_service", None) is not None:
        actor = "operator"
        reason = str(payload.get("reason") or "")
        state = rt._wealth_goal_service.set_goal(rt, payload, actor=actor, reason=reason)
        if isinstance(state, dict):
            state.setdefault("canonical", True)
            state.setdefault("service", "wealth_goal_service")
        if (
            isinstance(state, dict)
            and bool(state.get("ok", False))
            and bool(state.get("changed", True))
        ):
            append_optional_audit(
                getattr(getattr(rt, "_cc", None), "audit", None),
                "wealth_goal_update",
                {"goal": state.get("goal")},
                actor=actor,
                reason=reason,
            )
        return json_safe(state)

    goal = rt._treasury.cfg.goal
    current_goal = dict(getattr(goal, "__dict__", {}) or {})
    resolved = resolve_goal_patch_payload(payload, current_goal=current_goal)
    if not goal_patch_changes_state(resolved, current_goal=current_goal):
        return json_safe(
            {
                "ok": True,
                "goal": goal.__dict__,
                "recommendation": recommend_goal(
                    current_return_pct=0.0,
                    risk_tolerance=goal.risk_tolerance,
                    previous_target_pct=goal.target_return_percentage,
                ),
                "changed": False,
            }
        )
    goal.target_return_percentage = float(resolved["target_return_percentage"])
    goal.time_horizon_seconds = int(resolved["time_horizon_seconds"])
    goal.risk_tolerance = str(resolved["risk_tolerance"])
    goal.max_drawdown_pct = float(resolved["max_drawdown_pct"])
    goal.capital_commitment_pct = float(resolved["capital_commitment_pct"])
    rt._treasury.cfg.goal = goal
    rt._treasury._save_goal()
    append_optional_audit(
        getattr(getattr(rt, "_cc", None), "audit", None),
        "wealth_goal_update",
        {"goal": goal.__dict__},
        actor="operator",
        reason=str(payload.get("reason") or ""),
    )
    return json_safe(
        {
            "ok": True,
            "goal": goal.__dict__,
            "recommendation": recommend_goal(
                current_return_pct=0.0,
                risk_tolerance=goal.risk_tolerance,
                previous_target_pct=goal.target_return_percentage,
            ),
            "changed": True,
        }
    )
