from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Mapping

from ..research_pipeline.workspace import ResearchWorkspace

from fastapi import APIRouter, Body, Depends, Header, Request

from ..jsonsafe import to_json_safe as json_safe
from ..research_pipeline.candidates import _ALLOWED as _ALLOWED_RESEARCH_STAGES
from ..runtime_services.control_state import unavailable_state
from ..runtime_services.fund_service import fund_summary_unavailable_payload
from ..runtime_services.family_hardening_service import family_hardening_unavailable_summary
from ..security.auth import require_capability
from ..security.permissions import Capability
from ._route_helpers import (
    coerce_finite_float,
    coerce_non_empty_string,
    coerce_non_negative_int,
    attach_summary_contract,
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
)

router = APIRouter(tags=["fund"])


_FUND_ROUTE_COMPONENT_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


_NON_SUCCESS_COMPONENT_STATUSES = frozenset(
    {
        "blocked",
        "degraded",
        "denied",
        "error",
        "execute_failed",
        "failed",
        "invalid",
        "receipt_unavailable",
        "unavailable",
    }
)


_CANDIDATE_STORE_RUNTIME_FAILURES = (
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _reject_unknown_fields(
    payload: dict[str, Any], *, allowed_fields: frozenset[str]
) -> dict[str, Any] | None:
    unknown_fields = unexpected_request_fields(payload, allowed_fields=allowed_fields)
    if not unknown_fields:
        return None
    return invalid_request_payload(
        "unknown_request_fields",
        details={"fields": unknown_fields, "allowed_fields": sorted(allowed_fields)},
    )


def _coerce_optional_string(
    payload: dict[str, Any],
    *,
    field: str,
    default: str = "",
) -> tuple[bool, dict[str, Any] | None, str]:
    if field not in payload:
        return True, None, default
    ok, value = coerce_non_empty_string(payload.get(field))
    if ok:
        return True, None, value
    return (
        False,
        invalid_request_payload("invalid_string_value", field=field, value=payload.get(field)),
        "",
    )


def _coerce_required_string(
    payload: dict[str, Any],
    *,
    field: str,
) -> tuple[bool, dict[str, Any] | None, str]:
    if field not in payload:
        return False, invalid_request_payload(f"missing_{field}", field=field), ""
    ok, value = coerce_non_empty_string(payload.get(field))
    if ok:
        return True, None, value
    return (
        False,
        invalid_request_payload("invalid_string_value", field=field, value=payload.get(field)),
        "",
    )


def _coerce_optional_mapping(
    payload: dict[str, Any],
    *,
    field: str,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any]]:
    if field not in payload:
        return True, None, {}
    value = payload.get(field)
    if isinstance(value, ABCMapping):
        return True, None, dict(value)
    return False, invalid_request_payload("invalid_mapping_value", field=field, value=value), {}


def _coerce_optional_non_negative_int(
    payload: dict[str, Any],
    *,
    field: str,
) -> tuple[bool, dict[str, Any] | None, int | None]:
    if field not in payload:
        return True, None, None
    ok, value = coerce_non_negative_int(payload.get(field))
    if ok:
        return True, None, value
    return (
        False,
        invalid_request_payload("invalid_integer_value", field=field, value=payload.get(field)),
        None,
    )


def _coerce_optional_non_negative_float(
    payload: dict[str, Any],
    *,
    field: str,
) -> tuple[bool, dict[str, Any] | None, float | None]:
    if field not in payload:
        return True, None, None
    ok, value = coerce_finite_float(payload.get(field))
    if ok and value >= 0.0:
        return True, None, value
    return (
        False,
        invalid_request_payload("invalid_float_value", field=field, value=payload.get(field)),
        None,
    )


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def _runtime_component_payload(
    rt,
    *,
    method_name: str,
    unavailable_reason: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not hasattr(rt, method_name):
        return unavailable_state(unavailable_reason, extra=extra)
    try:
        payload = getattr(rt, method_name)()
    except _FUND_ROUTE_COMPONENT_FAILURES:
        return unavailable_state(unavailable_reason, extra=extra)
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return unavailable_state(unavailable_reason, extra=extra)


def _capital_truth_payload(rt) -> dict:
    return _runtime_component_payload(
        rt,
        method_name="capital_truth_state",
        unavailable_reason="capital_truth_unavailable",
    )


def _family_hardening_payload(rt) -> dict:
    if not hasattr(rt, "family_hardening_state"):
        return family_hardening_unavailable_summary()
    try:
        payload = rt.family_hardening_state()
    except _FUND_ROUTE_COMPONENT_FAILURES:
        return family_hardening_unavailable_summary()
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return family_hardening_unavailable_summary()


def _doctrine_payload(rt) -> dict:
    return _runtime_component_payload(
        rt,
        method_name="doctrine_state",
        unavailable_reason="doctrine_unavailable",
        extra={"optimizationObjectives": {}},
    )


def _ledger_payload(rt) -> dict:
    return _runtime_component_payload(
        rt,
        method_name="ledger_state",
        unavailable_reason="ledger_unavailable",
        extra={"balances": {}, "tail": [], "transactions": []},
    )


def _internal_prime_payload(rt) -> dict:
    return _runtime_component_payload(
        rt,
        method_name="internal_prime_state",
        unavailable_reason="internal_prime_unavailable",
        extra={
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "loanCount": 0,
        },
    )


def _research_pipeline_payload(rt) -> dict:
    if hasattr(rt, "research_pipeline_state"):
        try:
            payload = rt.research_pipeline_state()
        except _FUND_ROUTE_COMPONENT_FAILURES:
            payload = None
        if isinstance(payload, ABCMapping):
            return dict(payload)
    try:
        cfg = getattr(rt, "cfg", None)
        chain_obj = getattr(cfg, "chain", None)
        workspace = ResearchWorkspace(
            data_dir=str(getattr(rt, "data_dir", "data")),
            chain=str(getattr(chain_obj, "name", None) or "default"),
        ).snapshot()
        if isinstance(workspace, ABCMapping):
            return dict(workspace)
    except _FUND_ROUTE_COMPONENT_FAILURES:
        pass
    return {"items": [], "pipelineCounts": {}, "throughput": {}}


def _fund_summary_unavailable(rt) -> dict:
    return fund_summary_unavailable_payload(rt)


def _without_top_level_status_fields(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(payload or {})
    for key in ("ok", "status", "reason_code", "reason", "error"):
        out.pop(key, None)
    return out


def _fund_summary_failed_payload(rt) -> dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(
            "fund_summary_failed",
            extra=_without_top_level_status_fields(_fund_summary_unavailable(rt)),
        ),
        runtime=rt,
    )


def _fund_component_failed_payload(
    rt,
    *,
    reason_code: str,
    component_key: str,
    component_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return with_auto_trade_route_projection(
        degraded_payload(reason_code, extra={component_key: dict(component_payload or {})}),
        runtime=rt,
    )


def _component_response(component_key: str, payload: Mapping[str, Any] | None) -> dict:
    component = dict(payload or {})
    status = str(component.get("status") or component.get("stateStatus") or "").strip().lower()
    if "ok" in component:
        ok = bool(component.get("ok"))
    elif "stateReady" in component:
        ok = bool(component.get("stateReady"))
    else:
        ok = True
    if ok and status not in _NON_SUCCESS_COMPONENT_STATUSES:
        return {"ok": True, component_key: component}
    status_reasons = [str(x) for x in list(component.get("status_reasons") or []) if str(x)]
    reasons = [str(x) for x in list(component.get("reasons") or []) if str(x)]
    reason_code = str(
        component.get("reason_code")
        or component.get("reason")
        or component.get("stateReasonCode")
        or component.get("stateReason")
        or (status_reasons[0] if status_reasons else "")
        or (reasons[0] if reasons else "")
        or (f"{component_key}_{status}" if status and status != "ok" else "unavailable")
    )
    outer = unavailable_state(reason_code)
    outer["status"] = status or str(outer.get("status") or "unavailable")
    if "error" in component:
        outer["error"] = component["error"]
    if "text" in component:
        outer["text"] = component["text"]
    outer[component_key] = component
    return outer


def _candidate_store_unavailable_payload() -> dict[str, Any]:
    return unavailable_state(
        "candidate_store_unavailable",
        include_error=True,
    )


def _candidate_store_operation_failed_payload() -> dict[str, Any]:
    return unavailable_state(
        "candidate_store_unavailable",
        include_error=True,
    )


def _promotion_blocked_payload(decision: Mapping[str, Any] | None) -> dict[str, Any]:
    decision_payload = dict(decision or {})
    reason_code = str(decision_payload.get("reason_code") or "promotion_blocked")
    payload: dict[str, Any] = {
        "ok": False,
        "status": "blocked",
        "reason_code": reason_code,
        "reason": reason_code,
        "decision": decision_payload,
    }
    details = decision_payload.get("details")
    if isinstance(details, ABCMapping):
        payload["details"] = dict(details)
    return payload


def require_admin_write(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_WRITE, request=request, x_admin_key=x_admin_key)


def require_admin_read(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_READ, request=request, x_admin_key=x_admin_key)


@router.get("/api/fund/summary")
def fund_summary(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        svc = getattr(rt, "_fund_service", None)
        payload = _fund_summary_unavailable(rt) if svc is None else svc.summary(rt)
        projected = with_auto_trade_route_projection(payload, runtime=rt)
        return attach_summary_contract(
            projected,
            family="fund",
            read_model="fund_summary_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_summary_failed_payload(rt),
            family="fund",
            read_model="fund_summary_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/capital-truth")
def fund_capital_truth(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        projected = with_auto_trade_route_projection(
            _component_response("capitalTruth", _capital_truth_payload(rt)),
            runtime=rt,
        )
        return attach_summary_contract(
            projected,
            family="fund_capital_truth",
            read_model="fund_capital_truth_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_component_failed_payload(
                rt,
                reason_code="fund_capital_truth_failed",
                component_key="capitalTruth",
                component_payload=_capital_truth_payload(rt),
            ),
            family="fund_capital_truth",
            read_model="fund_capital_truth_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/family-hardening")
def fund_family_hardening(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        projected = with_auto_trade_route_projection(
            _component_response("familyHardening", _family_hardening_payload(rt)),
            runtime=rt,
        )
        return attach_summary_contract(
            projected,
            family="fund_family_hardening",
            read_model="fund_family_hardening_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_component_failed_payload(
                rt,
                reason_code="fund_family_hardening_failed",
                component_key="familyHardening",
                component_payload=_family_hardening_payload(rt),
            ),
            family="fund_family_hardening",
            read_model="fund_family_hardening_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/doctrine")
def fund_doctrine(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        projected = with_auto_trade_route_projection(
            _component_response("doctrine", _doctrine_payload(rt)),
            runtime=rt,
        )
        return attach_summary_contract(
            projected,
            family="fund_doctrine",
            read_model="fund_doctrine_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_component_failed_payload(
                rt,
                reason_code="fund_doctrine_failed",
                component_key="doctrine",
                component_payload=_doctrine_payload(rt),
            ),
            family="fund_doctrine",
            read_model="fund_doctrine_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/ledger", dependencies=[Depends(require_admin_read)])
def fund_ledger(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        projected = with_auto_trade_route_projection(
            _component_response("ledger", _ledger_payload(rt)),
            runtime=rt,
        )
        return attach_summary_contract(
            projected,
            family="fund_ledger",
            read_model="fund_ledger_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_component_failed_payload(
                rt,
                reason_code="fund_ledger_failed",
                component_key="ledger",
                component_payload=_ledger_payload(rt),
            ),
            family="fund_ledger",
            read_model="fund_ledger_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/internal-prime", dependencies=[Depends(require_admin_read)])
def fund_internal_prime(rt=Depends(get_runtime)):
    def _payload() -> dict[str, Any]:
        projected = with_auto_trade_route_projection(
            _component_response("internalPrime", _internal_prime_payload(rt)),
            runtime=rt,
        )
        return attach_summary_contract(
            projected,
            family="fund_internal_prime",
            read_model="fund_internal_prime_projection_v1",
            runtime=rt,
        )

    return safe_json_route_call(
        _payload,
        on_error=lambda _exc: attach_summary_contract(
            _fund_component_failed_payload(
                rt,
                reason_code="fund_internal_prime_failed",
                component_key="internalPrime",
                component_payload=_internal_prime_payload(rt),
            ),
            family="fund_internal_prime",
            read_model="fund_internal_prime_projection_v1",
            runtime=rt,
        ),
    )


@router.get("/api/fund/research/candidates")
def fund_candidates(rt=Depends(get_runtime)):
    return json_safe(
        attach_summary_contract(
            _research_pipeline_payload(rt),
            family="fund_research_candidates",
            read_model="fund_research_candidates_projection_v1",
            runtime=rt,
        )
    )


@router.post("/api/fund/research/candidates", dependencies=[Depends(require_admin_write)])
def create_candidate(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    rejected = _reject_unknown_fields(
        payload,
        allowed_fields=frozenset(
            {"family", "origin", "thesis", "owner", "generatedBy", "metadata"}
        ),
    )
    if rejected is not None:
        return json_safe(rejected)
    ok, rejected, thesis = _coerce_required_string(payload, field="thesis")
    if not ok:
        return json_safe(rejected)
    ok, rejected, family = _coerce_optional_string(
        payload,
        field="family",
        default="auto_generated_strategy",
    )
    if not ok:
        return json_safe(rejected)
    ok, rejected, origin = _coerce_optional_string(payload, field="origin", default="hybrid")
    if not ok:
        return json_safe(rejected)
    ok, rejected, owner = _coerce_optional_string(payload, field="owner", default="")
    if not ok:
        return json_safe(rejected)
    ok, rejected, generated_by = _coerce_optional_string(payload, field="generatedBy", default="")
    if not ok:
        return json_safe(rejected)
    ok, rejected, metadata = _coerce_optional_mapping(payload, field="metadata")
    if not ok:
        return json_safe(rejected)
    store = getattr(rt, "_research_candidates", None)
    if store is None:
        return json_safe(_candidate_store_unavailable_payload())
    try:
        item = store.create(
            family=family,
            origin=origin,
            thesis=thesis,
            owner=owner,
            generated_by=generated_by,
            metadata=metadata,
        )
    except _CANDIDATE_STORE_RUNTIME_FAILURES:
        return json_safe(_candidate_store_operation_failed_payload())
    return json_safe({"ok": True, "item": item})


@router.post("/api/fund/research/promote", dependencies=[Depends(require_admin_write)])
def promote_candidate(body: dict = Body(default={}), rt=Depends(get_runtime)):
    payload = dict(body or {})
    rejected = _reject_unknown_fields(
        payload,
        allowed_fields=frozenset(
            {"candidateId", "telemetryCount", "score", "riskScore", "stage", "reason", "reviewer"}
        ),
    )
    if rejected is not None:
        return json_safe(rejected)
    if "candidateId" not in payload:
        return json_safe(invalid_request_payload("missing_candidate_id", field="candidateId"))
    ok, candidate_id = coerce_non_empty_string(payload.get("candidateId"))
    if not ok:
        return json_safe(
            invalid_request_payload(
                "invalid_string_value",
                field="candidateId",
                value=payload.get("candidateId"),
            )
        )
    ok, rejected, telemetry_count = _coerce_optional_non_negative_int(
        payload, field="telemetryCount"
    )
    if not ok:
        return json_safe(rejected)
    ok, rejected, score = _coerce_optional_non_negative_float(payload, field="score")
    if not ok:
        return json_safe(rejected)
    ok, rejected, risk_score = _coerce_optional_non_negative_float(payload, field="riskScore")
    if not ok:
        return json_safe(rejected)
    ok, rejected, stage = _coerce_optional_string(payload, field="stage", default="")
    if not ok:
        return json_safe(rejected)
    if stage and stage not in _ALLOWED_RESEARCH_STAGES:
        return json_safe(
            invalid_request_payload(
                "invalid_stage",
                field="stage",
                value=stage,
                details={"allowed_stages": sorted(_ALLOWED_RESEARCH_STAGES)},
            )
        )
    ok, rejected, reason = _coerce_optional_string(payload, field="reason", default="promoted")
    if not ok:
        return json_safe(rejected)
    ok, rejected, reviewer = _coerce_optional_string(payload, field="reviewer", default="")
    if not ok:
        return json_safe(rejected)
    store = getattr(rt, "_research_candidates", None)
    if store is None:
        return json_safe(_candidate_store_unavailable_payload())
    evidence: dict[str, Any] = {}
    if telemetry_count is not None:
        evidence["telemetry_count"] = telemetry_count
    if score is not None:
        evidence["success_rate"] = score
    if risk_score is not None:
        evidence["drawdown_pct"] = risk_score
    try:
        decision = store.evaluate_promotion(candidate_id, evidence=evidence)
    except KeyError:
        return json_safe(
            invalid_request_payload(
                "candidate_not_found",
                field="candidateId",
                value=candidate_id,
            )
        )
    except _CANDIDATE_STORE_RUNTIME_FAILURES:
        return json_safe(_candidate_store_operation_failed_payload())
    if not decision.allowed:
        return json_safe(_promotion_blocked_payload(decision.to_dict()))
    next_stage = stage or str(decision.next_stage or "shadow_live")
    try:
        item = store.transition(
            candidate_id,
            stage=next_stage,
            reason=reason,
            reviewer=reviewer,
        )
    except KeyError:
        return json_safe(
            invalid_request_payload(
                "candidate_not_found",
                field="candidateId",
                value=candidate_id,
            )
        )
    except ValueError:
        return json_safe(
            invalid_request_payload(
                "invalid_stage",
                field="stage",
                value=next_stage,
                details={"allowed_stages": sorted(_ALLOWED_RESEARCH_STAGES)},
            )
        )
    except _CANDIDATE_STORE_RUNTIME_FAILURES:
        return json_safe(_candidate_store_operation_failed_payload())
    return json_safe(
        {"ok": True, "decision": decision.to_dict() | {"nextStage": next_stage}, "item": item}
    )
