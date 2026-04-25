from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from victor_ai_bot.runtime_services.profitability_truth import inspect_profit_after_costs_truth


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _runtime_bucket() -> Dict[str, Any]:
    return {"ok": True, "code": "ok", "detail": ""}


def _init_runtime() -> Dict[str, Any]:
    return {
        "input": _runtime_bucket(),
        "legs": _runtime_bucket(),
        "mutation": _runtime_bucket(),
        "profit": _runtime_bucket(),
        "degraded": False,
    }


def _mark_runtime(runtime: Dict[str, Any], bucket: str, code: str, detail: str = "") -> None:
    state = runtime.setdefault(bucket, _runtime_bucket())
    state["ok"] = False
    state["code"] = str(code)
    state["detail"] = str(detail or "")
    runtime["degraded"] = True


def _coerce_float(
    value: Any, default: float, runtime: Dict[str, Any], bucket: str, code: str
) -> float:
    if isinstance(value, bool):
        _mark_runtime(runtime, bucket, code, "boolean_not_allowed")
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        _mark_runtime(runtime, bucket, code, "float_invalid")
        return float(default)


def _coerce_int(value: Any, default: int, runtime: Dict[str, Any], bucket: str, code: str) -> int:
    if isinstance(value, bool):
        _mark_runtime(runtime, bucket, code, "boolean_not_allowed")
        return int(default)
    try:
        return int(str(value or "0"))
    except (TypeError, ValueError):
        _mark_runtime(runtime, bucket, code, "int_invalid")
        return int(default)


def _profit_after_costs_info(opp: Any, runtime: Dict[str, Any]) -> Tuple[int | None, bool]:
    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        return None, False
    truth = inspect_profit_after_costs_truth(meta)
    if truth.reason_code == "profit_after_costs_unavailable":
        return None, False
    if not truth.verified:
        code = (
            "plan_profit_after_costs_mismatch"
            if truth.reason_code == "profit_after_costs_mismatch"
            else "plan_profit_after_costs_invalid"
        )
        _mark_runtime(runtime, "profit", code, str(truth.reason_code))
        return None, False
    return int(truth.value_wei), True


def _sync_profit_fields(opp: Any, *, viability_min: float, runtime: Dict[str, Any]) -> None:
    scale = _clip(viability_min, 0.35, 1.0)
    exp = _coerce_int(
        getattr(opp, "expected_profit_raw", "0") or "0",
        0,
        runtime,
        "profit",
        "plan_expected_profit_invalid",
    )
    if exp > 0:
        try:
            setattr(opp, "expected_profit_raw", str(int(max(1, round(exp * scale)))))
        except (AttributeError, TypeError, ValueError):
            _mark_runtime(runtime, "profit", "plan_expected_profit_set_failed")
    profit_after, available = _profit_after_costs_info(opp, runtime)
    if not available or profit_after is None:
        return
    scaled_after = int(max(0, round(profit_after * scale)))
    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        return
    meta["profit_after_costs"] = str(scaled_after)
    safety = meta.get("safety")
    if not isinstance(safety, dict):
        safety = {}
        meta["safety"] = safety
    safety["profit_after_costs_wei"] = str(scaled_after)


def _safe_legs(route: Any, runtime: Dict[str, Any]) -> List[Any]:
    try:
        return list(getattr(route, "legs", []) or [])
    except TypeError:
        _mark_runtime(runtime, "input", "route_legs_invalid", "route.legs_not_iterable")
        return []


def _safe_leg(opp: Any, idx: int, runtime: Dict[str, Any]) -> Any | None:
    try:
        return opp.route.legs[idx]
    except (AttributeError, IndexError, TypeError):
        _mark_runtime(runtime, "legs", "plan_leg_missing", f"index={idx}")
        return None


def _normalize_split(
    route_plan: Dict[str, Any], current_venues: List[str], runtime: Dict[str, Any] | None = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    split = [dict(x) for x in list(route_plan.get("split") or []) if isinstance(x, dict)]
    selected = [str(v) for v in list(route_plan.get("selected_venues") or []) if str(v)]
    if not split:
        share = round(1.0 / float(max(1, len(current_venues))), 6)
        split = [
            {"venue": v, "share": share, "size_mult": share, "venue_quality": 0.8}
            for v in current_venues
        ]
    if not selected:
        selected = [str(x.get("venue") or "") for x in split if str(x.get("venue") or "")]
    if not selected:
        selected = list(current_venues)
    total = 0.0
    for row in split:
        total += _coerce_float(
            row.get("share") or 0.0, 0.0, runtime or _init_runtime(), "input", "route_share_invalid"
        )
    total = total or float(len(split) or 1)
    normalized = []
    for row in split:
        normalized.append(
            {
                "venue": str(row.get("venue") or ""),
                "share": round(
                    _coerce_float(
                        row.get("share") or 0.0,
                        0.0,
                        runtime or _init_runtime(),
                        "input",
                        "route_share_invalid",
                    )
                    / total,
                    6,
                ),
                "size_mult": round(
                    _coerce_float(
                        row.get("size_mult") or 0.0,
                        0.0,
                        runtime or _init_runtime(),
                        "input",
                        "route_size_mult_invalid",
                    ),
                    6,
                ),
                "venue_quality": round(
                    _coerce_float(
                        row.get("venue_quality") or 0.8,
                        0.8,
                        runtime or _init_runtime(),
                        "input",
                        "route_venue_quality_invalid",
                    ),
                    6,
                ),
            }
        )
    return normalized, selected


def build_execution_route_plan(*, opp: Any, decision: Any | None) -> Dict[str, Any]:
    runtime = _init_runtime()
    meta = (
        dict(getattr(decision, "metadata", {}) or {})
        if decision is not None and isinstance(getattr(decision, "metadata", None), dict)
        else {}
    )
    route_plan = dict(meta.get("route_plan") or {})
    flash = dict(meta.get("flashloan_resilience") or {})
    current_legs = _safe_legs(getattr(opp, "route", None), runtime)
    current_venues = [str(getattr(x, "venue", "") or "") for x in current_legs]
    split, selected = _normalize_split(route_plan, current_venues, runtime)
    fallback_tree = [
        dict(x) for x in list(route_plan.get("fallback_tree") or []) if isinstance(x, dict)
    ]
    chosen = dict(route_plan or {})
    fallback_used = False
    invalid_causes: List[str] = []
    leg_plan = []
    distortion = _coerce_float(
        flash.get("reserve_distortion") or 0.0, 0.0, runtime, "input", "route_distortion_invalid"
    )
    flash_legs = {
        str(x.get("venue") or ""): dict(x)
        for x in list(flash.get("leg_states") or [])
        if isinstance(x, dict)
    }
    executable = True
    split_map = {str(x.get("venue") or ""): dict(x) for x in split}
    for idx, leg in enumerate(current_legs):
        venue = str(getattr(leg, "venue", "") or "")
        split_row = split_map.get(
            venue,
            split[min(idx, len(split) - 1)] if split else {"share": 1.0, "venue_quality": 0.8},
        )
        flash_row = flash_legs.get(venue, {})
        selected_here = venue in selected or not selected
        leg_quality = _coerce_float(
            split_row.get("venue_quality") or 0.8,
            0.8,
            runtime,
            "input",
            "route_venue_quality_invalid",
        )
        distortion_here = _coerce_float(
            flash_row.get("distortion") or distortion,
            distortion,
            runtime,
            "input",
            "route_leg_distortion_invalid",
        )
        viability = _clip(leg_quality * (1.0 - distortion_here * 0.35), 0.05, 1.0)
        fallback_venues = [str(v) for v in list(flash_row.get("fallback_venues") or []) if str(v)]
        action = "execute"
        if not selected_here:
            action = "fallback_substitute" if fallback_venues else "invalidate"
        if not bool(flash_row.get("viable", True)):
            action = "fallback_substitute" if fallback_venues else "invalidate"
        if action == "invalidate":
            executable = False
            invalid_causes.append(f"leg:{idx}:{venue}:invalid")
        leg_plan.append(
            {
                "index": idx,
                "venue": venue,
                "share": _coerce_float(
                    split_row.get("share") or 0.0, 0.0, runtime, "input", "route_share_invalid"
                ),
                "venue_quality": leg_quality,
                "viability": round(viability, 6),
                "selected": selected_here,
                "distortion": round(distortion_here, 6),
                "action": action,
                "fallback_venues": fallback_venues,
            }
        )
    if not executable:
        for fb in fallback_tree:
            fb_selected = [str(v) for v in list(fb.get("selected_venues") or []) if str(v)]
            expected_value = _coerce_float(
                fb.get("expected_value") or 0.0,
                0.0,
                runtime,
                "input",
                "route_fallback_value_invalid",
            )
            if (
                set(current_venues).issubset(set(fb_selected or current_venues))
                and expected_value > 0.0
            ):
                chosen = fb
                split, selected = _normalize_split(fb, current_venues, runtime)
                fallback_used = True
                executable = True
                invalid_causes = []
                break
    mutation_factor = max(
        0.35,
        (
            min(
                _coerce_float(
                    x.get("viability") or 1.0, 1.0, runtime, "input", "route_viability_invalid"
                )
                for x in leg_plan
            )
            if leg_plan
            else 1.0
        ),
    )
    return {
        "selected_venues": selected,
        "split": split,
        "fallback_tree": fallback_tree,
        "fallback_used": fallback_used,
        "executable": executable,
        "require_fallback_tree": bool(flash.get("require_fallback_tree")),
        "provider_priority": list(flash.get("provider_priority") or []),
        "provider_fallback": str(flash.get("fallback_provider") or ""),
        "reserve_distortion": round(distortion, 6),
        "leg_plan": leg_plan,
        "raw_route_plan": chosen,
        "mutation_factor": round(mutation_factor, 6),
        "route_invalid_causes": invalid_causes,
        "runtime": runtime,
    }


def apply_execution_route_plan(*, opp: Any, plan: Dict[str, Any]) -> Any:
    if not bool(plan.get("executable", False)):
        raise ValueError("route_plan_not_executable")
    runtime = deepcopy(dict(plan.get("runtime") or _init_runtime()))
    opp2 = opp.copy(deep=True) if hasattr(opp, "copy") else deepcopy(opp)
    leg_plan = list(plan.get("leg_plan") or [])
    distortion = _coerce_float(
        plan.get("reserve_distortion") or 0.0, 0.0, runtime, "mutation", "plan_distortion_invalid"
    )
    route_min_factor = _coerce_float(
        plan.get("mutation_factor") or 1.0, 1.0, runtime, "mutation", "plan_mutation_factor_invalid"
    )
    viability_min = 1.0
    for row in leg_plan:
        idx = _coerce_int(row.get("index") or 0, 0, runtime, "legs", "plan_leg_index_invalid")
        leg = _safe_leg(opp2, idx, runtime)
        if leg is None:
            continue
        viability = _coerce_float(
            row.get("viability") or 1.0, 1.0, runtime, "mutation", "plan_viability_invalid"
        )
        viability_min = min(viability_min, viability)
        min_out = _coerce_int(
            getattr(leg, "min_out", "0") or "0", 0, runtime, "mutation", "plan_min_out_invalid"
        )
        adjusted = (
            int(
                max(
                    1,
                    round(
                        min_out
                        * _clip(viability * route_min_factor * (1.0 - distortion * 0.10), 0.45, 1.0)
                    ),
                )
            )
            if min_out > 0
            else min_out
        )
        try:
            leg.min_out = str(adjusted)
        except AttributeError:
            _mark_runtime(runtime, "mutation", "plan_leg_min_out_set_failed", f"index={idx}")
        if row.get("action") == "fallback_substitute" and list(row.get("fallback_venues") or []):
            try:
                leg.venue = str(list(row.get("fallback_venues") or [])[0])
            except (AttributeError, IndexError, TypeError):
                _mark_runtime(runtime, "legs", "plan_leg_fallback_set_failed", f"index={idx}")
    if isinstance(getattr(opp2, "meta", None), dict):
        opp2.meta["execution_route_plan"] = plan
        opp2.meta["execution_route_plan_applied"] = True
        opp2.meta["selected_venues"] = list(plan.get("selected_venues") or [])
        opp2.meta["route_fallback_ready"] = bool(plan.get("fallback_tree"))
        opp2.meta["route_invalid_causes"] = list(plan.get("route_invalid_causes") or [])
        opp2.meta["provider_priority"] = list(plan.get("provider_priority") or [])
        opp2.meta["execution_route_runtime"] = runtime
    try:
        opp2.min_outs = [
            str(getattr(leg, "min_out", "0") or "0") for leg in list(opp2.route.legs or [])
        ]
    except (AttributeError, TypeError):
        _mark_runtime(runtime, "legs", "plan_min_outs_refresh_failed")
    _sync_profit_fields(opp2, viability_min=viability_min, runtime=runtime)
    return opp2
