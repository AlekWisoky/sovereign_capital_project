from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import APIRouter, Body, Depends, Request

from ..jsonsafe import to_json_safe as json_safe
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import (
    coerce_finite_float,
    coerce_non_empty_string,
    invalid_request_payload,
    unexpected_request_fields,
    attach_summary_contract,
)

router = APIRouter(tags=["analytics"])


_ANALYTICS_DEFAULT_ROLE = "EXECUTIVE_VIEW"
_ANALYTICS_SCENARIO_ROLE = "RISK_MANAGER"
_ANALYTICS_ASK_ALLOWED_FIELDS = frozenset({"question"})
_ANALYTICS_SCENARIO_NUMERIC_FIELDS = frozenset(
    {
        "hypothetical_volatility_change",
        "capital_shift",
        "funding_rate_spike",
        "aggressiveness_adjustment",
    }
)


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def _analytics_state_payload(rt) -> dict:
    return (
        rt.quicksight_state()
        if hasattr(rt, "quicksight_state")
        else unavailable_state(
            "quicksight_unavailable",
            extra={"enabled": False},
            include_error=True,
        )
    )


def _analytics_dataset_payload(rt, name: str) -> dict:
    dataset = str(name)
    return (
        rt.quicksight_dataset(dataset)
        if hasattr(rt, "quicksight_dataset")
        else unavailable_state(
            "quicksight_unavailable",
            extra={"dataset": dataset, "rows": []},
            include_error=True,
        )
    )


def _analytics_dashboards_payload(rt) -> dict:
    return (
        rt.quicksight_dashboards()
        if hasattr(rt, "quicksight_dashboards")
        else unavailable_state(
            "quicksight_unavailable",
            extra={"dashboards": []},
            include_error=True,
        )
    )


def _analytics_query_unavailable_payload(*, extra: Dict[str, Any] | None = None) -> dict:
    return unavailable_state(
        "quicksight_unavailable",
        extra=dict(extra or {}),
        include_error=True,
    )


def _analytics_ask_payload(rt, *, question: str, role: str, token: str) -> dict:
    return (
        rt.quicksight_ask(question=question, role=role, token=token)
        if hasattr(rt, "quicksight_ask")
        else _analytics_query_unavailable_payload()
    )


def _analytics_scenario_payload(rt, *, params: Dict[str, Any], role: str, token: str) -> dict:
    return (
        rt.quicksight_scenario(params=dict(params or {}), role=role, token=token)
        if hasattr(rt, "quicksight_scenario")
        else _analytics_query_unavailable_payload()
    )


def _analytics_request_identity(request: Request, *, default_role: str) -> Tuple[str, str]:
    headers = getattr(request, "headers", None)
    if headers is None:
        return default_role, ""
    role = str(headers.get("X-Role", default_role) or default_role)
    token = str(headers.get("X-Role-Token", "") or "")
    return role, token


@router.get("/api/analytics/state")
def analytics_state(rt=Depends(get_runtime)):
    return json_safe(
        attach_summary_contract(
            _analytics_state_payload(rt),
            family="analytics_state",
            read_model="analytics_state_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/analytics/datasets/{name}")
def analytics_dataset(name: str, rt=Depends(get_runtime)):
    return json_safe(
        attach_summary_contract(
            _analytics_dataset_payload(rt, name),
            family="analytics_dataset",
            read_model="analytics_dataset_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/analytics/dashboards")
def analytics_dashboards(rt=Depends(get_runtime)):
    return json_safe(
        attach_summary_contract(
            _analytics_dashboards_payload(rt),
            family="analytics_dashboards",
            read_model="analytics_dashboards_projection_v1",
            runtime=rt,
        )
    )


@router.post("/api/analytics/ask")
def analytics_ask(request: Request, payload: Dict[str, Any] = Body(...), rt=Depends(get_runtime)):
    payload = dict(payload or {})
    unknown_fields = unexpected_request_fields(
        payload, allowed_fields=_ANALYTICS_ASK_ALLOWED_FIELDS
    )
    if unknown_fields:
        return json_safe(
            invalid_request_payload(
                "unknown_request_fields",
                details={"fields": unknown_fields},
            )
        )
    ok, question = coerce_non_empty_string(payload.get("question"))
    if not ok:
        return json_safe(
            invalid_request_payload(
                "empty_question",
                field="question",
                value=payload.get("question"),
            )
        )
    role, token = _analytics_request_identity(request, default_role=_ANALYTICS_DEFAULT_ROLE)
    return json_safe(_analytics_ask_payload(rt, question=question, role=role, token=token))


@router.post("/api/analytics/scenario")
def analytics_scenario(
    request: Request, payload: Dict[str, Any] = Body(...), rt=Depends(get_runtime)
):
    params = dict(payload or {})
    if not params:
        return json_safe(invalid_request_payload("empty_scenario_params"))
    for field in _ANALYTICS_SCENARIO_NUMERIC_FIELDS:
        if field not in params:
            continue
        ok, coerced = coerce_finite_float(params[field])
        if not ok:
            return json_safe(
                invalid_request_payload(
                    "invalid_float_value",
                    field=field,
                    value=params[field],
                )
            )
        params[field] = coerced
    role, token = _analytics_request_identity(request, default_role=_ANALYTICS_SCENARIO_ROLE)
    return json_safe(_analytics_scenario_payload(rt, params=params, role=role, token=token))
