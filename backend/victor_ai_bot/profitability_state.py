from __future__ import annotations

from typing import Any, Dict, Mapping

from .safety import check_profit_and_repay


_MICRO_USD_THRESHOLD = 1000.0


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _safe_int(value: Any, default: int = 0) -> int:
    if value in (None, "") or isinstance(value, bool):
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return int(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "") or isinstance(value, bool):
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return float(default)


def _raw_attr(opp: Any, name: str) -> Any:
    if isinstance(opp, Mapping):
        return opp.get(name)
    return getattr(opp, name, None)


def _raw_meta(opp: Any) -> Dict[str, Any]:
    return _safe_dict(_raw_attr(opp, "meta"))


def _continuity(opp: Any) -> Dict[str, Any]:
    return _safe_dict(_raw_meta(opp).get("profitability_continuity"))


def _safe_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s:
            out.append(s)
    return out


def _route_context_list(route_context: Mapping[str, Any], *keys: str) -> list[str]:
    for key in keys:
        if key in route_context:
            return _safe_str_list(route_context.get(key))
    return []


def _meta_list(meta: Mapping[str, Any], *keys: str) -> list[str]:
    for key in keys:
        if key in meta:
            return _safe_str_list(meta.get(key))
    return []


def _continuity_expected(existing: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(existing, Mapping):
        return {}
    expected = existing.get("expected")
    return _safe_dict(expected)


def _continuity_observed(existing: Mapping[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(existing, Mapping):
        return {}
    observed = existing.get("observed")
    return _safe_dict(observed)


def assess_post_mutation_profitability_continuity(
    opp: Any,
    cfg: Any,
    *,
    route_context: Mapping[str, Any] | None = None,
    existing_continuity: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    meta = _raw_meta(opp)
    route_context_dict = _safe_dict(route_context)
    amount_in_wei, amount_out_wei = _resolve_amounts(opp)
    gas_candidates = [
        _safe_int(meta.get("gas_cost_estimate_wei"), 0),
        _safe_int(_safe_dict(meta.get("search_profitability")).get("gas_cost_wei"), 0),
        _safe_int(_safe_dict(meta.get("safety")).get("gas_cost_wei"), 0),
        _safe_int(_safe_dict(meta.get("profitability")).get("gas_cost_wei"), 0),
    ]
    current_gas_cost_wei = next((int(x) for x in gas_candidates if int(x) > 0), 0)
    if current_gas_cost_wei <= 0:
        current_gas_cost_wei = _infer_gas_cost_wei(opp, cfg, None)
    current_flashloan_fee_bps = 0
    try:
        current_flashloan_fee_bps = int(
            getattr(getattr(cfg, "execution", None), "flashloan_fee_bps", 0) or 0
        )
    except (AttributeError, TypeError, ValueError):
        current_flashloan_fee_bps = 0

    observed = {
        "amount_in_wei": str(max(0, int(amount_in_wei))),
        "amount_out_wei": str(max(0, int(amount_out_wei))),
        "route_id": str(_raw_attr(opp, "route_id") or meta.get("route_id") or ""),
        "selected_venues": _meta_list(meta, "selected_venues")
        or _meta_list(_safe_dict(meta.get("execution_route_plan")), "selected_venues"),
        "provider_priority": _meta_list(meta, "provider_priority")
        or _meta_list(_safe_dict(meta.get("execution_route_plan")), "provider_priority"),
        "route_invalid_causes": _meta_list(meta, "route_invalid_causes")
        or _meta_list(_safe_dict(meta.get("execution_route_plan")), "route_invalid_causes"),
        "gas_cost_wei": str(max(0, int(current_gas_cost_wei))),
        "flashloan_fee_bps": int(max(0, int(current_flashloan_fee_bps))),
        "execution_route_plan_applied": bool(meta.get("execution_route_plan_applied")),
    }

    expected = dict(_continuity_expected(existing_continuity) or observed)

    route_expected_selected = _route_context_list(
        route_context_dict, "selectedVenues", "selected_venues"
    )
    if route_expected_selected:
        expected["selected_venues"] = route_expected_selected
    route_expected_provider = _route_context_list(
        route_context_dict, "providerPriority", "provider_priority"
    )
    if route_expected_provider:
        expected["provider_priority"] = route_expected_provider
    if "routeInvalidCauses" in route_context_dict or "route_invalid_causes" in route_context_dict:
        expected["route_invalid_causes"] = _route_context_list(
            route_context_dict, "routeInvalidCauses", "route_invalid_causes"
        )

    mismatches: list[str] = []
    if str(expected.get("amount_in_wei") or observed["amount_in_wei"]) != observed["amount_in_wei"]:
        mismatches.append("mutation_desync_amount_in")
    if (
        str(expected.get("amount_out_wei") or observed["amount_out_wei"])
        != observed["amount_out_wei"]
    ):
        mismatches.append("mutation_desync_amount_out")
    if str(expected.get("route_id") or observed["route_id"]) != observed["route_id"]:
        mismatches.append("mutation_desync_route_id")
    if _safe_str_list(expected.get("selected_venues")) != _safe_str_list(
        observed.get("selected_venues")
    ):
        mismatches.append("mutation_desync_selected_venues")
    if _safe_str_list(expected.get("provider_priority")) != _safe_str_list(
        observed.get("provider_priority")
    ):
        mismatches.append("mutation_desync_provider_priority")
    if _safe_str_list(expected.get("route_invalid_causes")) != _safe_str_list(
        observed.get("route_invalid_causes")
    ):
        mismatches.append("mutation_desync_route_invalid_causes")
    if str(expected.get("gas_cost_wei") or observed["gas_cost_wei"]) != observed["gas_cost_wei"]:
        mismatches.append("mutation_desync_gas_cost")
    if _safe_int(
        expected.get("flashloan_fee_bps"), _safe_int(observed["flashloan_fee_bps"], 0)
    ) != _safe_int(observed["flashloan_fee_bps"], 0):
        mismatches.append("mutation_desync_flashloan_fee_bps")

    existing_valid = True
    existing_reason = "ok"
    if isinstance(existing_continuity, Mapping):
        existing_valid = bool(existing_continuity.get("valid", True))
        existing_reason = str(existing_continuity.get("reason") or "ok")

    valid = bool(existing_valid and not mismatches)
    reason = str(mismatches[0] if mismatches else (existing_reason if not existing_valid else "ok"))
    return {
        "valid": valid,
        "reason": reason,
        "mismatchCodes": list(mismatches),
        "expected": expected,
        "observed": observed,
    }


def has_profitability_contract(opp: Any) -> bool:
    meta = _raw_meta(opp)
    return bool(
        _safe_dict(meta.get("profitability"))
        or _safe_dict(meta.get("profitability_continuity"))
        or _safe_dict(meta.get("safety"))
    )


def _gas_cost_candidates(opp: Any) -> list[int]:
    meta = _raw_meta(opp)
    profitability = _safe_dict(meta.get("profitability"))
    safety = _safe_dict(meta.get("safety"))
    search_profitability = _safe_dict(meta.get("search_profitability"))
    return [
        _safe_int(profitability.get("gas_cost_wei"), 0),
        _safe_int(safety.get("gas_cost_wei"), 0),
        _safe_int(meta.get("gas_cost_estimate_wei"), 0),
        _safe_int(search_profitability.get("gas_cost_wei"), 0),
    ]


def _infer_gas_cost_wei(opp: Any, cfg: Any, gas_cost_wei: int | None) -> int:
    if gas_cost_wei is not None:
        return max(0, int(gas_cost_wei))
    for candidate in _gas_cost_candidates(opp):
        if candidate > 0:
            return int(candidate)
    return 0


def _resolve_amounts(opp: Any) -> tuple[int, int]:
    amount_in_wei = 0
    amount_out_wei = 0
    try:
        amount_in_wei = int(str(getattr(_raw_attr(opp, "route").legs[0], "amount_in", "0") or "0"))
    except (AttributeError, IndexError, TypeError, ValueError):
        amount_in_wei = 0
    try:
        min_outs = list(_raw_attr(opp, "min_outs") or [])
        if min_outs:
            amount_out_wei = int(str(min_outs[-1] or "0"))
        else:
            route = _raw_attr(opp, "route")
            legs = list(getattr(route, "legs", []) or [])
            if legs:
                amount_out_wei = int(str(getattr(legs[-1], "min_out", "0") or "0"))
    except (AttributeError, IndexError, TypeError, ValueError):
        amount_out_wei = 0
    return int(amount_in_wei), int(amount_out_wei)


def build_profitability_state(
    *,
    stage: str,
    source: str,
    reason: str,
    revalidated: bool,
    stale: bool,
    valid: bool,
    gross_profit_wei: int = 0,
    expected_profit_usd: float = 0.0,
    profit_after_costs_wei: int = 0,
    profit_after_costs_usd_micro: int = 0,
    gas_cost_wei: int = 0,
    flashloan_fee_wei: int = 0,
    amount_in_wei: int = 0,
    amount_out_wei: int = 0,
    continuity: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    continuity_dict = _safe_dict(continuity)
    return {
        "stage": str(stage or "unknown"),
        "source": str(source or "unknown"),
        "reason": str(reason or "unknown"),
        "revalidated": bool(revalidated),
        "stale": bool(stale),
        "valid": bool(valid),
        "authoritative": bool(revalidated and valid and not stale),
        "gross_profit_wei": str(max(0, int(gross_profit_wei))),
        "expected_profit_usd": float(expected_profit_usd or 0.0),
        "profit_after_costs_wei": str(int(profit_after_costs_wei)),
        "profit_after_costs_usd_micro": int(profit_after_costs_usd_micro or 0),
        "gas_cost_wei": str(max(0, int(gas_cost_wei))),
        "flashloan_fee_wei": str(max(0, int(flashloan_fee_wei))),
        "amount_in_wei": str(max(0, int(amount_in_wei))),
        "amount_out_wei": str(max(0, int(amount_out_wei))),
        "continuity": continuity_dict,
    }


def set_profitability_state(opp: Any, state: Mapping[str, Any]) -> None:
    if isinstance(getattr(opp, "meta", None), dict):
        opp.meta["profitability"] = dict(state)


def build_terminal_profitability_authority(
    profitability: Mapping[str, Any] | None, *, source: str = "execution_plan"
) -> Dict[str, Any]:
    state = _safe_dict(profitability)
    stage = str(state.get("stage") or "unknown")
    reason = str(state.get("reason") or "unknown")
    authoritative = bool(state.get("authoritative", False))
    return {
        "source": str(source or "execution_plan"),
        "stage": stage,
        "reason": reason,
        "authoritative": authoritative,
        "live_gas_derived": stage.startswith("execution_preflight"),
        "profitability": state,
    }


def build_post_mutation_revalidation_contract(
    profitability: Mapping[str, Any] | None,
    *,
    source: str = "execution_service",
    route_context: Mapping[str, Any] | None = None,
    safety: Mapping[str, Any] | None = None,
    continuity: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    state = _safe_dict(profitability)
    route_context_dict = _safe_dict(route_context)
    safety_dict = _safe_dict(safety)
    continuity_dict = _safe_dict(state.get("continuity")) or _safe_dict(continuity)
    reason_code = str(
        state.get("reason")
        or continuity_dict.get("reason")
        or safety_dict.get("reason")
        or "profitability_unavailable"
    )
    return {
        "source": str(source or state.get("source") or "execution_service"),
        "stage": str(state.get("stage") or "post_mutation_revalidation_unavailable"),
        "reason_code": reason_code,
        "reason": reason_code,
        "degraded": bool(state.get("stale", True) or (not bool(state.get("valid", False)))),
        "authoritative": bool(state.get("authoritative", False)),
        "revalidated": bool(state.get("revalidated", False)),
        "valid": bool(state.get("valid", False)),
        "continuity": continuity_dict,
        "safety": {
            "revalidated": bool(safety_dict.get("revalidated", False)),
            "reason": str(safety_dict.get("reason") or reason_code),
            "gas_cost_wei": str(
                _safe_int(safety_dict.get("gas_cost_wei"), _safe_int(state.get("gas_cost_wei"), 0))
            ),
            "profit_after_costs_wei": str(
                _safe_int(
                    safety_dict.get("profit_after_costs_wei"),
                    _safe_int(state.get("profit_after_costs_wei"), 0),
                )
            ),
            "flashloan_fee_wei": str(
                _safe_int(
                    safety_dict.get("flashloan_fee_wei"),
                    _safe_int(state.get("flashloan_fee_wei"), 0),
                )
            ),
        },
        "routeInvalidCauses": list(
            route_context_dict.get("routeInvalidCauses")
            or route_context_dict.get("route_invalid_causes")
            or []
        ),
        "selectedVenues": list(
            route_context_dict.get("selectedVenues")
            or route_context_dict.get("selected_venues")
            or []
        ),
        "providerPriority": list(
            route_context_dict.get("providerPriority")
            or route_context_dict.get("provider_priority")
            or []
        ),
        "profitability": state,
    }


def set_post_mutation_revalidation_contract(opp: Any, contract: Mapping[str, Any]) -> None:
    if isinstance(getattr(opp, "meta", None), dict):
        opp.meta["post_mutation_revalidation"] = dict(contract)


def post_mutation_revalidation_view(opp: Any) -> Dict[str, Any]:
    return _safe_dict(_raw_meta(opp).get("post_mutation_revalidation"))


def revalidate_profitability_state(
    opp: Any,
    cfg: Any,
    *,
    stage: str,
    source: str,
    gas_cost_wei: int | None = None,
) -> Dict[str, Any]:
    if not isinstance(getattr(opp, "meta", None), dict):
        try:
            opp.meta = {}
        except (AttributeError, TypeError, ValueError):
            return {}
    meta = opp.meta
    continuity = _continuity(opp)
    amount_in_wei, amount_out_wei = _resolve_amounts(opp)
    gross_profit_wei = int(amount_out_wei) - int(amount_in_wei)
    expected_profit_usd = _safe_float(
        _raw_attr(opp, "expected_profit_usd")
        or _safe_dict(meta.get("unit_econ")).get("expected_profit_usd_micro"),
        0.0,
    )
    if expected_profit_usd > _MICRO_USD_THRESHOLD:
        expected_profit_usd /= 1_000_000.0
    resolved_gas_cost_wei = _infer_gas_cost_wei(opp, cfg, gas_cost_wei)

    if continuity and not bool(continuity.get("valid", False)):
        state = build_profitability_state(
            stage=str(stage),
            source=str(source),
            reason=str(continuity.get("reason") or "mutation_invalid"),
            revalidated=False,
            stale=True,
            valid=False,
            gross_profit_wei=int(gross_profit_wei),
            expected_profit_usd=float(expected_profit_usd),
            profit_after_costs_wei=0,
            profit_after_costs_usd_micro=0,
            gas_cost_wei=int(resolved_gas_cost_wei),
            flashloan_fee_wei=0,
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out_wei),
            continuity=continuity,
        )
    elif amount_in_wei <= 0 or amount_out_wei <= 0:
        state = build_profitability_state(
            stage=str(stage),
            source=str(source),
            reason="invalid_amounts",
            revalidated=False,
            stale=True,
            valid=False,
            gross_profit_wei=int(gross_profit_wei),
            expected_profit_usd=float(expected_profit_usd),
            profit_after_costs_wei=0,
            profit_after_costs_usd_micro=0,
            gas_cost_wei=int(resolved_gas_cost_wei),
            flashloan_fee_wei=0,
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out_wei),
            continuity=continuity,
        )
    elif resolved_gas_cost_wei <= 0:
        state = build_profitability_state(
            stage=str(stage),
            source=str(source),
            reason="gas_cost_unavailable",
            revalidated=False,
            stale=True,
            valid=False,
            gross_profit_wei=int(gross_profit_wei),
            expected_profit_usd=float(expected_profit_usd),
            profit_after_costs_wei=0,
            profit_after_costs_usd_micro=0,
            gas_cost_wei=0,
            flashloan_fee_wei=0,
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out_wei),
            continuity=continuity,
        )
    else:
        sr = check_profit_and_repay(
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out_wei),
            min_profit_abs_wei=int(getattr(cfg.safety, "minProfitAbs", 0) or 0),
            min_profit_bps=int(getattr(cfg.safety, "minProfitBps", 0) or 0),
            flashloan_fee_bps=int(getattr(cfg.execution, "flashloan_fee_bps", 0) or 0),
            gas_cost_wei=int(resolved_gas_cost_wei),
        )
        state = build_profitability_state(
            stage=str(stage),
            source=str(source),
            reason=("ok" if bool(sr.ok) else str(sr.reason or "denied")),
            revalidated=True,
            stale=False,
            valid=bool(sr.ok),
            gross_profit_wei=int(gross_profit_wei),
            expected_profit_usd=float(expected_profit_usd),
            profit_after_costs_wei=int(sr.profit_after_costs_wei),
            profit_after_costs_usd_micro=0,
            gas_cost_wei=int(sr.gas_cost_wei),
            flashloan_fee_wei=int(sr.flashloan_fee_wei),
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out_wei),
            continuity=continuity,
        )
        safety = _safe_dict(meta.get("safety"))
        safety.update(
            {
                "ok": bool(sr.ok),
                "is_safe": bool(sr.ok),
                "revalidated": True,
                "reason": ("ok" if bool(sr.ok) else str(sr.reason or "denied")),
                "amount_out_final_wei": str(int(amount_out_wei)),
                "flashloan_fee_wei": str(int(sr.flashloan_fee_wei)),
                "gas_cost_wei": str(int(sr.gas_cost_wei)),
                "profit_after_costs_wei": str(int(sr.profit_after_costs_wei)),
                "continuity": dict(continuity),
            }
        )
        if not safety.get("gas_limit"):
            try:
                safety["gas_limit"] = int(getattr(cfg.execution, "gas_limit", 0) or 0)
            except (AttributeError, TypeError, ValueError):
                pass
        meta["safety"] = safety
    set_profitability_state(opp, state)
    unit_econ = _safe_dict(meta.get("unit_econ"))
    unit_econ["profitability_revalidated"] = bool(state.get("revalidated", False)) and bool(
        state.get("valid", False)
    )
    meta["unit_econ"] = unit_econ
    return dict(state)


def refresh_post_mutation_revalidation_contract(
    opp: Any,
    cfg: Any,
    *,
    stage: str,
    source: str,
    route_context: Mapping[str, Any] | None = None,
    gas_cost_wei: int | None = None,
) -> Dict[str, Any]:
    meta = _raw_meta(opp)
    continuity = assess_post_mutation_profitability_continuity(
        opp,
        cfg,
        route_context=route_context,
        existing_continuity=_safe_dict(meta.get("profitability_continuity")),
    )
    if isinstance(getattr(opp, "meta", None), dict):
        opp.meta["profitability_continuity"] = dict(continuity)
    state = revalidate_profitability_state(
        opp,
        cfg,
        stage=stage,
        source=source,
        gas_cost_wei=gas_cost_wei,
    )
    meta = _raw_meta(opp)
    contract = build_post_mutation_revalidation_contract(
        state,
        source=str(source),
        route_context=route_context,
        safety=_safe_dict(meta.get("safety")),
        continuity=_safe_dict(meta.get("profitability_continuity")),
    )
    set_post_mutation_revalidation_contract(opp, contract)
    return dict(contract)


def profitability_state_view(opp: Any) -> Dict[str, Any]:
    meta = _raw_meta(opp)
    continuity = _safe_dict(meta.get("profitability_continuity"))
    safety = _safe_dict(meta.get("safety"))
    search_profitability = _safe_dict(meta.get("search_profitability"))
    post_mutation = _safe_dict(meta.get("post_mutation_revalidation"))
    profitability = _safe_dict(post_mutation.get("profitability")) or _safe_dict(
        meta.get("profitability")
    )
    unit_econ = _safe_dict(meta.get("unit_econ"))

    continuity_present = bool(continuity)
    continuity_valid = bool(continuity.get("valid", True)) if continuity_present else True

    if profitability:
        profitability_continuity = _safe_dict(profitability.get("continuity")) or continuity
        continuity_present = bool(profitability_continuity)
        continuity_valid = (
            bool(profitability_continuity.get("valid", True)) if continuity_present else True
        )
        revalidated = bool(profitability.get("revalidated", False))
        stale = bool(
            profitability.get(
                "stale",
                (continuity_present and not continuity_valid)
                or (continuity_present and not revalidated),
            )
        )
        gross_profit_wei_int = _safe_int(
            profitability.get("gross_profit_wei") or _raw_attr(opp, "expected_profit_raw"), 0
        )
        after_costs_wei_int = _safe_int(
            profitability.get("profit_after_costs_wei")
            or safety.get("profit_after_costs_wei")
            or meta.get("profit_after_all_costs_estimate_wei")
            or search_profitability.get("profit_after_costs_wei")
            or meta.get("profit_after_gas_estimate_wei"),
            0,
        )
        expected_profit_usd = _safe_float(
            profitability.get("expected_profit_usd")
            or _raw_attr(opp, "expected_profit_usd")
            or unit_econ.get("expected_profit_usd_micro"),
            0.0,
        )
        if expected_profit_usd > _MICRO_USD_THRESHOLD:
            expected_profit_usd /= 1_000_000.0
        after_costs_usd_micro_int = _safe_int(
            profitability.get("profit_after_costs_usd_micro")
            or safety.get("profit_after_costs_usd_micro")
            or meta.get("profit_after_gas_estimate_usd_micro"),
            0,
        )
        return {
            "stage": str(
                post_mutation.get("stage") or profitability.get("stage") or "legacy_projected"
            ),
            "source": str(post_mutation.get("source") or profitability.get("source") or "legacy"),
            "reason": str(
                post_mutation.get("reason_code")
                or profitability.get("reason")
                or profitability_continuity.get("reason")
                or safety.get("reason")
                or search_profitability.get("reason")
                or ("ok" if not stale else "profitability_metadata_stale")
            ),
            "revalidated": revalidated,
            "stale": stale,
            "valid": bool(profitability.get("valid", not stale)),
            "authoritative": bool(profitability.get("authoritative", revalidated and not stale)),
            "continuity": profitability_continuity,
            "continuityPresent": continuity_present,
            "continuityValid": continuity_valid,
            "grossProfitWeiInt": gross_profit_wei_int,
            "profitAfterCostsWeiInt": after_costs_wei_int,
            "expectedProfitUsd": expected_profit_usd,
            "profitAfterCostsUsdMicroInt": after_costs_usd_micro_int,
            "amountInWeiInt": _safe_int(profitability.get("amount_in_wei"), 0),
            "amountOutWeiInt": _safe_int(profitability.get("amount_out_wei"), 0),
            "gasCostWeiInt": _safe_int(
                profitability.get("gas_cost_wei") or safety.get("gas_cost_wei"), 0
            ),
            "flashloanFeeWeiInt": _safe_int(
                profitability.get("flashloan_fee_wei") or safety.get("flashloan_fee_wei"), 0
            ),
        }

    safety_revalidated = bool(safety.get("revalidated", not continuity_present))
    stale = (continuity_present and not continuity_valid) or (
        continuity_present and not safety_revalidated
    )
    gross_profit_wei_int = _safe_int(_raw_attr(opp, "expected_profit_raw"), 0)
    after_costs_wei_int = _safe_int(
        safety.get("profit_after_costs_wei")
        or meta.get("profit_after_all_costs_estimate_wei")
        or search_profitability.get("profit_after_costs_wei")
        or meta.get("profit_after_gas_estimate_wei"),
        0,
    )
    expected_profit_usd = _safe_float(
        _raw_attr(opp, "expected_profit_usd") or unit_econ.get("expected_profit_usd_micro"),
        0.0,
    )
    if expected_profit_usd > _MICRO_USD_THRESHOLD:
        expected_profit_usd /= 1_000_000.0
    after_costs_usd_micro_int = _safe_int(
        safety.get("profit_after_costs_usd_micro")
        or meta.get("profit_after_gas_estimate_usd_micro"),
        0,
    )
    return {
        "stage": str(
            search_profitability.get("stage")
            or ("safety_revalidated" if safety else "legacy_projected")
        ),
        "source": str(search_profitability.get("stage") or "legacy"),
        "reason": str(
            continuity.get("reason")
            or safety.get("reason")
            or search_profitability.get("reason")
            or ("ok" if not stale else "profitability_metadata_stale")
        ),
        "revalidated": safety_revalidated,
        "stale": stale,
        "valid": bool((not stale) and after_costs_wei_int > 0),
        "authoritative": bool(bool(safety) and safety_revalidated and not stale),
        "continuity": continuity,
        "continuityPresent": continuity_present,
        "continuityValid": continuity_valid,
        "grossProfitWeiInt": gross_profit_wei_int,
        "profitAfterCostsWeiInt": after_costs_wei_int,
        "expectedProfitUsd": expected_profit_usd,
        "profitAfterCostsUsdMicroInt": after_costs_usd_micro_int,
        "amountInWeiInt": 0,
        "amountOutWeiInt": 0,
        "gasCostWeiInt": _safe_int(
            safety.get("gas_cost_wei") or meta.get("gas_cost_estimate_wei"), 0
        ),
        "flashloanFeeWeiInt": _safe_int(safety.get("flashloan_fee_wei"), 0),
    }
