from __future__ import annotations

from typing import Any, Dict, List, Mapping

_ROUTE_RUNTIME_REASON_ALIASES = {
    "plan_profit_after_costs_invalid": "profit_after_costs_invalid",
    "plan_profit_after_costs_mismatch": "profit_after_costs_mismatch",
}


def _safe_mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _unique_strings(values: List[Any]) -> List[str]:
    out: List[str] = []
    for value in values:
        code = str(value or "").strip()
        code = str(_ROUTE_RUNTIME_REASON_ALIASES.get(code, code) or code)
        if code and code not in out:
            out.append(code)
    return out


def execution_route_runtime_reason_codes(runtime: Mapping[str, Any] | None) -> List[str]:
    payload = _safe_mapping(runtime)
    codes: List[Any] = []
    codes.extend(list(payload.get("reason_codes") or []))
    codes.extend(list(payload.get("route_degradation_reasons") or []))
    for key in (
        "route_quality_reason_code",
        "router_reliability_reason_code",
        "calldata_quality_reason_code",
    ):
        value = str(payload.get(key) or "")
        if value:
            codes.append(value)
    for bucket in ("input", "legs", "mutation", "profit"):
        state = _safe_mapping(payload.get(bucket))
        if state and not bool(state.get("ok", True)):
            codes.append(str(state.get("code") or f"execution_route_{bucket}_degraded"))
    return _unique_strings(codes)


def execution_route_truth(meta: Mapping[str, Any] | None) -> Dict[str, Any]:
    meta_payload = _safe_mapping(meta)
    execution_plan = _safe_mapping(meta_payload.get("execution_route_plan"))
    route_invalid_causes = _unique_strings(
        list(
            execution_plan.get("route_invalid_causes")
            or meta_payload.get("route_invalid_causes")
            or []
        )
    )
    route_runtime = _safe_mapping(meta_payload.get("execution_route_runtime"))
    route_runtime_reason_codes = execution_route_runtime_reason_codes(route_runtime)
    route_runtime_degraded = bool(route_runtime.get("degraded", False)) or bool(
        route_runtime_reason_codes
    )
    route_plan_executable = bool(execution_plan.get("executable", True)) if execution_plan else True

    if execution_plan and not route_plan_executable:
        reason = str(
            route_invalid_causes[0] if route_invalid_causes else "route_plan_not_executable"
        )
        reason_codes = list(route_invalid_causes or [reason])
        next_action = "refresh_execution_route_plan"
        ready = False
    elif route_runtime_degraded:
        reason = str(
            route_runtime_reason_codes[0]
            if route_runtime_reason_codes
            else "execution_route_runtime_degraded"
        )
        reason_codes = list(route_runtime_reason_codes or [reason])
        next_action = (
            "refresh_after_fee_profitability_truth"
            if str(reason).startswith("profit_after_costs_")
            else "refresh_execution_route_runtime"
        )
        ready = False
    elif route_invalid_causes:
        reason = str(route_invalid_causes[0])
        reason_codes = list(route_invalid_causes)
        next_action = "refresh_execution_route_plan"
        ready = False
    else:
        reason = "ok"
        reason_codes = []
        next_action = "continue_execution"
        ready = True

    return {
        "ready": ready,
        "reason": reason,
        "reason_codes": reason_codes,
        "suggested_next_action": next_action,
        "plan_executable": route_plan_executable,
        "invalid_causes": route_invalid_causes,
        "runtime": route_runtime,
        "runtime_degraded": route_runtime_degraded,
        "runtime_reason_codes": route_runtime_reason_codes,
    }
