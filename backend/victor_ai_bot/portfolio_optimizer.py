from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, InvalidOperation
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Set, Tuple


_ROUTE_RUNTIME_REASON_ALIASES = {
    "plan_profit_after_costs_invalid": "profit_after_costs_invalid",
    "plan_profit_after_costs_mismatch": "profit_after_costs_mismatch",
}


_SAFE_CANDIDATE_BUILD_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_INT_COERCE_EXCEPTIONS = (TypeError, ValueError)
_SAFE_LIST_COERCE_EXCEPTIONS = (TypeError, ValueError)
_USD_TO_WEI_SCALE = Decimal(10) ** 18
_FAMILY_CAPITAL_ALIASES = {
    "flash_arb": "flashloan_atomic",
    "cex_dex_arb": "cross_cex_dex",
    "liquidation_capture": "liquidation_anticipation",
}


@dataclass
class Candidate:
    opp_id: str
    route_id: str
    ev_wei: int
    gas_cost_wei: int
    conflict_keys: List[str]
    correlation_key: str = ""
    strategy_family: str = ""
    engine_type: str = ""
    chain: str = ""
    token_keys: List[str] = field(default_factory=list)
    venue_keys: List[str] = field(default_factory=list)
    capital_required_wei: int = 0
    path_id: str = ""
    p_success: float = 1.0
    quality_edge_wei: int = 0
    route_quality_score: float = 1.0


def _meta_mapping(opp: Any) -> Mapping[str, Any]:
    meta = getattr(opp, "meta", None)
    return meta if isinstance(meta, Mapping) else {}


def _coerce_int(value: Any, default: int = 0) -> int:
    amount = _coerce_decimal(value)
    if amount is None:
        return int(default)
    try:
        return int(amount)
    except (OverflowError, ValueError):
        return int(default)


def _coerce_ceil_int(value: Any, default: int = 0) -> int:
    amount = _coerce_decimal(value)
    if amount is None:
        return int(default)
    try:
        return int(amount.to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, OverflowError, ValueError):
        return int(default)


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    try:
        return list(value)
    except _SAFE_LIST_COERCE_EXCEPTIONS:
        return []


def _obj_field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _canonical_family_name(value: Any) -> str:
    family = str(value or "").strip()
    return str(_FAMILY_CAPITAL_ALIASES.get(family, family) or family)


def _coerce_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _usd_to_budget_wei(value: Any) -> int:
    amount = _coerce_decimal(value)
    if amount is None or amount <= 0:
        return 0
    return int((amount * _USD_TO_WEI_SCALE).to_integral_value(rounding=ROUND_CEILING))


def _candidate_gas_cost_wei(c: Candidate) -> int:
    return max(0, _coerce_ceil_int(getattr(c, "gas_cost_wei", 0), 0))


def _candidate_capital_required_wei(c: Candidate) -> int:
    return max(0, _coerce_ceil_int(getattr(c, "capital_required_wei", 0), 0))


def _candidate_ev_wei(c: Candidate) -> int:
    return _coerce_int(getattr(c, "ev_wei", 0), 0)


def _candidate_quality_edge_wei(c: Candidate, adjusted_ev: int) -> int:
    return max(0, _coerce_int(getattr(c, "quality_edge_wei", adjusted_ev), adjusted_ev))


def _canonical_family_capital_limits(
    family_capital_remaining_wei: Dict[str, int] | None,
) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for raw_key, raw_value in dict(family_capital_remaining_wei or {}).items():
        family = _canonical_family_name(raw_key)
        if not family:
            continue
        value = max(0, _coerce_int(raw_value, 0))
        existing = out.get(family)
        out[family] = value if existing is None else min(existing, value)
    return out


def _route_legs(opp: Any) -> List[Any]:
    route = getattr(opp, "route", None)
    legs = _obj_field(route, "legs", [])
    return [x for x in _coerce_list(legs) if x is not None]


def _nonempty_strings(values: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _ordered_route_tokens(opp: Any) -> List[str]:
    ordered: List[str] = []
    seen: Set[str] = set()
    for leg in _route_legs(opp):
        for key in ("token_in", "token_out"):
            token = str(_obj_field(leg, key, "") or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            ordered.append(token)
    return ordered


def _route_venues(opp: Any) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for leg in _route_legs(opp):
        venue = str(_obj_field(leg, "venue", "") or _obj_field(leg, "dex", "") or "").strip()
        if not venue or venue in seen:
            continue
        seen.add(venue)
        out.append(venue)
    return out


def _route_conflict_keys(opp: Any, rid: str) -> List[str]:
    keys: List[str] = []
    seen: Set[str] = set()
    for idx, leg in enumerate(_route_legs(opp)):
        venue = (
            str(_obj_field(leg, "venue", "") or _obj_field(leg, "dex", "") or "unknown").strip()
            or "unknown"
        )
        token_in = str(_obj_field(leg, "token_in", "") or "").strip()
        token_out = str(_obj_field(leg, "token_out", "") or "").strip()
        aux = str(_obj_field(leg, "data", "") or "").strip()
        pair = sorted([x for x in (token_in, token_out) if x])
        pair_key = ":".join(pair) if pair else f"leg{idx}"
        key = f"routeleg:{venue}:{pair_key}:{aux or rid or idx}"
        if key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _infer_capital_required_wei(opp: Any, meta: Mapping[str, Any]) -> int:
    for key in ("capital_required_wei", "capitalRequiredWei"):
        direct = _coerce_ceil_int(meta.get(key), 0)
        if direct > 0:
            return direct
    for attr in ("capital_required_wei", "capitalRequiredWei"):
        direct = _coerce_ceil_int(getattr(opp, attr, 0), 0)
        if direct > 0:
            return direct
    for key in (
        "capital_required_usd",
        "capitalRequiredUsd",
        "notional_usd",
        "notionalUsd",
        "repayUsd",
    ):
        direct = _usd_to_budget_wei(meta.get(key))
        if direct > 0:
            return direct
    for attr in ("capital_required_usd", "capitalRequiredUsd", "notional_usd", "notionalUsd"):
        direct = _usd_to_budget_wei(getattr(opp, attr, 0))
        if direct > 0:
            return direct
    return 0


def _route_runtime_reason_codes(runtime: Mapping[str, Any]) -> List[str]:
    codes: List[str] = []
    for bucket in ("input", "legs", "mutation", "profit"):
        state = _obj_field(runtime, bucket, {})
        state = state if isinstance(state, Mapping) else {}
        if state and not bool(_obj_field(state, "ok", True)):
            code = str(
                _obj_field(state, "code", f"execution_route_{bucket}_degraded")
                or f"execution_route_{bucket}_degraded"
            )
            code = str(_ROUTE_RUNTIME_REASON_ALIASES.get(code, code) or code)
            if code and code not in codes:
                codes.append(code)
    return codes


def opportunity_route_ready(opp: Any) -> Tuple[bool, str, List[str]]:
    meta = _meta_mapping(opp)
    execution_plan = _obj_field(meta, "execution_route_plan", {})
    execution_plan = execution_plan if isinstance(execution_plan, Mapping) else {}
    raw_invalid_causes = list(_obj_field(execution_plan, "route_invalid_causes", []) or []) + list(
        _obj_field(meta, "route_invalid_causes", []) or []
    )
    invalid_causes = _nonempty_strings(raw_invalid_causes)
    route_plan_executable = (
        bool(_obj_field(execution_plan, "executable", True)) if execution_plan else True
    )
    route_runtime = _obj_field(meta, "execution_route_runtime", {})
    route_runtime = route_runtime if isinstance(route_runtime, Mapping) else {}
    runtime_reason_codes = _route_runtime_reason_codes(route_runtime)
    route_runtime_degraded = bool(_obj_field(route_runtime, "degraded", False)) or bool(
        runtime_reason_codes
    )
    if execution_plan and not route_plan_executable:
        reason = str(invalid_causes[0] if invalid_causes else "route_plan_not_executable")
        return False, reason, list(invalid_causes or [reason])
    if invalid_causes:
        return False, str(invalid_causes[0]), list(invalid_causes)
    if route_runtime_degraded:
        reason = str(
            runtime_reason_codes[0] if runtime_reason_codes else "execution_route_runtime_degraded"
        )
        return False, reason, list(runtime_reason_codes or [reason])
    return True, "ok", []


def _route_quality_from_meta(meta: Mapping[str, Any]) -> float:
    explicit = meta.get("route_quality_score")
    if explicit is None:
        explicit = meta.get("route_quality")
    if explicit is None:
        explicit = meta.get("calibrationQuality")
    if explicit not in (None, ""):
        try:
            return _clip(float(str(explicit)), 0.20, 1.20)
        except _SAFE_INT_COERCE_EXCEPTIONS:
            pass
    route_plan_value = meta.get("route_plan")
    route_plan: Mapping[str, Any] = (
        route_plan_value if isinstance(route_plan_value, Mapping) else {}
    )
    exec_plan_value = meta.get("execution_route_plan")
    exec_plan: Mapping[str, Any] = exec_plan_value if isinstance(exec_plan_value, Mapping) else {}
    for plan in (exec_plan, route_plan):
        split = _coerce_list(plan.get("split"))
        qualities: List[float] = []
        for row in split:
            raw = _obj_field(row, "venue_quality", None)
            try:
                if raw is not None:
                    qualities.append(_clip(float(raw), 0.20, 1.20))
            except _SAFE_INT_COERCE_EXCEPTIONS:
                continue
        if qualities:
            return float(round(mean(qualities), 6))
    return 1.0


def _quality_edge_wei(meta: Mapping[str, Any], *, ev_wei: int) -> int:
    brain = meta.get("brain") if isinstance(meta.get("brain"), Mapping) else {}
    raw = brain.get("ev_score_wei") if isinstance(brain, Mapping) else None
    scored = _coerce_int(raw, 0)
    return scored if scored > 0 else int(max(0, ev_wei))


def _success_probability(meta: Mapping[str, Any]) -> float:
    brain = meta.get("brain") if isinstance(meta.get("brain"), Mapping) else {}
    raw = brain.get("p_success") if isinstance(brain, Mapping) else None
    try:
        if raw is None:
            return 1.0
        return _clip(float(raw), 0.05, 1.0)
    except _SAFE_INT_COERCE_EXCEPTIONS:
        return 1.0


def _derived_path_id(*, corr: str, rid: str) -> str:
    return f"{corr}:{rid}"


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _base_adjusted_ev(
    c: Candidate,
    *,
    used_correlation: Set[str],
    covariance_penalties: Dict[str, float],
    path_penalties: Dict[str, float],
) -> int:
    ev_effective = _candidate_ev_wei(c)
    if c.correlation_key and c.correlation_key in used_correlation:
        ev_effective = int(ev_effective * 0.72)
    if c.strategy_family:
        ev_effective = int(
            ev_effective
            * max(0.65, 1.0 - float(covariance_penalties.get(c.strategy_family, 0.0) or 0.0))
        )
    if c.path_id:
        ev_effective = int(
            ev_effective * max(0.60, 1.0 - float(path_penalties.get(c.path_id, 0.0) or 0.0))
        )
    return ev_effective


def _capital_efficiency(c: Candidate, adjusted_ev: int) -> float:
    capital_required = max(1, _candidate_capital_required_wei(c))
    edge_ratio = float(max(0, adjusted_ev)) / float(capital_required)
    # compress to a stable 0.75-1.25 band so we prefer capital-efficient trades
    # without overwhelming realized-edge ranking.
    return _clip(0.75 + min(0.50, edge_ratio * 5.0), 0.75, 1.25)


def _candidate_family(c: Candidate) -> str:
    return _canonical_family_name(c.strategy_family)


def _crowding_penalty(
    c: Candidate,
    *,
    picked: List[Candidate],
    used_tokens: Set[str],
    used_venues: Set[str],
    family_counts: Dict[str, int],
    engine_counts: Dict[str, int],
) -> float:
    penalty = 1.0
    if c.token_keys:
        shared_tokens = sum(1 for t in c.token_keys if t in used_tokens)
        penalty -= min(0.18, 0.06 * shared_tokens)
    if c.venue_keys:
        shared_venues = sum(1 for v in c.venue_keys if v in used_venues)
        penalty -= min(0.18, 0.06 * shared_venues)
    family = _candidate_family(c)
    if family:
        penalty -= min(0.15, 0.08 * family_counts.get(family, 0))
    if c.engine_type:
        penalty -= min(0.10, 0.05 * engine_counts.get(c.engine_type, 0))
    if c.chain and picked and all(str(getattr(p, "chain", "") or "") == c.chain for p in picked):
        penalty -= 0.03
    return _clip(penalty, 0.55, 1.0)


def _score_tuple(
    c: Candidate,
    *,
    adjusted_ev: int,
    picked: List[Candidate],
    used_tokens: Set[str],
    used_venues: Set[str],
    family_counts: Dict[str, int],
    engine_counts: Dict[str, int],
) -> Tuple[float, float, float, int]:
    gas = max(1, _candidate_gas_cost_wei(c))
    crowd_penalty = _crowding_penalty(
        c,
        picked=picked,
        used_tokens=used_tokens,
        used_venues=used_venues,
        family_counts=family_counts,
        engine_counts=engine_counts,
    )
    capital_efficiency = _capital_efficiency(c, adjusted_ev)
    quality_edge = _candidate_quality_edge_wei(c, adjusted_ev)
    quality_ratio = 1.0
    if adjusted_ev > 0:
        quality_ratio = _clip(float(quality_edge) / float(max(1, adjusted_ev)), 0.70, 1.0)
    reliability_mult = _clip(0.70 + (0.30 * float(c.p_success or 1.0)), 0.70, 1.0)
    route_quality_mult = _clip(0.80 + (0.20 * float(c.route_quality_score or 1.0)), 0.80, 1.0)
    quality_mult = quality_ratio * reliability_mult * route_quality_mult
    score = (float(adjusted_ev) * quality_mult * crowd_penalty * capital_efficiency) / float(gas)
    return (score, capital_efficiency, quality_mult, int(adjusted_ev))


def select_portfolio(
    candidates: List[Candidate],
    *,
    gas_budget_remaining_wei: int,
    max_trades: int,
    family_caps: Dict[str, int] | None = None,
    engine_caps: Dict[str, int] | None = None,
    covariance_penalties: Dict[str, float] | None = None,
    path_penalties: Dict[str, float] | None = None,
    capital_budget_remaining_wei: int | None = None,
    family_capital_remaining_wei: Dict[str, int] | None = None,
) -> List[Candidate]:
    """Select a non-conflicting set of trades under a gas budget.

    Design constraints:
    - Must be fast (bounded greedy, no RPC)
    - Must not require global portfolio state
    - Conflict is defined via `conflict_keys` (pool-level keys)

    Algorithm:
    - Iteratively choose the best marginal candidate that fits the gas budget.
    - Base EV is adjusted by correlation/path/family penalties already known locally.
    - Additive crowding penalties reduce concentration across token paths, venues,
      family reuse, and engine reuse.
    - Capital efficiency is a secondary preference so equal-EV trades that lock
      less capital are preferred, without dominating realized-edge ranking.
    - When provided, deployable-capital and family-capital budgets are treated as
      hard fail-closed constraints, not soft preferences.
    """
    if max_trades <= 0 or gas_budget_remaining_wei <= 0:
        return []

    family_caps = _canonical_family_capital_limits(family_caps)
    engine_caps = dict(engine_caps or {})
    covariance_penalties = dict(covariance_penalties or {})
    path_penalties = dict(path_penalties or {})
    capital_limit_wei = None
    if capital_budget_remaining_wei is not None:
        capital_limit_wei = max(0, _coerce_int(capital_budget_remaining_wei, 0))
    family_capital_limits = _canonical_family_capital_limits(family_capital_remaining_wei)
    ordered = sorted(
        candidates,
        key=lambda c: (
            _coerce_int(getattr(c, "ev_wei", 0), 0),
            -_candidate_gas_cost_wei(c),
            -_candidate_capital_required_wei(c),
        ),
        reverse=True,
    )

    picked: List[Candidate] = []
    used_conflicts: Set[str] = set()
    used_gas = 0
    used_capital_wei = 0
    used_correlation: Set[str] = set()
    used_tokens: Set[str] = set()
    used_venues: Set[str] = set()
    family_counts: Dict[str, int] = {}
    engine_counts: Dict[str, int] = {}
    family_capital_used_wei: Dict[str, int] = {}
    remaining = list(ordered)

    while remaining and len(picked) < max_trades:
        best_idx = -1
        best_score: Tuple[float, float, float, int] | None = None
        for idx, c in enumerate(remaining):
            if _candidate_ev_wei(c) <= 0:
                continue
            gc = _candidate_gas_cost_wei(c)
            if used_gas + gc > gas_budget_remaining_wei:
                continue
            capital_required = _candidate_capital_required_wei(c)
            family = _candidate_family(c)
            capital_truth_required = capital_limit_wei is not None or bool(family_capital_limits)
            if capital_truth_required and capital_required <= 0:
                continue
            if capital_limit_wei is not None and capital_required > 0:
                if used_capital_wei + capital_required > capital_limit_wei:
                    continue
            if family and capital_required > 0 and family in family_capital_limits:
                family_remaining = int(family_capital_limits[family])
                if family_capital_used_wei.get(family, 0) + capital_required > family_remaining:
                    continue
            if (
                family
                and family in family_caps
                and family_counts.get(family, 0) >= _coerce_int(family_caps[family], 0)
            ):
                continue
            if (
                c.engine_type
                and c.engine_type in engine_caps
                and engine_counts.get(c.engine_type, 0)
                >= _coerce_int(engine_caps[c.engine_type], 0)
            ):
                continue
            if any(k in used_conflicts for k in (c.conflict_keys or [])):
                continue
            adjusted_ev = _base_adjusted_ev(
                c,
                used_correlation=used_correlation,
                covariance_penalties=covariance_penalties,
                path_penalties=path_penalties,
            )
            if adjusted_ev <= 0:
                continue
            score = _score_tuple(
                c,
                adjusted_ev=adjusted_ev,
                picked=picked,
                used_tokens=used_tokens,
                used_venues=used_venues,
                family_counts=family_counts,
                engine_counts=engine_counts,
            )
            if best_score is None or score > best_score:
                best_idx = idx
                best_score = score
        if best_idx < 0:
            break
        c = remaining.pop(best_idx)
        picked.append(c)
        used_gas += _candidate_gas_cost_wei(c)
        used_capital_wei += _candidate_capital_required_wei(c)
        family = _candidate_family(c)
        if family:
            family_counts[family] = family_counts.get(family, 0) + 1
            family_capital_used_wei[family] = family_capital_used_wei.get(family, 0) + int(
                _candidate_capital_required_wei(c)
            )
        if c.engine_type:
            engine_counts[c.engine_type] = engine_counts.get(c.engine_type, 0) + 1
        if c.correlation_key:
            used_correlation.add(c.correlation_key)
        for k in c.conflict_keys or []:
            used_conflicts.add(k)
        for t in c.token_keys or []:
            used_tokens.add(str(t))
        for v in c.venue_keys or []:
            used_venues.add(str(v))

    return picked


def candidates_from_opps(opps: List[Any]) -> List[Candidate]:
    out: List[Candidate] = []
    for o in opps:
        try:
            meta = _meta_mapping(o)
            route_ready, _route_reason, _route_reason_codes = opportunity_route_ready(o)
            if not route_ready:
                continue
            brain_value = meta.get("brain")
            brain: Mapping[str, Any] = brain_value if isinstance(brain_value, Mapping) else {}
            safety_value = meta.get("safety")
            safety: Mapping[str, Any] = safety_value if isinstance(safety_value, Mapping) else {}
            ev = _coerce_int(brain.get("ev_wei"), 0)
            rid = str(getattr(o, "route_id", "") or "")
            gc = _coerce_ceil_int(safety.get("gas_cost_wei"), 0)
            corr = str(meta.get("route_family") or "")
            fam = _canonical_family_name(
                meta.get("strategy_family") or getattr(o, "strategy", "") or ""
            )
            eng = str(meta.get("engine_type") or "")
            chain = str(meta.get("chain") or getattr(o, "chain", "") or "")

            route_tokens = _ordered_route_tokens(o)
            route_venues = _route_venues(o)
            conflicts = _coerce_list(meta.get("pool_keys"))
            toks = _coerce_list(meta.get("token_path"))
            vens = _coerce_list(meta.get("venues"))
            cap_req = _infer_capital_required_wei(o, meta)
            path_id = str(meta.get("path_id") or "")

            conflict_keys = _nonempty_strings(conflicts) or _route_conflict_keys(o, rid)
            token_keys = _nonempty_strings(toks) or route_tokens
            venue_keys = _nonempty_strings(vens) or route_venues
            derived_path_id = path_id or _derived_path_id(corr=corr, rid=rid)
            p_success = _success_probability(meta)
            quality_edge = _quality_edge_wei(meta, ev_wei=ev)
            route_quality_score = _route_quality_from_meta(meta)

            out.append(
                Candidate(
                    opp_id=str(getattr(o, "id", "")),
                    route_id=rid,
                    ev_wei=ev,
                    gas_cost_wei=gc,
                    conflict_keys=conflict_keys,
                    correlation_key=corr,
                    strategy_family=fam,
                    engine_type=eng,
                    chain=chain,
                    token_keys=token_keys,
                    venue_keys=venue_keys,
                    capital_required_wei=cap_req,
                    path_id=derived_path_id,
                    p_success=p_success,
                    quality_edge_wei=quality_edge,
                    route_quality_score=route_quality_score,
                )
            )
        except _SAFE_CANDIDATE_BUILD_EXCEPTIONS:
            continue
    return out
