from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime_services.control_state import unavailable_state
from ..runtime import MultiRuntimeBundle
from ._route_helpers import (
    attach_summary_contract,
    coerce_non_empty_string,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
)

router = APIRouter(tags=["superstructure"])


def _reject_unknown_fields(
    payload: Dict[str, Any], *, allowed_fields: frozenset[str]
) -> Dict[str, Any] | None:
    unknown_fields = unexpected_request_fields(payload, allowed_fields=allowed_fields)
    if not unknown_fields:
        return None
    return invalid_request_payload(
        "unknown_request_fields",
        details={"fields": unknown_fields, "allowed_fields": sorted(allowed_fields)},
    )


def _disabled_unavailable(**extra: Any) -> Dict[str, Any]:
    payload = {"enabled": False}
    payload.update(extra)
    return unavailable_state("unavailable", extra=payload)


def _error_unavailable() -> Dict[str, Any]:
    return unavailable_state("unavailable", include_reason=False, include_error=True)


def _superstructure_read_failed_payload(
    reason_code: str,
    *,
    runtime: Any | None = None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    family = "superstructure_state"
    read_model = "superstructure_state_projection_v1"
    if reason_code == "superstructure_stability_failed":
        family = "superstructure_stability"
        read_model = "superstructure_stability_projection_v1"
    elif reason_code == "governance_state_legacy_failed":
        family = "governance_legacy"
        read_model = "governance_legacy_projection_v1"
    elif reason_code == "governance_health_failed":
        family = "governance_health"
        read_model = "governance_health_projection_v1"
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload(reason_code, extra=extra),
            runtime=runtime,
        ),
        family=family,
        read_model=read_model,
        runtime=runtime,
    )


def get_runtime(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    if isinstance(rt, MultiRuntimeBundle):
        return rt._runtimes.get(rt._active_chain) or rt
    return rt


@router.get("/api/org/state")
async def org_state(request: Request):
    rt = get_runtime(request)

    def _payload() -> Dict[str, Any]:
        if hasattr(rt, "superstructure_state"):
            return attach_summary_contract(
                with_auto_trade_route_projection(rt.superstructure_state(), runtime=rt),
                family="superstructure_state",
                read_model="superstructure_state_projection_v1",
                runtime=rt,
            )
        return attach_summary_contract(
            with_auto_trade_route_projection(_disabled_unavailable(), runtime=rt),
            family="superstructure_state",
            read_model="superstructure_state_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: _superstructure_read_failed_payload(
            "superstructure_state_failed",
            runtime=rt,
            extra={"enabled": False},
        ),
    )


@router.post("/api/org/agent/pause", dependencies=[Depends(require_admin)])
async def org_pause_agent(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"agent_id"}))
    if rejected is not None:
        return json_safe(rejected)
    if "agent_id" not in payload:
        return json_safe(invalid_request_payload("missing_agent_id", field="agent_id"))
    ok, agent_id = coerce_non_empty_string(payload.get("agent_id"))
    if not ok:
        return json_safe(
            invalid_request_payload(
                "invalid_string_value",
                field="agent_id",
                value=payload.get("agent_id"),
            )
        )
    if hasattr(rt, "superstructure_pause"):
        ok = bool(rt.superstructure_pause(agent_id))
        return json_safe({"ok": ok})
    return json_safe(_error_unavailable())


@router.post("/api/org/agent/resume", dependencies=[Depends(require_admin)])
async def org_resume_agent(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"agent_id"}))
    if rejected is not None:
        return json_safe(rejected)
    if "agent_id" not in payload:
        return json_safe(invalid_request_payload("missing_agent_id", field="agent_id"))
    ok, agent_id = coerce_non_empty_string(payload.get("agent_id"))
    if not ok:
        return json_safe(
            invalid_request_payload(
                "invalid_string_value",
                field="agent_id",
                value=payload.get("agent_id"),
            )
        )
    if hasattr(rt, "superstructure_resume"):
        ok = bool(rt.superstructure_resume(agent_id))
        return json_safe({"ok": ok})
    return json_safe(_error_unavailable())


@router.get("/api/org/stability")
async def org_stability(request: Request):
    rt = get_runtime(request)

    def _payload() -> Dict[str, Any]:
        if hasattr(rt, "superstructure_state"):
            st = rt.superstructure_state()
            return attach_summary_contract(
                with_auto_trade_route_projection(
                    {"ok": True, "stability": (st.get("stability") or {})},
                    runtime=rt,
                ),
                family="superstructure_stability",
                read_model="superstructure_stability_projection_v1",
                runtime=rt,
            )
        return attach_summary_contract(
            with_auto_trade_route_projection(_disabled_unavailable(), runtime=rt),
            family="superstructure_stability",
            read_model="superstructure_stability_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: _superstructure_read_failed_payload(
            "superstructure_stability_failed",
            runtime=rt,
            extra={"enabled": False, "stability": {}},
        ),
    )


@router.get("/api/governance/state_legacy")
async def governance_state_legacy(request: Request):
    rt = get_runtime(request)

    def _payload() -> Dict[str, Any]:
        if hasattr(rt, "governance_state"):
            return attach_summary_contract(
                with_auto_trade_route_projection(rt.governance_state(), runtime=rt),
                family="governance_legacy",
                read_model="governance_legacy_projection_v1",
                runtime=rt,
            )
        return attach_summary_contract(
            with_auto_trade_route_projection(_disabled_unavailable(), runtime=rt),
            family="governance_legacy",
            read_model="governance_legacy_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: _superstructure_read_failed_payload(
            "governance_state_legacy_failed",
            runtime=rt,
            extra={"enabled": False},
        ),
    )


@router.get("/api/governance/health")
async def governance_health(request: Request):
    rt = get_runtime(request)

    def _payload() -> Dict[str, Any]:
        if hasattr(rt, "governance_health"):
            return attach_summary_contract(
                with_auto_trade_route_projection(rt.governance_health(), runtime=rt),
                family="governance_health",
                read_model="governance_health_projection_v1",
                runtime=rt,
            )
        return attach_summary_contract(
            with_auto_trade_route_projection(_disabled_unavailable(), runtime=rt),
            family="governance_health",
            read_model="governance_health_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: _superstructure_read_failed_payload(
            "governance_health_failed",
            runtime=rt,
            extra={"enabled": False},
        ),
    )
