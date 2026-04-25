from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..api import get_runtime
from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import (
    attach_summary_contract,
    coerce_non_empty_string,
    coerce_non_negative_float,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
)

router = APIRouter(tags=["operator-command"])


def _runtime_method_result(
    runtime: Any, method_name: str, *args: Any, **kwargs: Any
) -> Dict[str, Any]:
    method = getattr(runtime, method_name, None)
    if method is None:
        return unavailable_state("unavailable", include_reason=False, include_error=True)
    return {"ok": bool(method(*args, **kwargs))}


def _disabled_unavailable() -> Dict[str, Any]:
    return unavailable_state("unavailable", extra={"enabled": False})


def _command_state_unavailable(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(_disabled_unavailable(), runtime=runtime),
        family="operator_command_state",
        read_model="operator_command_state_projection_v1",
        runtime=runtime,
    )


def _command_state_failed_payload(runtime: Any | None = None) -> Dict[str, Any]:
    return attach_summary_contract(
        with_auto_trade_route_projection(
            degraded_payload("command_state_route_failed", extra={"enabled": False}),
            runtime=runtime,
        ),
        family="operator_command_state",
        read_model="operator_command_state_projection_v1",
        runtime=runtime,
    )


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


def _coerce_non_negative_float_payload(
    payload: Dict[str, Any],
    *,
    field: str,
    default: float,
) -> tuple[bool, Dict[str, Any] | None, float]:
    raw_value = payload.get(field, default)
    ok, coerced = coerce_non_negative_float(raw_value)
    if ok:
        return True, None, coerced
    return False, invalid_request_payload("invalid_float_value", field=field, value=raw_value), 0.0


def _coerce_mapping_payload(
    payload: Dict[str, Any],
    *,
    field: str,
    default: Dict[str, Any] | None = None,
    allow_none: bool = False,
) -> tuple[bool, Dict[str, Any] | None, Dict[str, Any]]:
    raw_value = payload.get(field, default if default is not None else {})
    if raw_value is None:
        if field in payload and not allow_none:
            return (
                False,
                invalid_request_payload("invalid_mapping_value", field=field, value=raw_value),
                {},
            )
        return True, None, {}
    if isinstance(raw_value, Mapping):
        return True, None, dict(raw_value)
    return False, invalid_request_payload("invalid_mapping_value", field=field, value=raw_value), {}


def _reject_empty_payload(
    payload: Dict[str, Any],
    *,
    required_any_of: frozenset[str],
) -> Dict[str, Any] | None:
    if any(field in payload for field in required_any_of):
        return None
    return invalid_request_payload(
        "empty_command_payload",
        details={"required_any_of": sorted(required_any_of)},
    )


@router.get("/api/command/state")
async def command_state(request: Request):
    runtime = get_runtime(request)

    def _payload() -> Dict[str, Any]:
        if hasattr(runtime, "superstructure_command_state"):
            return attach_summary_contract(
                with_auto_trade_route_projection(
                    runtime.superstructure_command_state(), runtime=runtime
                ),
                family="operator_command_state",
                read_model="operator_command_state_projection_v1",
                runtime=runtime,
            )
        return _command_state_unavailable(runtime)

    return safe_json_route_call(
        _payload,
        on_error=lambda exc: _command_state_failed_payload(runtime),
    )


@router.post("/api/command/directive", dependencies=[Depends(require_admin)])
async def command_set_directive(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    rejected = _reject_unknown_fields(
        payload, allowed_fields=frozenset({"directive", "payload", "ttl_s"})
    )
    if rejected is not None:
        return json_safe(rejected)
    rejected = _reject_empty_payload(payload, required_any_of=frozenset({"directive", "payload"}))
    if rejected is not None:
        return json_safe(rejected)
    directive_field = (
        "directive"
        if "directive" in payload
        else ("payload" if "payload" in payload else "directive")
    )
    ok, rejected, directive = _coerce_mapping_payload(
        payload, field=directive_field, default={}, allow_none=False
    )
    if not ok:
        return json_safe(rejected)
    ok, rejected, ttl_s = _coerce_non_negative_float_payload(
        payload, field="ttl_s", default=6 * 3600.0
    )
    if not ok:
        return json_safe(rejected)
    return json_safe(
        _runtime_method_result(
            runtime,
            "superstructure_set_directive",
            directive,
            ttl_s=ttl_s,
        )
    )


@router.post("/api/command/risk_multiplier", dependencies=[Depends(require_admin)])
async def command_set_risk_multiplier(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"risk_multiplier"}))
    if rejected is not None:
        return json_safe(rejected)
    rejected = _reject_empty_payload(payload, required_any_of=frozenset({"risk_multiplier"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, multiplier = _coerce_non_negative_float_payload(
        payload, field="risk_multiplier", default=1.0
    )
    if not ok:
        return json_safe(rejected)
    return json_safe(
        _runtime_method_result(runtime, "superstructure_set_risk_multiplier", multiplier)
    )


@router.post("/api/command/exploration_cap", dependencies=[Depends(require_admin)])
async def command_set_exploration_cap(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"exploration_cap"}))
    if rejected is not None:
        return json_safe(rejected)
    rejected = _reject_empty_payload(payload, required_any_of=frozenset({"exploration_cap"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, exploration_cap = _coerce_non_negative_float_payload(
        payload, field="exploration_cap", default=1.0
    )
    if not ok:
        return json_safe(rejected)
    return json_safe(
        _runtime_method_result(runtime, "superstructure_set_exploration_cap", exploration_cap)
    )


@router.post("/api/command/approve", dependencies=[Depends(require_admin)])
async def command_approve(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"proposal_id", "ttl_s"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, proposal_id = True, None, ""
    if "proposal_id" in payload:
        ok, proposal_id = coerce_non_empty_string(payload.get("proposal_id"))
        if not ok:
            rejected = invalid_request_payload(
                "invalid_string_value",
                field="proposal_id",
                value=payload.get("proposal_id"),
            )
    if not ok:
        return json_safe(rejected)
    ok, rejected, ttl_s = _coerce_non_negative_float_payload(payload, field="ttl_s", default=600.0)
    if not ok:
        return json_safe(rejected)
    if not proposal_id:
        return json_safe(invalid_request_payload("missing_proposal_id", field="proposal_id"))
    return json_safe(
        _runtime_method_result(
            runtime,
            "superstructure_approve",
            proposal_id,
            ttl_s=ttl_s,
        )
    )


@router.post("/api/command/force_safe_mode", dependencies=[Depends(require_admin)])
async def command_force_safe_mode(request: Request, payload: Dict[str, Any] = Body(...)):
    runtime = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"ttl_s", "reason"}))
    if rejected is not None:
        return json_safe(rejected)
    rejected = _reject_empty_payload(payload, required_any_of=frozenset({"ttl_s", "reason"}))
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, ttl_s = _coerce_non_negative_float_payload(payload, field="ttl_s", default=120.0)
    if not ok:
        return json_safe(rejected)
    if "reason" in payload:
        ok, reason = coerce_non_empty_string(payload.get("reason"))
        if not ok:
            return json_safe(
                invalid_request_payload(
                    "invalid_string_value",
                    field="reason",
                    value=payload.get("reason"),
                )
            )
    else:
        reason = "human_force_safe_mode"
    return json_safe(
        _runtime_method_result(
            runtime,
            "superstructure_force_safe_mode",
            ttl_s=ttl_s,
            reason=reason,
        )
    )
