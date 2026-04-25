from __future__ import annotations

from collections.abc import Mapping as ABCMapping
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Body, Depends, Header, Request

from ..jsonsafe import to_json_safe as json_safe
from ..runtime_services.control_state import unavailable_state
from ..runtime_services.family_hardening_service import family_hardening_unavailable_summary
from ..runtime_services.auxiliary_state_service import AuxiliaryStateService
from ..runtime_services.capital_truth_read_context import build_capital_truth_read_context
from ..runtime_services.summary_read_contract import build_summary_read_contract
from ..degraded_state_contract import aggregate_state_contracts, contract_from_surface
from ..security.auth import require_capability
from ..security.permissions import Capability
from ._route_helpers import (
    degraded_payload,
    invalid_request_payload,
    safe_json_route_call,
    unexpected_request_fields,
    with_auto_trade_route_projection,
    attach_summary_contract,
)

router = APIRouter(tags=["system"])


_RPC_PREFERENCE_FIELDS = frozenset({"read", "send", "private"})


_SYSTEM_READ_FAILURES = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def _read_surface_payload(
    rt,
    *,
    method_name: str,
    unavailable_reason: str,
    extra: dict | None = None,
    include_reason: bool = True,
    include_error: bool = False,
    include_text: bool = False,
):
    if not hasattr(rt, method_name):
        return unavailable_state(
            unavailable_reason,
            extra=extra,
            include_reason=include_reason,
            include_error=include_error,
            include_text=include_text,
        )
    try:
        payload = getattr(rt, method_name)()
    except _SYSTEM_READ_FAILURES:
        return unavailable_state(
            unavailable_reason,
            extra=extra,
            include_reason=include_reason,
            include_error=include_error,
            include_text=include_text,
        )
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return unavailable_state(
        unavailable_reason,
        extra=extra,
        include_reason=include_reason,
        include_error=include_error,
        include_text=include_text,
    )


def _service_health_payload(rt) -> dict:
    return attach_summary_contract(
        _read_surface_payload(
            rt,
            method_name="service_health_state",
            unavailable_reason="service_health_unavailable",
        ),
        family="service_health",
        read_model="service_health_projection_v1",
        runtime=rt,
    )


def _capital_truth_payload(rt) -> dict:
    return _read_surface_payload(
        rt,
        method_name="capital_truth_state",
        unavailable_reason="capital_truth_unavailable",
    )


def _family_hardening_payload(rt) -> dict:
    if not hasattr(rt, "family_hardening_state"):
        return family_hardening_unavailable_summary()
    try:
        payload = rt.family_hardening_state()
    except _SYSTEM_READ_FAILURES:
        return family_hardening_unavailable_summary()
    if isinstance(payload, ABCMapping):
        return dict(payload)
    return family_hardening_unavailable_summary()


def _capital_explain_payload(rt) -> dict:
    return _read_surface_payload(
        rt,
        method_name="capital_explain",
        unavailable_reason="capital_explanation_unavailable",
        extra={"facts": {}, "causal": {}},
        include_reason=False,
        include_text=True,
    )


def _unified_state_payload(rt) -> dict:
    payload = (
        rt.unified_state()
        if hasattr(rt, "unified_state")
        else unavailable_state("unified_state_unavailable", extra={"enabled": False})
    )
    return attach_summary_contract(
        payload,
        family="unified_state",
        read_model="unified_state_projection_v1",
        runtime=rt,
    )


def _spread_opportunities_payload(rt) -> dict:
    payload = (
        rt.spread_opportunities()
        if hasattr(rt, "spread_opportunities")
        else unavailable_state(
            "spread_opportunities_unavailable",
            extra={"count": 0, "opps": []},
        )
    )
    return attach_summary_contract(
        payload,
        family="spread_opportunities",
        read_model="spread_opportunities_projection_v1",
        runtime=rt,
    )


def _orchestrator_state_payload(rt) -> dict:
    payload = (
        rt.orchestrator_state()
        if hasattr(rt, "orchestrator_state")
        else unavailable_state("orchestrator_state_unavailable", extra={"enabled": False})
    )
    return attach_summary_contract(
        payload,
        family="orchestrator_state",
        read_model="orchestrator_state_projection_v1",
        runtime=rt,
    )


def _consensus_state_payload(rt) -> dict:
    payload = (
        rt.consensus_state()
        if hasattr(rt, "consensus_state")
        else unavailable_state("consensus_state_unavailable", extra={"last": {}})
    )
    return attach_summary_contract(
        payload,
        family="consensus_state",
        read_model="consensus_state_projection_v1",
        runtime=rt,
    )


def _behaveagent_state_payload(rt) -> dict:
    payload = (
        rt.behaveagent_state()
        if hasattr(rt, "behaveagent_state")
        else unavailable_state("behaveagent_state_unavailable", extra={"enabled": False})
    )
    return attach_summary_contract(
        payload,
        family="behaveagent_state",
        read_model="behaveagent_state_projection_v1",
        runtime=rt,
    )


def _governance_state_payload(rt) -> dict:
    payload = (
        rt.governance_layer_state()
        if hasattr(rt, "governance_layer_state")
        else unavailable_state("governance_layer_unavailable", extra={"enabled": False})
    )
    return attach_summary_contract(
        payload,
        family="governance_layer",
        read_model="governance_layer_projection_v1",
        runtime=rt,
    )


def _blockspace_state_payload(rt) -> dict:
    payload = (
        rt.blockspace_state()
        if hasattr(rt, "blockspace_state")
        else unavailable_state("blockspace_state_unavailable", extra={"enabled": False})
    )
    return attach_summary_contract(
        payload,
        family="blockspace_state",
        read_model="blockspace_state_projection_v1",
        runtime=rt,
    )


def _agent_hub_state_payload(rt) -> dict:
    payload = (
        rt.agent_hub_state()
        if hasattr(rt, "agent_hub_state")
        else unavailable_state("agent_hub_state_unavailable", extra={"state": {}})
    )
    return attach_summary_contract(
        payload,
        family="agent_hub",
        read_model="agent_hub_projection_v1",
        runtime=rt,
    )


def _system_auxiliary_failed_payload(
    failed_reason_code: str,
    unavailable_reason: str,
    *,
    extra: dict[str, Any] | None = None,
) -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            failed_reason_code,
            extra=unavailable_state(unavailable_reason, extra=extra),
        )
    )


def _execution_quality_defaults() -> dict:
    return {
        "calibration": {"items": []},
        "venue_profiles": {"venues": []},
        "risk_memory": {"failures": {}},
        "path_diversity": {"paths": []},
        "edge_learning": {"items": []},
        "endpoint_quality": {"lanes": {}, "summary": {}, "generatedAtMs": 0},
        "endpoint_universe": {"read": {}, "public": {}, "protected": {}, "private": {}},
        "venue_scorecards": {"pairs": {}},
        "route_quality": {"items": []},
        "live_execution": {"items": []},
        "drawdown": {},
        "kill_switch": {"suppressed": []},
    }


def _execution_quality_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_execution_quality_failed",
            extra=_execution_quality_defaults(),
        ),
    )


def _execution_quality_payload(rt) -> dict:
    payload = {
        "ok": True,
        "calibration": (
            rt.execution_calibration_state()
            if hasattr(rt, "execution_calibration_state")
            else {"items": []}
        ),
        "venue_profiles": (
            rt.venue_profiles_state() if hasattr(rt, "venue_profiles_state") else {"venues": []}
        ),
        "risk_memory": (
            rt.risk_memory_state() if hasattr(rt, "risk_memory_state") else {"failures": {}}
        ),
        "path_diversity": (
            rt.path_diversity_state() if hasattr(rt, "path_diversity_state") else {"paths": []}
        ),
        "edge_learning": (
            rt.edge_learning_state() if hasattr(rt, "edge_learning_state") else {"items": []}
        ),
        "endpoint_quality": (
            rt.endpoint_quality_state()
            if hasattr(rt, "endpoint_quality_state")
            else {"lanes": {}, "summary": {}, "generatedAtMs": 0}
        ),
        "endpoint_universe": (
            rt.endpoint_universe_state()
            if hasattr(rt, "endpoint_universe_state")
            else {"read": {}, "public": {}, "protected": {}, "private": {}}
        ),
        "venue_scorecards": (
            rt.venue_scorecards_state() if hasattr(rt, "venue_scorecards_state") else {"pairs": {}}
        ),
        "route_quality": (
            rt.route_quality_state() if hasattr(rt, "route_quality_state") else {"items": []}
        ),
        "live_execution": (
            rt.execution_live_state() if hasattr(rt, "execution_live_state") else {"items": []}
        ),
        "drawdown": rt.drawdown_state() if hasattr(rt, "drawdown_state") else {},
        "kill_switch": (
            rt.kill_switch_state() if hasattr(rt, "kill_switch_state") else {"suppressed": []}
        ),
    }
    return with_auto_trade_route_projection(
        attach_summary_contract(
            payload,
            family="execution_quality",
            read_model="execution_quality_projection_v1",
            runtime=rt,
        ),
        runtime=rt,
    )


def _system_summary_defaults() -> dict:
    return {
        "services": unavailable_state("service_health_unavailable"),
        "capitalTruth": unavailable_state("capital_truth_unavailable"),
        "familyHardening": family_hardening_unavailable_summary(),
    }


def _fund_health_payload(rt) -> dict:
    return _read_surface_payload(
        rt,
        method_name="fund_summary_state",
        unavailable_reason="fund_summary_unavailable",
        extra={"health": {}},
    )


def _system_summary_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_summary_failed",
            extra=_system_summary_defaults(),
        ),
    )


def _system_summary_payload(rt) -> dict:
    svc = getattr(rt, "_analytics_service", None)
    if svc is not None:
        try:
            raw_payload = svc.system_summary(rt)
        except _SYSTEM_READ_FAILURES:
            raw_payload = None
        payload = (
            dict(raw_payload)
            if isinstance(raw_payload, ABCMapping)
            else unavailable_state(
                "analytics_service_unavailable", include_reason=False, include_error=True
            )
        )
    else:
        payload = unavailable_state(
            "analytics_service_unavailable", include_reason=False, include_error=True
        )
    fund_summary = _fund_health_payload(rt)
    fund_health = (
        dict((fund_summary.get("health") or fund_summary)) if isinstance(fund_summary, dict) else {}
    )
    capital_context = build_capital_truth_read_context(
        rt,
        auxiliary_state=AuxiliaryStateService(),
        fund_summary=fund_health,
    )
    capital_truth = capital_context.capital_truth
    payload["services"] = _service_health_payload(rt)
    payload["capitalTruth"] = _capital_truth_payload(rt)
    payload["familyHardening"] = _family_hardening_payload(rt)
    capital_surface = dict(capital_context.capital_surface or {})
    payload.update(capital_surface)
    execution_service = getattr(rt, "_execution_service", None)
    execution_summary = {}
    if execution_service is not None and hasattr(execution_service, "summarize"):
        try:
            execution_summary = dict(execution_service.summarize(rt) or {})
        except _SYSTEM_READ_FAILURES:
            execution_summary = {}
    payload.setdefault("serviceContracts", {})
    payload["serviceContracts"]["summary"] = contract_from_surface(
        payload,
        phase="system_summary",
        default_reason=str(payload.get("reason_code") or payload.get("error") or "ok"),
        sticky_cycle=True,
    )
    payload["serviceContracts"]["capitalTruth"] = dict(
        payload["capitalTruthHealth"].get("stateContract")
        or {
            "phase": "capital_truth_summary",
            "status": "unavailable",
            "reason_code": "capital_truth_unavailable",
        }
    )
    payload["serviceContracts"].setdefault(
        "execution",
        dict(
            execution_summary.get("stateContract")
            or {
                "phase": "execution",
                "status": "unavailable",
                "reason_code": "execution_service_unavailable",
            }
        ),
    )
    payload["stateContract"] = aggregate_state_contracts(
        phase="system_summary",
        contracts={
            "summary": dict(payload["serviceContracts"].get("summary") or {}),
            "capitalTruth": dict(payload["serviceContracts"].get("capitalTruth") or {}),
            "execution": dict(payload["serviceContracts"].get("execution") or {}),
        },
        sticky_cycle=True,
    )
    payload["degraded"] = bool(
        payload.get("degraded", False) or payload["stateContract"].get("degraded", False)
    )
    payload["reason_code"] = str(
        payload["stateContract"].get("reason_code") or payload.get("reason_code") or "ok"
    )
    payload["summaryContract"] = build_summary_read_contract(
        family="system",
        payload=payload,
        capital_contract=dict(capital_truth.capital_contract or {}),
        capital_policy=dict(capital_truth.capital_policy or {}),
        source_contracts={
            "summary": dict(payload["serviceContracts"].get("summary") or {}),
            "capitalTruth": dict(payload["serviceContracts"].get("capitalTruth") or {}),
            "execution": dict(payload["serviceContracts"].get("execution") or {}),
            "capitalContract": dict(capital_truth.capital_contract or {}),
            "capitalPolicy": dict(capital_truth.capital_policy or {}),
        },
        phase="system_summary",
    )
    return with_auto_trade_route_projection(payload, runtime=rt)


def _system_services_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_services_failed",
            extra=unavailable_state("service_health_unavailable"),
        )
    )


def _system_capital_truth_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_capital_truth_failed",
            extra=unavailable_state("capital_truth_unavailable"),
        )
    )


def _system_family_hardening_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_family_hardening_failed",
            extra=family_hardening_unavailable_summary(),
        )
    )


def _system_capital_explain_failed_payload() -> dict:
    return with_auto_trade_route_projection(
        degraded_payload(
            "system_capital_explain_failed",
            extra=unavailable_state(
                "capital_explanation_unavailable",
                extra={"facts": {}, "causal": {}},
                include_reason=False,
                include_text=True,
            ),
        )
    )


@router.get("/api/system/summary")
def system_summary(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _system_summary_payload(rt),
        on_error=lambda exc: _system_summary_failed_payload(),
    )


def require_admin_read(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_READ, request=request, x_admin_key=x_admin_key)


def require_admin_write(
    request: Request, x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")
):
    return require_capability(Capability.ADMIN_WRITE, request=request, x_admin_key=x_admin_key)


@router.get("/api/system/security/audit", dependencies=[Depends(require_admin_read)])
def security_audit(request: Request):
    rt = request.app.state.runtime  # type: ignore[attr-defined]
    store = getattr(rt, "_security_audit", None)
    db = getattr(store, "db", None)
    if db is None:
        return json_safe({"items": []})
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT ts_ms, action, subject, chain, allowed, capability, details_json FROM security_audit ORDER BY ts_ms DESC LIMIT 200"
        ).fetchall()
    return json_safe({"items": [dict(r) for r in rows]})


@router.get("/api/system/execution/quality")
def execution_quality(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: _execution_quality_payload(rt),
        on_error=lambda exc: _execution_quality_failed_payload(),
    )


@router.get("/api/system/services")
def system_services(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_service_health_payload(rt), runtime=rt),
        on_error=lambda exc: _system_services_failed_payload(),
    )


@router.get("/api/system/capital/truth")
def system_capital_truth(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_capital_truth_payload(rt), runtime=rt),
        on_error=lambda exc: _system_capital_truth_failed_payload(),
    )


@router.get("/api/system/family-hardening")
def system_family_hardening(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_family_hardening_payload(rt), runtime=rt),
        on_error=lambda exc: _system_family_hardening_failed_payload(),
    )


@router.get("/api/system/capital/explain")
def system_capital_explain(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_capital_explain_payload(rt), runtime=rt),
        on_error=lambda exc: _system_capital_explain_failed_payload(),
    )


def _normalize_rpc_preference_lane(body: Dict[str, Any], lane: str) -> Tuple[bool, Any]:
    if lane not in body:
        return True, None
    value = body.get(lane)
    if not isinstance(value, list):
        return False, invalid_request_payload(
            "invalid_rpc_preference_list",
            field=lane,
            value=value,
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            return False, invalid_request_payload(
                "invalid_rpc_preference_item",
                field=lane,
                details={"index": idx, "value": item},
            )
        trimmed = item.strip()
        if not trimmed:
            return False, invalid_request_payload(
                "invalid_rpc_preference_item",
                field=lane,
                details={"index": idx, "value": item},
            )
        if trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return True, normalized


def _validate_rpc_preferences_patch(body: Any) -> Tuple[bool, Dict[str, Any]]:
    if not isinstance(body, dict):
        return False, invalid_request_payload(
            "invalid_request_payload", details={"expected": "object"}
        )
    extras = unexpected_request_fields(body, allowed_fields=_RPC_PREFERENCE_FIELDS)
    if extras:
        return False, invalid_request_payload(
            "unknown_request_fields",
            details={"fields": extras},
        )
    if not body:
        return False, invalid_request_payload("rpc_preferences_patch_empty")
    patch: Dict[str, Any] = {}
    for lane in ("read", "send", "private"):
        ok, normalized = _normalize_rpc_preference_lane(body, lane)
        if not ok:
            return False, normalized
        if normalized is not None:
            patch[lane] = normalized
    if not patch:
        return False, invalid_request_payload("rpc_preferences_patch_empty")
    return True, patch


@router.get("/api/system/rpc/preferences", dependencies=[Depends(require_admin_read)])
def rpc_preferences(rt=Depends(get_runtime)):
    return json_safe(
        rt.rpc_preferences_state()
        if hasattr(rt, "rpc_preferences_state")
        else {"read": [], "send": [], "private": [], "configured": False}
    )


@router.post("/api/system/rpc/preferences", dependencies=[Depends(require_admin_write)])
def set_rpc_preferences(body: dict = Body(default={}), rt=Depends(get_runtime)):
    store = getattr(rt, "_rpc_preferences", None)
    if store is None:
        return json_safe(unavailable_state("rpc_preferences_unavailable", include_error=True))
    ok, patch = _validate_rpc_preferences_patch(body or {})
    if not ok:
        return json_safe(patch)
    snap = store.patch(
        read=patch.get("read"),
        send=patch.get("send"),
        private=patch.get("private"),
    )
    return json_safe({"ok": True, "status": "updated", "preferences": snap})


@router.get("/api/unified/state")
def unified_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_unified_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "unified_state_failed",
            "unified_state_unavailable",
            extra={"enabled": False},
        ),
    )


@router.get("/api/spread/opportunities")
def spread_opportunities(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_spread_opportunities_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "spread_opportunities_failed",
            "spread_opportunities_unavailable",
            extra={"count": 0, "opps": []},
        ),
    )


@router.get("/api/orchestrator/state")
def orchestrator_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_orchestrator_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "orchestrator_state_failed",
            "orchestrator_state_unavailable",
            extra={"enabled": False},
        ),
    )


@router.get("/api/consensus/state")
def consensus_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_consensus_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "consensus_state_failed",
            "consensus_state_unavailable",
            extra={"last": {}},
        ),
    )


@router.get("/api/behaveagent/state")
def behaveagent_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_behaveagent_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "behaveagent_state_failed",
            "behaveagent_state_unavailable",
            extra={"enabled": False},
        ),
    )


@router.get("/api/governance/state")
def governance_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_governance_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "governance_layer_state_failed",
            "governance_layer_unavailable",
            extra={"enabled": False},
        ),
    )


@router.get("/api/blockspace/state")
def blockspace_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_blockspace_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "blockspace_state_failed",
            "blockspace_state_unavailable",
            extra={"enabled": False},
        ),
    )


@router.get("/api/agenthub/state")
def agent_hub_state(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: with_auto_trade_route_projection(_agent_hub_state_payload(rt), runtime=rt),
        on_error=lambda exc: _system_auxiliary_failed_payload(
            "agent_hub_state_failed",
            "agent_hub_state_unavailable",
            extra={"state": {}},
        ),
    )
