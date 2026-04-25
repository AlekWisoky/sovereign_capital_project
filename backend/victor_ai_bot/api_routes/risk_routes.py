from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..jsonsafe import to_json_safe as json_safe
from ._route_helpers import (
    degraded_payload,
    safe_json_route_call,
    with_auto_trade_route_projection,
    attach_summary_contract,
)

router = APIRouter(tags=["risk"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/risk/cio-summary")
def cio_summary(rt=Depends(get_runtime)):
    svc = getattr(rt, "_cio_service", None)
    if svc is None:
        return json_safe({"ok": False, "reason": "cio_service_unavailable"})
    return json_safe(
        attach_summary_contract(
            {"ok": True, "summary": svc.summary(rt)},
            family="cio_route",
            read_model="cio_route_projection_v1",
            runtime=rt,
        )
    )


def _risk_live_state_defaults() -> Dict[str, Any]:
    return {
        "drawdown": {},
        "kill_switch": {"suppressed": []},
        "capital": {},
        "endpoint_quality": {},
        "endpoint_universe": {},
        "route_quality": {},
        "live_execution": {"items": []},
    }


def _risk_live_state_failed_payload() -> Dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "risk_live_state_failed",
            extra=_risk_live_state_defaults(),
        ),
        include_recent_events=True,
    )


def _optional_runtime_state(rt: Any, method_name: str, fallback: Dict[str, Any]) -> Dict[str, Any]:
    method = getattr(rt, method_name, None)
    if method is None:
        return dict(fallback)
    try:
        value = method()
    except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, NotImplementedError):
        return dict(fallback)
    return value if isinstance(value, dict) else dict(value or {})


def _risk_live_state_payload(rt: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": True, **_risk_live_state_defaults()}
    payload["drawdown"] = _optional_runtime_state(rt, "drawdown_state", {})
    payload["kill_switch"] = _optional_runtime_state(rt, "kill_switch_state", {"suppressed": []})
    payload["capital"] = _optional_runtime_state(rt, "capital_engine_state", {})
    payload["endpoint_quality"] = _optional_runtime_state(rt, "endpoint_quality_state", {})
    payload["endpoint_universe"] = _optional_runtime_state(rt, "endpoint_universe_state", {})
    payload["route_quality"] = _optional_runtime_state(rt, "route_quality_state", {})
    payload["live_execution"] = _optional_runtime_state(rt, "execution_live_state", {"items": []})
    return with_auto_trade_route_projection(
        attach_summary_contract(
            payload,
            family="risk_live_state",
            read_model="risk_live_state_projection_v1",
            runtime=rt,
        ),
        runtime=rt,
    )


@router.get("/api/risk/live-state")
def risk_live_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _risk_live_state_payload(rt),
        on_error=lambda exc: _risk_live_state_failed_payload(),
    )
