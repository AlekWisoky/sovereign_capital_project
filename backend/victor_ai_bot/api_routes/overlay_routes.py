from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..jsonsafe import json_safe
from ..runtime_services.control_state import unavailable_state
from ._route_helpers import (
    attach_summary_contract,
    coerce_canonical_bool,
    coerce_non_empty_string,
    coerce_non_negative_float,
    invalid_request_payload,
    unexpected_request_fields,
)
from ..runtime import MultiRuntimeBundle

router = APIRouter(tags=["overlays"])


def _disabled_unavailable(**extra: Any) -> Dict[str, Any]:
    payload = {"enabled": False}
    payload.update(extra)
    return unavailable_state("unavailable", extra=payload)


def _reason_unavailable() -> Dict[str, Any]:
    return unavailable_state("unavailable")


def _error_unavailable() -> Dict[str, Any]:
    return unavailable_state("unavailable", include_reason=False, include_error=True)


_SAFE_RUNTIME_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


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


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/multichain/fioa/state", dependencies=[Depends(require_admin)])
async def multichain_fioa_state(request: Request):
    """Aggregated FIOA state across chains (admin-only)."""
    rt = get_runtime(request)
    if isinstance(rt, MultiRuntimeBundle):
        out: Dict[str, Any] = {}
        for name, one in rt._runtimes.items():
            try:
                out[name] = (
                    one.fioa_state() if hasattr(one, "fioa_state") else _disabled_unavailable()
                )
            except _SAFE_RUNTIME_EXCEPTIONS as e:
                out[name] = {"ok": False, "error": f"fioa_state_failed:{e}"}
        return json_safe(
            attach_summary_contract(
                {"active": rt._active_chain, "chains": out},
                family="fioa_multichain",
                read_model="fioa_multichain_projection_v1",
                runtime=rt,
            )
        )
    try:
        name = getattr(rt.cfg.chain, "name", "")
        state = rt.fioa_state() if hasattr(rt, "fioa_state") else _disabled_unavailable()
        return json_safe(
            attach_summary_contract(
                {"active": name, "chains": {name: state}},
                family="fioa_multichain",
                read_model="fioa_multichain_projection_v1",
                runtime=rt,
            )
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        return json_safe(
            attach_summary_contract(
                {"ok": False, "error": "single_fioa_state_failed"},
                family="fioa_multichain",
                read_model="fioa_multichain_projection_v1",
                runtime=rt,
            )
        )


@router.get("/api/fioa/state")
async def fioa_state(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "fioa_state"):
        return json_safe(
            attach_summary_contract(
                rt.fioa_state(),
                family="fioa_state",
                read_model="fioa_state_projection_v1",
                runtime=rt,
            )
        )
    return json_safe(
        attach_summary_contract(
            _disabled_unavailable(),
            family="fioa_state",
            read_model="fioa_state_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/fioa/audit", dependencies=[Depends(require_admin)])
async def fioa_audit(request: Request, limit: int = 200):
    rt = get_runtime(request)
    if hasattr(rt, "fioa_audit_tail"):
        return json_safe(rt.fioa_audit_tail(limit=int(limit)))
    return json_safe(_disabled_unavailable(items=[]))


@router.get("/api/fioa/report", dependencies=[Depends(require_admin)])
async def fioa_report(request: Request, limit_audit: int = 200):
    rt = get_runtime(request)
    if hasattr(rt, "fioa_governance_report"):
        return json_safe(
            attach_summary_contract(
                rt.fioa_governance_report(limit_audit=int(limit_audit)),
                family="fioa_report",
                read_model="fioa_report_projection_v1",
                runtime=rt,
            )
        )
    return json_safe(
        attach_summary_contract(
            _disabled_unavailable(),
            family="fioa_report",
            read_model="fioa_report_projection_v1",
            runtime=rt,
        )
    )


@router.post("/api/fioa/agent/restrict", dependencies=[Depends(require_admin)])
async def fioa_restrict(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"agent_id", "reason"}))
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
    reason = str(payload.get("reason", "") or "")
    if hasattr(rt, "fioa_restrict_agent"):
        ok = bool(rt.fioa_restrict_agent(agent_id, reason=reason))
        return json_safe({"ok": ok})
    return json_safe(_reason_unavailable())


@router.post("/api/fioa/agent/resume", dependencies=[Depends(require_admin)])
async def fioa_resume(request: Request, payload: Dict[str, Any] = Body(...)):
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
    if hasattr(rt, "fioa_resume_agent"):
        ok = bool(rt.fioa_resume_agent(agent_id))
        return json_safe({"ok": ok})
    return json_safe(_reason_unavailable())


@router.post("/api/fioa/safe_mode", dependencies=[Depends(require_admin)])
async def fioa_safe_mode(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"on", "ttl_s", "reason"}))
    if rejected is not None:
        return json_safe(rejected)
    if "on" not in payload:
        return json_safe(invalid_request_payload("missing_safe_mode_toggle", field="on"))
    on_payload = payload.get("on")
    ok, on = coerce_canonical_bool(on_payload)
    if not ok:
        return json_safe(
            invalid_request_payload("invalid_boolean_value", field="on", value=on_payload)
        )
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
        reason = ""
    if hasattr(rt, "fioa_set_safe_mode"):
        ok = bool(rt.fioa_set_safe_mode(on, ttl_s=ttl_s, reason=reason))
        return json_safe({"ok": ok})
    return json_safe(_reason_unavailable())


@router.get("/api/narrative/state")
async def narrative_state(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "narrative_state"):
        return json_safe(
            attach_summary_contract(
                rt.narrative_state(),
                family="narrative_state",
                read_model="narrative_state_projection_v1",
                runtime=rt,
            )
        )
    return json_safe(
        attach_summary_contract(
            _disabled_unavailable(),
            family="narrative_state",
            read_model="narrative_state_projection_v1",
            runtime=rt,
        )
    )


@router.get("/api/narrative/history", dependencies=[Depends(require_admin)])
async def narrative_history(request: Request, limit: int = 100):
    rt = get_runtime(request)
    if hasattr(rt, "narrative_history"):
        return json_safe(rt.narrative_history(limit=int(limit)))
    return json_safe(_disabled_unavailable(items=[]))


@router.get("/api/narrative/report", dependencies=[Depends(require_admin)])
async def narrative_report(request: Request, limit: int = 100):
    rt = get_runtime(request)
    if hasattr(rt, "narrative_report"):
        return json_safe(rt.narrative_report(limit=int(limit)))
    return json_safe(_disabled_unavailable(report=""))


@router.post("/api/narrative/explanation_level", dependencies=[Depends(require_admin)])
async def narrative_set_level(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    rejected = _reject_unknown_fields(payload, allowed_fields=frozenset({"level"}))
    if rejected is not None:
        return json_safe(rejected)
    if "level" not in payload:
        return json_safe(invalid_request_payload("missing_level", field="level"))
    ok, level = coerce_non_empty_string(payload.get("level"))
    if not ok:
        return json_safe(
            invalid_request_payload(
                "invalid_string_value",
                field="level",
                value=payload.get("level"),
            )
        )
    if hasattr(rt, "narrative_set_level"):
        return json_safe(rt.narrative_set_level(level))
    return json_safe(_error_unavailable())


@router.post("/api/narrative/query", dependencies=[Depends(require_admin)])
async def narrative_query(request: Request, payload: Dict[str, Any] = Body(...)):
    rt = get_runtime(request)
    q = str(payload.get("query") or payload.get("q") or "").strip()
    agent_id = str(payload.get("agent_id") or "GOVERNANCE_AGENT")
    data_level = str(payload.get("data_level") or "INTERNAL_STRATEGY")
    if not q:
        return json_safe({"ok": False, "error": "missing_query"})
    if hasattr(rt, "narrative_query"):
        return json_safe(
            await rt.narrative_query(agent_id=agent_id, query_text=q, data_level=data_level)
        )
    return json_safe(_error_unavailable())


@router.get("/api/narrative/insights", dependencies=[Depends(require_admin)])
async def narrative_insights(request: Request):
    rt = get_runtime(request)
    if hasattr(rt, "narrative_insights"):
        return json_safe(await rt.narrative_insights())
    return json_safe(_error_unavailable())


@router.get("/api/multichain/narrative/state", dependencies=[Depends(require_admin)])
async def multichain_narrative_state(request: Request):
    rt = get_runtime(request)
    if isinstance(rt, MultiRuntimeBundle):
        out: Dict[str, Any] = {}
        for ch, one in rt._runtimes.items():
            try:
                out[ch] = (
                    one.narrative_state()
                    if hasattr(one, "narrative_state")
                    else _disabled_unavailable()
                )
            except _SAFE_RUNTIME_EXCEPTIONS as e:
                out[ch] = {"ok": False, "error": f"state_failed:{e}"}
        return json_safe({"ok": True, "chains": out, "active": rt._active_chain})
    active = get_runtime(request)
    try:
        nm = (
            active.narrative_state()
            if hasattr(active, "narrative_state")
            else _disabled_unavailable()
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        nm = _disabled_unavailable()
    return json_safe(
        {
            "ok": True,
            "chains": {getattr(active.cfg.chain, "name", ""): nm},
            "active": getattr(active.cfg.chain, "name", ""),
        }
    )
