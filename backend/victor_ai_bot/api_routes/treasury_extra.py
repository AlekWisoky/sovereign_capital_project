from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..auth import require_admin
from ..jsonsafe import to_json_safe as json_safe
from ..runtime import RuntimeBundle
from ..runtime_services.control_state import unavailable_state
from ..runtime_services.auxiliary_state_service import AuxiliaryStateService
from ..wealth_goals import (
    goal_patch_changes_state,
    goal_patch_requested,
    resolve_goal_patch_payload,
)
from ._route_helpers import (
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

router = APIRouter(tags=["treasury"])

_TREASURY_GOAL_ALLOWED_FIELDS = frozenset(
    {
        "target_return_percentage",
        "time_horizon_seconds",
        "risk_tolerance",
        "max_drawdown_pct",
        "capital_commitment_pct",
    }
)


def _treasury_unavailable(*, include_goal: bool = False) -> dict[str, object]:
    payload = unavailable_state(
        "treasury_disabled",
        include_error=True,
        extra={"enabled": False},
    )
    if include_goal:
        payload.setdefault("goal", None)
    return payload


def _treasury_goal_unavailable() -> dict[str, object]:
    return unavailable_state(
        "treasury_goal_unavailable",
        include_error=True,
        extra={"goal": None, "enabled": False},
    )


def _treasury_state_unavailable() -> dict[str, object]:
    return unavailable_state(
        "treasury_state_unavailable",
        include_error=True,
        extra={"enabled": False},
    )


def _capital_engine_unavailable() -> dict[str, object]:
    return unavailable_state("capital_engine_state_unavailable", include_error=True)


def _treasury_capital_failed_payload() -> dict[str, object]:
    return with_auto_trade_route_projection(
        degraded_payload("treasury_capital_failed"),
    )


def _treasury_state_failed_payload() -> dict[str, object]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "treasury_state_failed",
            extra={"enabled": False},
        ),
    )


def _treasury_goal_failed_payload() -> dict[str, object]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "treasury_goal_failed",
            extra={"goal": None, "enabled": False},
        ),
    )


def _invalid_set_goal_payload(payload: dict[str, object]) -> dict[str, object] | None:
    if not goal_patch_requested(payload):
        return invalid_request_payload("empty_goal_patch")

    unknown_fields = unexpected_request_fields(
        payload, allowed_fields=_TREASURY_GOAL_ALLOWED_FIELDS
    )
    if unknown_fields:
        return invalid_request_payload(
            "unknown_request_fields",
            details={"fields": unknown_fields},
        )

    for field in ("target_return_percentage", "max_drawdown_pct", "capital_commitment_pct"):
        if field not in payload:
            continue
        ok, _ = coerce_non_negative_float(payload[field])
        if not ok:
            return invalid_request_payload("invalid_float_value", field=field, value=payload[field])

    if "time_horizon_seconds" in payload:
        ok, _ = coerce_positive_int(payload["time_horizon_seconds"])
        if not ok:
            return invalid_request_payload(
                "invalid_integer_value",
                field="time_horizon_seconds",
                value=payload["time_horizon_seconds"],
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


def _goal_read_payload(goal: object) -> dict[str, object]:
    goal_payload = dict(getattr(goal, "__dict__", {}) or {})
    if not goal_payload:
        return _treasury_goal_unavailable()
    normalized = resolve_goal_patch_payload({}, current_goal=goal_payload)
    return {
        "ok": True,
        "status": "available",
        "canonical": True,
        "service": "treasury_goal_route",
        "goal": normalized,
    }


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/treasury/capital")
def treasury_capital(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(
            attach_summary_contract(
                AuxiliaryStateService().treasury_state(
                    rt, capital_truth=AuxiliaryStateService().capital_truth(rt)
                ),
                family="treasury_capital",
                read_model="treasury_capital_projection_v1",
                runtime=rt,
            ),
            runtime=rt,
        ),
        on_error=lambda exc: _treasury_capital_failed_payload(),
    )


@router.get("/api/treasury/state")
def treasury_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(
            attach_summary_contract(
                AuxiliaryStateService().treasury_state(
                    rt, capital_truth=AuxiliaryStateService().capital_truth(rt)
                ),
                family="treasury_state",
                read_model="treasury_state_projection_v1",
                runtime=rt,
            ),
            runtime=rt,
        ),
        on_error=lambda exc: _treasury_state_failed_payload(),
    )


@router.get("/api/treasury/goal")
def treasury_goal(rt=Depends(RuntimeBundle.dep)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(
            attach_summary_contract(
                (
                    _treasury_unavailable(include_goal=True)
                    if getattr(rt, "_treasury", None) is None
                    else _goal_read_payload(
                        getattr(getattr(rt._treasury, "cfg", None), "goal", None)
                    )
                ),
                family="treasury_goal",
                read_model="treasury_goal_projection_v1",
                runtime=rt,
            ),
            runtime=rt,
        ),
        on_error=lambda exc: _treasury_goal_failed_payload(),
    )


@router.post("/api/treasury/goal", dependencies=[Depends(require_admin)])
def set_treasury_goal(payload: dict[str, object], rt=Depends(RuntimeBundle.dep)):
    if getattr(rt, "_treasury", None) is None:
        return json_safe(_treasury_unavailable())

    rejected = _invalid_set_goal_payload(payload)
    if rejected is not None:
        return json_safe(rejected)

    try:
        g = rt._treasury.cfg.goal
        target_return_percentage = float(g.target_return_percentage)
        time_horizon_seconds = int(g.time_horizon_seconds)
        risk_tolerance = str(g.risk_tolerance)
        max_drawdown_pct = float(g.max_drawdown_pct)
        capital_commitment_pct = float(g.capital_commitment_pct)

        if "target_return_percentage" in payload:
            _, target_return_percentage = coerce_non_negative_float(
                payload["target_return_percentage"]
            )
        if "time_horizon_seconds" in payload:
            _, time_horizon_seconds = coerce_positive_int(payload["time_horizon_seconds"])
        if "risk_tolerance" in payload:
            _, risk_tolerance = coerce_non_empty_string(payload["risk_tolerance"])
        if "max_drawdown_pct" in payload:
            _, max_drawdown_pct = coerce_non_negative_float(payload["max_drawdown_pct"])
        if "capital_commitment_pct" in payload:
            _, capital_commitment_pct = coerce_non_negative_float(payload["capital_commitment_pct"])

        resolved = {
            "target_return_percentage": target_return_percentage,
            "time_horizon_seconds": time_horizon_seconds,
            "risk_tolerance": risk_tolerance,
            "max_drawdown_pct": max_drawdown_pct,
            "capital_commitment_pct": capital_commitment_pct,
        }
        if not goal_patch_changes_state(
            resolved, current_goal=dict(getattr(g, "__dict__", {}) or {})
        ):
            return json_safe({"ok": True, "goal": g.__dict__, "changed": False})

        g.target_return_percentage = target_return_percentage
        g.time_horizon_seconds = time_horizon_seconds
        g.risk_tolerance = risk_tolerance
        g.max_drawdown_pct = max_drawdown_pct
        g.capital_commitment_pct = capital_commitment_pct
        rt._treasury.cfg.goal = g
        rt._treasury._save_goal()
        return json_safe({"ok": True, "goal": g.__dict__, "changed": True})
    except (AttributeError, KeyError, TypeError, ValueError):
        return json_safe(
            {
                "ok": False,
                "status": "unavailable",
                "error": "set_goal_failed",
                "reason_code": "set_goal_failed",
                "reason": "set_goal_failed",
            }
        )
