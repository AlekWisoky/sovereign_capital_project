from __future__ import annotations

"""Bounded gas-adjusted split economics for independent arbitrage cycles.

This module is diagnostic-only: executor ABI v2 accepts one sequential route,
not multiple independent cycles funded from partitions of one flash loan.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Mapping, Sequence


_SHARED_EXECUTION_OVERHEAD_GAS_UNITS = 180_000 + 90_000
_EXTRA_SPLIT_ROUTE_GAS_UNITS = 75_000  # planning heuristic, not an upper bound
_DEFAULT_MAX_ROUTES = 3
_DEFAULT_MAX_CANDIDATES_PER_AMOUNT = 8
_DEFAULT_MAX_SEARCH_STATES = 2_000
_DEFAULT_MAX_PLANS = 8
_DIVERSITY_TOLERANCE_BPS = 50
_EXACT_BASE_L1_STATUSES = {"exact_calldata", "exact_calldata_cached"}


@dataclass(frozen=True)
class _SplitSearchLimits:
    max_routes: int = _DEFAULT_MAX_ROUTES
    max_candidates_per_amount: int = _DEFAULT_MAX_CANDIDATES_PER_AMOUNT
    max_search_states: int = _DEFAULT_MAX_SEARCH_STATES
    max_plans: int = _DEFAULT_MAX_PLANS


@dataclass
class _SplitSearchState:
    borrow_token: str
    target_amount: int
    candidates: List[Dict[str, Any]]
    best_single_net: int | None
    limits: _SplitSearchLimits
    states_seen: int = 0
    combinations_evaluated: int = 0
    best_plan: Dict[str, Any] | None = None


@dataclass(frozen=True)
class _PartialSplit:
    start_index: int
    remaining_amount: int
    parts: tuple[Dict[str, Any], ...] = ()
    used_route_ids: frozenset[str] = frozenset()
    used_pool_keys: frozenset[str] = frozenset()


def _int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _leg_pool_key(leg: Mapping[str, Any]) -> str | None:
    """Return a conservative physical-pool identity, not a router identity."""
    dex = str(leg.get("dex") or "").strip().lower()
    token_in = str(leg.get("token_in") or "").strip().lower()
    token_out = str(leg.get("token_out") or "").strip().lower()
    venue = str(leg.get("venue") or "").strip().lower()
    aux = str(leg.get("data") or leg.get("aux") or "0x").strip().lower()
    if not dex or not token_in or not token_out or token_in == token_out:
        return None
    pair = "|".join(sorted((token_in, token_out)))
    if dex == "curve":
        # Coin indices select a direction inside the pool; they do not create
        # a new physical pool identity.
        return f"curve|{venue}" if venue else None
    if dex == "balancer":
        return f"balancer|{aux}" if aux not in {"", "0x"} else None
    if not venue:
        return None
    if dex in {"camelot_algebra", "camelot_v2", "constant_product"}:
        return f"{dex}|{venue}|{pair}"
    if dex in {"univ3", "slipstream", "aerodrome"}:
        return f"{dex}|{venue}|{pair}|{aux}" if aux not in {"", "0x"} else None
    return f"{dex}|{venue}|{pair}|{aux}"


def _candidate_numeric_values(candidate: Mapping[str, Any]) -> Dict[str, int] | None:
    fields = {
        "amount": "amount_in",
        "gross": "gross_profit_wei",
        "fee": "flashloan_fee_wei",
        "gas_token": "gas_cost_profit_token_wei",
        "native_cost": "gas_cost_wei",
        "l2_gas": "gas_cost_l2_wei",
        "gas_units": "gas_units_estimate",
        "l1_fee": "base_l1_fee_wei",
    }
    values: Dict[str, int] = {}
    for output_key, input_key in fields.items():
        value = _int(candidate.get(input_key))
        if value is None:
            return None
        values[output_key] = value
    return values


def _has_positive_repay_evidence(
    candidate: Mapping[str, Any], values: Mapping[str, int]
) -> bool:
    return bool(
        values["amount"] > 0
        and values["gross"] > 0
        and values["fee"] >= 0
        and values["gas_token"] > 0
        and candidate.get("repayment_valid") is True
    )


def _has_complete_gas_evidence(values: Mapping[str, int]) -> bool:
    return bool(
        values["native_cost"] > 0
        and values["l2_gas"] > 0
        and values["gas_units"] > _SHARED_EXECUTION_OVERHEAD_GAS_UNITS
        and values["l1_fee"] >= 0
    )


def _base_fee_evidence_is_adequate(
    candidate: Mapping[str, Any], chain_id: int
) -> bool:
    if int(chain_id) != 8453:
        return True
    return str(candidate.get("base_l1_fee_status") or "") in _EXACT_BASE_L1_STATUSES


def _route_leg_identity(
    leg: Mapping[str, Any], expected_token_in: str
) -> Dict[str, str] | None:
    token_in = str(leg.get("token_in") or "").strip().lower()
    token_out = str(leg.get("token_out") or "").strip().lower()
    protocol = str(leg.get("dex") or "").strip().lower()
    pool_key = _leg_pool_key(leg)
    if not token_in or not token_out or token_in == token_out:
        return None
    if token_in != expected_token_in or not protocol or pool_key is None:
        return None
    venue = str(leg.get("venue") or "").strip().lower()
    return {
        "token_in": token_in,
        "token_out": token_out,
        "protocol": protocol,
        "pool_key": pool_key,
        "venue": venue,
        "directed_pair": f"{token_in}->{token_out}",
    }


def _cycle_identity(
    legs: Sequence[Mapping[str, Any]], amount_in: int
) -> Dict[str, Any] | None:
    if len(legs) not in (2, 3):
        return None
    first_amount = _int(legs[0].get("amount_in"))
    if first_amount != amount_in:
        return None
    borrow_token = str(legs[0].get("token_in") or "").strip().lower()
    if not borrow_token:
        return None

    prior_token = borrow_token
    pool_keys: List[str] = []
    protocols: set[str] = set()
    routers: set[str] = set()
    directed_pairs: set[str] = set()
    for leg in legs:
        identity = _route_leg_identity(leg, prior_token)
        if identity is None:
            return None
        prior_token = identity["token_out"]
        pool_keys.append(identity["pool_key"])
        protocols.add(identity["protocol"])
        directed_pairs.add(identity["directed_pair"])
        if identity["venue"] and identity["protocol"] != "curve":
            routers.add(identity["venue"])

    if prior_token != borrow_token or len(pool_keys) != len(set(pool_keys)):
        return None
    return {
        "borrow_token": borrow_token,
        "pool_keys": set(pool_keys),
        "protocols": protocols,
        "routers": routers,
        "directed_pairs": directed_pairs,
    }


def _candidate_evidence_rank(row: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    """Prefer valid authoritative economics before a larger diagnostic estimate."""
    return (
        int(bool(row.get("revalidated") and row.get("authoritative") and row.get("valid") and row.get("repayment_valid"))),
        int(bool(row.get("authoritative"))),
        int(bool(row.get("revalidated"))),
        int(row.get("single_route_net_wei") or 0),
        int(row.get("gross_profit_wei") or 0),
    )


def _normalize_candidate(
    candidate: Mapping[str, Any], *, chain_id: int
) -> Dict[str, Any] | None:
    route_id = str(candidate.get("route_id") or "")
    if not route_id:
        return None
    values = _candidate_numeric_values(candidate)
    if values is None:
        return None
    if not _has_positive_repay_evidence(candidate, values):
        return None
    if not _has_complete_gas_evidence(values):
        return None
    if not _base_fee_evidence_is_adequate(candidate, int(chain_id)):
        return None

    legs = [dict(row) for row in candidate.get("legs", []) if isinstance(row, Mapping)]
    identity = _cycle_identity(legs, values["amount"])
    if identity is None:
        return None

    l2_price = max(1, (values["l2_gas"] + values["gas_units"] - 1) // values["gas_units"])
    conversion = Fraction(values["gas_token"], values["native_cost"])
    return {
        "route_id": route_id,
        "amount_in": values["amount"],
        "gross_profit_wei": values["gross"],
        "flashloan_fee_wei": values["fee"],
        "gas_cost_profit_token_wei": values["gas_token"],
        "gas_cost_wei": values["native_cost"],
        "gas_cost_l2_wei": values["l2_gas"],
        "gas_units_estimate": values["gas_units"],
        "gas_price_effective_wei": l2_price,
        "base_l1_fee_wei": values["l1_fee"],
        "base_l1_fee_status": str(candidate.get("base_l1_fee_status") or ""),
        "borrow_token": identity["borrow_token"],
        "legs": legs,
        "pool_keys": identity["pool_keys"],
        "protocols": identity["protocols"],
        "routers": identity["routers"],
        "directed_pairs": identity["directed_pairs"],
        "single_route_net_wei": values["gross"] - values["fee"] - values["gas_token"],
        "gas_token_per_native_wei": conversion,
        "revalidated": candidate.get("revalidated") is True,
        "authoritative": candidate.get("authoritative") is True,
        "valid": candidate.get("valid") is True,
        "repayment_valid": candidate.get("repayment_valid") is True,
    }


def _size_row_has_quote_success(size_row: Mapping[str, Any]) -> bool:
    return bool(
        (_int(size_row.get("quote_requests")) or 0) > 0
        and (_int(size_row.get("quote_successes")) or 0) > 0
    )


def _iter_quote_backed_candidates(
    size_matrix: Sequence[Mapping[str, Any]],
):
    for size_row in size_matrix:
        if not isinstance(size_row, Mapping) or not _size_row_has_quote_success(size_row):
            continue
        for row in size_row.get("candidates", []) or []:
            if isinstance(row, Mapping):
                yield row


def _deduplicate_candidates(
    raw_candidates: Sequence[Mapping[str, Any]], chain_id: int
) -> Dict[tuple[str, int, str], Dict[str, Any]]:
    unique: Dict[tuple[str, int, str], Dict[str, Any]] = {}
    for raw in raw_candidates:
        candidate = _normalize_candidate(raw, chain_id=chain_id)
        if candidate is None:
            continue
        key = (
            candidate["borrow_token"],
            candidate["amount_in"],
            candidate["route_id"],
        )
        prior = unique.get(key)
        if prior is None or _candidate_evidence_rank(candidate) > _candidate_evidence_rank(prior):
            unique[key] = candidate
    return unique


def _group_candidates_by_token_and_amount(
    candidates: Sequence[Mapping[str, Any]],
) -> Dict[str, Dict[int, List[Dict[str, Any]]]]:
    grouped: Dict[str, Dict[int, List[Dict[str, Any]]]] = {}
    for candidate in candidates:
        token = str(candidate["borrow_token"])
        amount = int(candidate["amount_in"])
        grouped.setdefault(token, {}).setdefault(amount, []).append(dict(candidate))
    return grouped


def _best_diverse_candidate_index(
    pending: Sequence[Mapping[str, Any]],
    chosen: Sequence[Mapping[str, Any]],
    best_net: int,
    tolerance: int,
) -> int:
    near_best = [
        idx for idx, row in enumerate(pending)
        if best_net - int(row["single_route_net_wei"]) <= tolerance
    ]
    if not near_best:
        return 0
    chosen_protocols = set().union(*(row["protocols"] for row in chosen))
    chosen_pools = set().union(*(row["pool_keys"] for row in chosen))
    return max(
        near_best,
        key=lambda idx: (
            len(pending[idx]["protocols"] - chosen_protocols),
            len(pending[idx]["pool_keys"] - chosen_pools),
            pending[idx]["single_route_net_wei"],
            pending[idx]["gross_profit_wei"],
        ),
    )


def _shortlist_amount_bucket(
    rows: Sequence[Mapping[str, Any]], max_candidates: int
) -> List[Dict[str, Any]]:
    pending = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            row["single_route_net_wei"],
            row["gross_profit_wei"],
            row["route_id"],
        ),
        reverse=True,
    )
    if not pending or max_candidates <= 0:
        return []
    chosen = [pending.pop(0)]
    best_net = int(chosen[0]["single_route_net_wei"])
    tolerance = max(1, abs(best_net) * _DIVERSITY_TOLERANCE_BPS // 10_000)
    while pending and len(chosen) < max_candidates:
        index = _best_diverse_candidate_index(pending, chosen, best_net, tolerance)
        chosen.append(pending.pop(index))
    return chosen


def _prepare_candidate_buckets(
    size_matrix: Sequence[Mapping[str, Any]], *, chain_id: int, max_per_amount: int
) -> Dict[str, List[Dict[str, Any]]]:
    raw_candidates = list(_iter_quote_backed_candidates(size_matrix))
    unique = _deduplicate_candidates(raw_candidates, int(chain_id))
    grouped = _group_candidates_by_token_and_amount(list(unique.values()))
    cap = max(1, min(int(max_per_amount), 12))
    return {
        token: [
            candidate
            for amount in sorted(amount_buckets)
            for candidate in _shortlist_amount_bucket(amount_buckets[amount], cap)
        ]
        for token, amount_buckets in grouped.items()
    }


def _split_cost_totals(parts: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    gross = sum(int(row["gross_profit_wei"]) for row in parts)
    fee = sum(int(row["flashloan_fee_wei"]) for row in parts) + max(0, len(parts) - 1)
    shared_units = _SHARED_EXECUTION_OVERHEAD_GAS_UNITS
    route_units = sum(
        max(0, int(row["gas_units_estimate"]) - _SHARED_EXECUTION_OVERHEAD_GAS_UNITS)
        for row in parts
    )
    extra_units = max(0, len(parts) - 1) * _EXTRA_SPLIT_ROUTE_GAS_UNITS
    l2_units = shared_units + route_units + extra_units
    gas_price = max(int(row["gas_price_effective_wei"]) for row in parts)
    l2_cost = l2_units * gas_price
    l1_cost = sum(int(row["base_l1_fee_wei"]) for row in parts)
    native_cost = l2_cost + l1_cost
    conversion = max(row["gas_token_per_native_wei"] for row in parts)
    gas_token_cost = (native_cost * conversion.numerator + conversion.denominator - 1) // conversion.denominator
    return {
        "amount": sum(int(row["amount_in"]) for row in parts),
        "gross": gross,
        "fee": fee,
        "l2_units": l2_units,
        "l2_cost": l2_cost,
        "l1_cost": l1_cost,
        "native_cost": native_cost,
        "gas_token_cost": gas_token_cost,
        "net": gross - fee - gas_token_cost,
    }


def _identity_coverage(parts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return {
        "unique_protocols": len(set().union(*(row["protocols"] for row in parts))),
        "unique_pool_keys": len(set().union(*(row["pool_keys"] for row in parts))),
        "unique_router_ids": len(set().union(*(row["routers"] for row in parts))),
        "unique_directed_pairs": len(set().union(*(row["directed_pairs"] for row in parts))),
        "router_identity_is_not_a_profit_score": True,
    }


def _allocation_leg(leg: Mapping[str, Any]) -> Dict[str, str]:
    return {
        "dex": str(leg.get("dex") or ""),
        "venue": str(leg.get("venue") or ""),
        "token_in": str(leg.get("token_in") or ""),
        "token_out": str(leg.get("token_out") or ""),
        "amount_in": str(leg.get("amount_in") or ""),
        "min_out": str(leg.get("min_out") or ""),
        "data": str(leg.get("data") or ""),
    }


def _allocation_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "route_id": str(row["route_id"]),
        "amount_in": str(row["amount_in"]),
        "gross_profit_wei": str(row["gross_profit_wei"]),
        "flashloan_fee_wei": str(row["flashloan_fee_wei"]),
        "gas_cost_profit_token_wei_observed": str(row["gas_cost_profit_token_wei"]),
        "protocols": sorted(row["protocols"]),
        "pool_keys": sorted(row["pool_keys"]),
        "router_ids": sorted(row["routers"]),
        "directed_pairs": sorted(row["directed_pairs"]),
        "legs": [_allocation_leg(leg) for leg in row["legs"]],
        "component_revalidated": bool(row["revalidated"]),
        "component_authoritative": bool(row["authoritative"]),
        "component_valid": bool(row["valid"]),
        "component_repayment_valid": bool(row["repayment_valid"]),
    }


def _evaluate_split(parts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    totals = _split_cost_totals(parts)
    route_ids = [str(row["route_id"]) for row in parts]
    return {
        "amount_in": str(totals["amount"]),
        "economic_comparison_scope": "within_borrow_token_only",
        "profit_units": "borrow_token_wei",
        "gross_profit_wei": str(totals["gross"]),
        "flashloan_fee_wei": str(totals["fee"]),
        "gas_cost_wei_estimate": str(totals["native_cost"]),
        "gas_cost_profit_token_wei_estimate": str(totals["gas_token_cost"]),
        "estimated_l2_gas_units": str(totals["l2_units"]),
        "estimated_l2_gas_cost_wei": str(totals["l2_cost"]),
        "estimated_l1_data_fee_wei": str(totals["l1_cost"]),
        "economic_after_cost_profit_wei": str(totals["net"]),
        "after_cost_positive_estimate": totals["net"] > 0,
        "revalidated": False,
        "authoritative": False,
        "valid": False,
        "execution_authority_granted": False,
        "execution_supported": False,
        "required_executor_abi_version": 3,
        "execution_block_reason": "executor_abi_v2_supports_one_sequential_route_only",
        "simulation_required_before_authority": True,
        "route_count": len(parts),
        "route_ids": route_ids,
        "identity_coverage": _identity_coverage(parts),
        "allocations": [_allocation_row(row) for row in parts],
    }


def _record_completed_split(
    state: _SplitSearchState, partial: _PartialSplit
) -> None:
    if len(partial.parts) < 2:
        return
    model = _evaluate_split(partial.parts)
    model["borrow_token"] = state.borrow_token
    best_single = state.best_single_net
    improvement = int(model["economic_after_cost_profit_wei"]) - best_single if best_single is not None else None
    model["best_single_route_net_wei_at_target"] = str(best_single) if best_single is not None else None
    model["improvement_over_best_single_wei"] = str(improvement) if improvement is not None else None
    model["better_than_best_single_estimate"] = improvement is not None and improvement > 0
    model["composite_route_key"] = "|".join(model["route_ids"])
    state.combinations_evaluated += 1
    if (
        state.best_plan is None
        or int(model["economic_after_cost_profit_wei"])
        > int(state.best_plan["economic_after_cost_profit_wei"])
    ):
        state.best_plan = model


def _extend_split_search(
    state: _SplitSearchState, partial: _PartialSplit
) -> None:
    for idx in range(partial.start_index, len(state.candidates)):
        row = state.candidates[idx]
        row_amount = int(row["amount_in"])
        if row_amount > partial.remaining_amount:
            continue
        route_id = str(row["route_id"])
        if route_id in partial.used_route_ids:
            continue
        pool_keys = frozenset(row["pool_keys"])
        if partial.used_pool_keys.intersection(pool_keys):
            continue
        child = _PartialSplit(
            start_index=idx + 1,
            remaining_amount=partial.remaining_amount - row_amount,
            parts=(*partial.parts, row),
            used_route_ids=partial.used_route_ids | {route_id},
            used_pool_keys=partial.used_pool_keys | pool_keys,
        )
        _walk_split_search(state, child)
        if state.states_seen >= state.limits.max_search_states:
            return


def _walk_split_search(state: _SplitSearchState, partial: _PartialSplit) -> None:
    if state.states_seen >= state.limits.max_search_states:
        return
    state.states_seen += 1
    if partial.remaining_amount == 0:
        _record_completed_split(state, partial)
        return
    if len(partial.parts) >= state.limits.max_routes:
        return
    _extend_split_search(state, partial)


def _new_target_search_state(
    token: str,
    candidates: Sequence[Mapping[str, Any]],
    target_amount: int,
    limits: _SplitSearchLimits,
) -> _SplitSearchState:
    single_route_nets = [
        int(row["single_route_net_wei"])
        for row in candidates
        if int(row["amount_in"]) == target_amount
    ]
    best_single_net = max(single_route_nets, default=None)
    amount_pool = sorted(
        [dict(row) for row in candidates if int(row["amount_in"]) <= target_amount],
        key=lambda row: (
            -int(row["single_route_net_wei"]),
            -int(row["gross_profit_wei"]),
            int(row["amount_in"]),
            str(row["route_id"]),
        ),
    )
    return _SplitSearchState(
        borrow_token=token,
        target_amount=target_amount,
        candidates=amount_pool,
        best_single_net=best_single_net,
        limits=limits,
    )


def _search_target_amount(
    token: str,
    candidates: Sequence[Mapping[str, Any]],
    target_amount: int,
    limits: _SplitSearchLimits,
) -> tuple[Dict[str, Any] | None, int, bool]:
    state = _new_target_search_state(token, candidates, target_amount, limits)
    _walk_split_search(
        state,
        _PartialSplit(start_index=0, remaining_amount=target_amount),
    )
    truncated = state.states_seen >= limits.max_search_states
    if state.best_plan is not None:
        state.best_plan["search_states"] = state.states_seen
        state.best_plan["split_combinations_evaluated_for_target"] = state.combinations_evaluated
        state.best_plan["search_truncated"] = truncated
        state.best_plan["selection_basis"] = "gas_adjusted_split_economic_diagnostic"
    return state.best_plan, state.combinations_evaluated, truncated


def _search_token_targets(
    token: str,
    candidates: Sequence[Mapping[str, Any]],
    limits: _SplitSearchLimits,
) -> tuple[List[Dict[str, Any]], int, int]:
    plans: List[Dict[str, Any]] = []
    evaluated = 0
    truncated_count = 0
    target_amounts = sorted({int(row["amount_in"]) for row in candidates})
    for target_amount in target_amounts:
        plan, target_evaluated, truncated = _search_target_amount(
            token, candidates, target_amount, limits
        )
        evaluated += target_evaluated
        truncated_count += int(truncated)
        if plan is not None:
            plans.append(plan)
    return plans, evaluated, truncated_count


def _collect_split_plans(
    candidates_by_token: Mapping[str, Sequence[Mapping[str, Any]]],
    limits: _SplitSearchLimits,
) -> tuple[List[Dict[str, Any]], int, int]:
    plans: List[Dict[str, Any]] = []
    evaluated = 0
    truncated = 0
    for token, candidates in sorted(candidates_by_token.items()):
        token_plans, token_evaluated, token_truncated = _search_token_targets(
            token, candidates, limits
        )
        plans.extend(token_plans)
        evaluated += token_evaluated
        truncated += token_truncated
    return plans, evaluated, truncated


def _round_robin_split_plans(
    plans: Sequence[Mapping[str, Any]], max_plans: int
) -> tuple[List[Dict[str, Any]], int, int]:
    by_token: Dict[str, List[Dict[str, Any]]] = {}
    for plan in plans:
        by_token.setdefault(str(plan.get("borrow_token") or ""), []).append(dict(plan))
    for token_plans in by_token.values():
        token_plans.sort(
            key=lambda row: (
                int(row["economic_after_cost_profit_wei"]),
                int(row.get("improvement_over_best_single_wei") or 0),
                int(row.get("gross_profit_wei") or 0),
            ),
            reverse=True,
        )

    interleaved: List[Dict[str, Any]] = []
    max_rank = max((len(rows) for rows in by_token.values()), default=0)
    for rank in range(max_rank):
        for token in sorted(by_token):
            token_plans = by_token[token]
            if rank < len(token_plans):
                interleaved.append(token_plans[rank])
    positive_count = sum(
        int(row.get("economic_after_cost_profit_wei") or 0) > 0
        for row in interleaved
    )
    return interleaved[:max(1, min(int(max_plans), 32))], len(interleaved), positive_count


def build_gas_adjusted_split_frontier(
    size_matrix: Sequence[Mapping[str, Any]],
    *,
    chain_id: int,
) -> Dict[str, Any]:
    """Estimate bounded split economics; never grants execution authority."""
    limits = _SplitSearchLimits()
    candidates_by_token = _prepare_candidate_buckets(
        size_matrix,
        chain_id=int(chain_id),
        max_per_amount=limits.max_candidates_per_amount,
    )
    eligible_routes = sum(len(rows) for rows in candidates_by_token.values())
    plans, evaluated, truncated = _collect_split_plans(candidates_by_token, limits)
    returned_plans, candidate_plan_count, positive_estimate_count = _round_robin_split_plans(
        plans, limits.max_plans
    )
    reason_code = (
        "executor_abi_v2_supports_one_sequential_route_only"
        if eligible_routes
        else "no_routes_with_complete_positive_gross_and_gas_cost_evidence"
    )
    return {
        "enabled": True,
        "mode": "bounded_gas_adjusted_split_diagnostic",
        "chain_id": int(chain_id),
        "ranking_scope": "within_borrow_token_only_then_round_robin_across_tokens",
        "eligible_route_amount_evidence": int(eligible_routes),
        "candidate_plans_before_output_limit": int(candidate_plan_count),
        "returned_plan_count": int(len(returned_plans)),
        "split_combinations_evaluated": int(evaluated),
        "search_states_limit_per_target": int(limits.max_search_states),
        "search_truncated_targets": int(truncated),
        "max_routes_per_split": int(limits.max_routes),
        "max_candidates_per_amount": int(limits.max_candidates_per_amount),
        "positive_after_cost_estimates": int(positive_estimate_count),
        "plans": returned_plans,
        "execution_supported": False,
        "required_executor_abi_version": 3,
        "execution_authority_granted": False,
        "reason_code": reason_code,
        "cost_model": {
            "gross_profit_units": "borrow_token_wei",
            "flashloan_fee_units": "borrow_token_wei",
            "gas_cost_conversion": "profit_token_wei",
            "gas_cost_policy": "one shared L2 overhead plus per-route leg estimates; max observed gas price and conversion ratio; component L1 fees are a planning proxy",
            "split_extra_route_gas_units_estimate": int(_EXTRA_SPLIT_ROUTE_GAS_UNITS),
            "split_extra_route_gas_units_is_upper_bound": False,
            "base_l1_fee_policy": "sum exact-calldata fees observed for individual ABI-v2 routes; proxy for future split ABI calldata, not exact ABI-v3 pricing",
            "future_split_calldata_cost_is_authoritative": False,
            "flashloan_fee_policy": "sum exact sampled portion fees plus one-wei-per-extra-route rounding reserve",
            "pool_policy": "reject plans that reuse a normalized pool key",
            "candidate_diversity_policy": "highest-net route first; alternatives may trade at most 50 bps of net value for new protocol/pool identity",
            "candidate_diversity_tolerance_bps": _DIVERSITY_TOLERANCE_BPS,
            "all_results_diagnostic_only": True,
        },
    }
