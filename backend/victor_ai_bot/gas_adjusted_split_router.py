from __future__ import annotations

"""Bounded gas-adjusted split economics for independent arbitrage cycles.

This module is deliberately diagnostic-only. A split plan consists of multiple
independent cycles, while executor ABI v2 accepts only one sequential leg chain.
No plan produced here grants execution authority.
"""

from fractions import Fraction
from typing import Any, Dict, List, Mapping, Sequence, Tuple

# Must remain aligned with gas_model.estimate_route_gas_units().
_SHARED_EXECUTION_OVERHEAD_GAS_UNITS = 180_000 + 90_000
# Conservative allowance for per-route ABI decoding/looping and added calldata
# inside a future atomic split executor. Exact cost must be simulated on that ABI.
_EXTRA_SPLIT_ROUTE_GAS_UNITS = 75_000
_DEFAULT_MAX_ROUTES = 3
_DEFAULT_MAX_CANDIDATES_PER_AMOUNT = 8
_DEFAULT_MAX_SEARCH_STATES = 2_000


def _int(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _leg_pool_key(leg: Mapping[str, Any]) -> str | None:
    """Conservative normalized pool identity; unknown identities fail closed."""
    dex = str(leg.get("dex") or "").strip().lower()
    token_in = str(leg.get("token_in") or "").strip().lower()
    token_out = str(leg.get("token_out") or "").strip().lower()
    venue = str(leg.get("venue") or "").strip().lower()
    aux = str(leg.get("data") or leg.get("aux") or "0x").strip().lower()
    if not dex or not token_in or not token_out or token_in == token_out:
        return None
    pair = "|".join(sorted((token_in, token_out)))
    if dex == "curve":
        return f"curve|{venue}|{aux}" if venue else None
    if dex == "balancer":
        return f"balancer|{aux}" if aux not in {"", "0x"} else None
    if dex in {"univ3", "slipstream", "aerodrome", "camelot_algebra", "camelot_v2", "constant_product"}:
        # Include router identity plus pair. Native fee/factory/tick/pool data
        # disambiguates protocol-specific pools that share the same router.
        if not venue:
            return None
        if dex in {"camelot_algebra", "camelot_v2", "constant_product"}:
            return f"{dex}|{venue}|{pair}"
        if aux in {"", "0x"}:
            return None
        return f"{dex}|{venue}|{pair}|{aux}"
    return f"{dex}|{venue}|{pair}|{aux}" if venue else None


def _normalize_candidate(candidate: Mapping[str, Any], *, chain_id: int) -> Dict[str, Any] | None:
    route_id = str(candidate.get("route_id") or "")
    amount = _int(candidate.get("amount_in"))
    gross = _int(candidate.get("gross_profit_wei"))
    fee = _int(candidate.get("flashloan_fee_wei"))
    gas_token = _int(candidate.get("gas_cost_profit_token_wei"))
    native_cost = _int(candidate.get("gas_cost_wei"))
    l2_gas = _int(candidate.get("gas_cost_l2_wei"))
    gas_units = _int(candidate.get("gas_units_estimate"))
    l1_fee = _int(candidate.get("base_l1_fee_wei"))
    legs = [dict(row) for row in candidate.get("legs", []) if isinstance(row, Mapping)]
    if (
        not route_id or amount is None or amount <= 0 or gross is None or gross <= 0
        or fee is None or fee < 0 or gas_token is None or gas_token <= 0
        or native_cost is None or native_cost <= 0 or l2_gas is None or l2_gas <= 0
        or gas_units is None or gas_units <= _SHARED_EXECUTION_OVERHEAD_GAS_UNITS
        or l1_fee is None or l1_fee < 0 or len(legs) < 2 or len(legs) > 3
    ):
        return None
    if chain_id == 8453 and str(candidate.get("base_l1_fee_status") or "") not in {
        "exact_calldata", "exact_calldata_cached"
    }:
        return None

    leg_start_amount = _int(legs[0].get("amount_in"))
    if leg_start_amount is None or leg_start_amount != amount:
        return None
    borrow_token = str(legs[0].get("token_in") or "").strip().lower()
    prior_out = borrow_token
    pool_keys = []
    protocols = set()
    routers = set()
    directed_pairs = set()
    for leg in legs:
        token_in = str(leg.get("token_in") or "").strip().lower()
        token_out = str(leg.get("token_out") or "").strip().lower()
        if not token_in or not token_out or token_in != prior_out or token_in == token_out:
            return None
        prior_out = token_out
        protocol = str(leg.get("dex") or "").strip().lower()
        if not protocol:
            return None
        protocols.add(protocol)
        venue = str(leg.get("venue") or "").strip().lower()
        # Curve venue is the pool itself, not a router. Preserve pool identity
        # separately and do not mislabel it as a router.
        if venue and protocol != "curve":
            routers.add(venue)
        directed_pairs.add(f"{token_in}->{token_out}")
        key = _leg_pool_key(leg)
        if key is None:
            return None
        pool_keys.append(key)
    if prior_out != borrow_token or len(pool_keys) != len(set(pool_keys)):
        return None

    l2_price = max(1, (l2_gas + gas_units - 1) // gas_units)
    conversion = Fraction(gas_token, native_cost)
    return {
        "route_id": route_id,
        "amount_in": amount,
        "gross_profit_wei": gross,
        "flashloan_fee_wei": fee,
        "gas_cost_profit_token_wei": gas_token,
        "gas_cost_wei": native_cost,
        "gas_cost_l2_wei": l2_gas,
        "gas_units_estimate": gas_units,
        "gas_price_effective_wei": l2_price,
        "base_l1_fee_wei": l1_fee,
        "base_l1_fee_status": str(candidate.get("base_l1_fee_status") or ""),
        "borrow_token": borrow_token,
        "legs": legs,
        "pool_keys": set(pool_keys),
        "protocols": protocols,
        "routers": routers,
        "directed_pairs": directed_pairs,
        "single_route_net_wei": gross - fee - gas_token,
        "gas_token_per_native_wei": conversion,
        "revalidated": candidate.get("revalidated") is True,
        "authoritative": candidate.get("authoritative") is True,
        "valid": candidate.get("valid") is True,
        "repayment_valid": candidate.get("repayment_valid") is True,
    }


def _candidate_evidence_rank(row: Mapping[str, Any]) -> tuple[int, int, int, int, int]:
    """Prefer valid authoritative economics, then signed net estimate."""
    return (
        int(bool(row.get("revalidated") and row.get("authoritative") and row.get("valid") and row.get("repayment_valid"))),
        int(bool(row.get("authoritative"))),
        int(bool(row.get("revalidated"))),
        int(row.get("single_route_net_wei") or 0),
        int(row.get("gross_profit_wei") or 0),
    )


def _prepare_candidate_buckets(
    size_matrix: Sequence[Mapping[str, Any]], *, chain_id: int, max_per_amount: int
) -> Dict[str, List[Dict[str, Any]]]:
    by_key: Dict[Tuple[str, int, str], Dict[str, Any]] = {}
    for size_row in size_matrix:
        if not isinstance(size_row, Mapping):
            continue
        if (_int(size_row.get("quote_requests")) or 0) <= 0 or (_int(size_row.get("quote_successes")) or 0) <= 0:
            continue
        for raw in size_row.get("candidates", []) or []:
            if not isinstance(raw, Mapping):
                continue
            candidate = _normalize_candidate(raw, chain_id=chain_id)
            if candidate is None:
                continue
            key = (candidate["borrow_token"], candidate["amount_in"], candidate["route_id"])
            prior = by_key.get(key)
            if prior is None or _candidate_evidence_rank(candidate) > _candidate_evidence_rank(prior):
                by_key[key] = candidate

    by_token: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in by_key.values():
        by_token.setdefault(candidate["borrow_token"], []).append(candidate)

    bounded: Dict[str, List[Dict[str, Any]]] = {}
    for token, candidates in by_token.items():
        by_amount: Dict[int, List[Dict[str, Any]]] = {}
        for candidate in candidates:
            by_amount.setdefault(candidate["amount_in"], []).append(candidate)
        kept = []
        for _amount, bucket in by_amount.items():
            # Keep the top-net route, then preserve economically near-best
            # alternatives that add pool/protocol coverage. A route can only
            # trade some net value for diversity inside a bounded 50-bps band.
            chosen: List[Dict[str, Any]] = []
            pending = sorted(
                bucket,
                key=lambda row: (
                    row["single_route_net_wei"],
                    row["gross_profit_wei"],
                    row["route_id"],
                ),
                reverse=True,
            )
            if pending:
                chosen.append(pending.pop(0))
            best_net = int(chosen[0]["single_route_net_wei"]) if chosen else 0
            tolerance = max(1, abs(best_net) * 50 // 10_000)
            while pending and len(chosen) < max(1, max_per_amount):
                near_best = [
                    idx for idx, row in enumerate(pending)
                    if best_net - int(row["single_route_net_wei"]) <= tolerance
                ]
                if not near_best:
                    # No economically comparable alternative remains. Continue
                    # with highest net evidence, never diversity-only promotion.
                    chosen.append(pending.pop(0))
                    continue
                selected_protocols = set().union(*(row["protocols"] for row in chosen))
                selected_pools = set().union(*(row["pool_keys"] for row in chosen))
                pick_idx = max(
                    near_best,
                    key=lambda idx: (
                        len(pending[idx]["protocols"] - selected_protocols),
                        len(pending[idx]["pool_keys"] - selected_pools),
                        pending[idx]["single_route_net_wei"],
                        pending[idx]["gross_profit_wei"],
                    ),
                )
                chosen.append(pending.pop(pick_idx))
            kept.extend(chosen)
        bounded[token] = sorted(
            kept,
            key=lambda row: (row["amount_in"], row["single_route_net_wei"], row["route_id"]),
        )
    return bounded


def _evaluate_split(parts: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    amount = sum(int(row["amount_in"]) for row in parts)
    gross = sum(int(row["gross_profit_wei"]) for row in parts)
    # Portion fees are observed at their exact sampled sizes. Add one wei per
    # additional part as a rounding reserve for fee rounding on the aggregated
    # flash loan, so splitting cannot understate the flash premium.
    fee = sum(int(row["flashloan_fee_wei"]) for row in parts) + max(0, len(parts) - 1)

    combined_l2_units = _SHARED_EXECUTION_OVERHEAD_GAS_UNITS + sum(
        max(0, int(row["gas_units_estimate"]) - _SHARED_EXECUTION_OVERHEAD_GAS_UNITS)
        for row in parts
    ) + max(0, len(parts) - 1) * _EXTRA_SPLIT_ROUTE_GAS_UNITS
    gas_price = max(int(row["gas_price_effective_wei"]) for row in parts)
    l2_cost = combined_l2_units * gas_price
    # Sum per-route L1 data costs rather than discounting them. Until ABI-v3
    # calldata exists, summation is a conservative upper bound.
    l1_cost = sum(int(row["base_l1_fee_wei"]) for row in parts)
    native_cost = l2_cost + l1_cost
    # Use the highest observed token/native conversion ratio to avoid understating
    # gas costs when candidate rows are not perfectly aligned.
    conversion = max(row["gas_token_per_native_wei"] for row in parts)
    gas_token_cost = (native_cost * conversion.numerator + conversion.denominator - 1) // conversion.denominator
    net = gross - fee - gas_token_cost
    return {
        "amount_in": str(amount),
        "gross_profit_wei": str(gross),
        "flashloan_fee_wei": str(fee),
        "gas_cost_wei_estimate": str(native_cost),
        "gas_cost_profit_token_wei_estimate": str(gas_token_cost),
        "estimated_l2_gas_units": str(combined_l2_units),
        "estimated_l2_gas_cost_wei": str(l2_cost),
        "estimated_l1_data_fee_wei": str(l1_cost),
        "economic_after_cost_profit_wei": str(net),
        "after_cost_positive_estimate": net > 0,
        "revalidated": False,
        "authoritative": False,
        "valid": False,
        "execution_authority_granted": False,
        "execution_supported": False,
        "required_executor_abi_version": 3,
        "execution_block_reason": "executor_abi_v2_supports_one_sequential_route_only",
        "simulation_required_before_authority": True,
        "route_count": len(parts),
        "route_ids": [str(row["route_id"]) for row in parts],
        "identity_coverage": {
            "unique_protocols": len(set().union(*(row["protocols"] for row in parts))),
            "unique_pool_keys": len(set().union(*(row["pool_keys"] for row in parts))),
            "unique_router_ids": len(set().union(*(row["routers"] for row in parts))),
            "unique_directed_pairs": len(set().union(*(row["directed_pairs"] for row in parts))),
            "router_identity_is_not_a_profit_score": True,
        },
        "allocations": [
            {
                "route_id": str(row["route_id"]),
                "amount_in": str(row["amount_in"]),
                "gross_profit_wei": str(row["gross_profit_wei"]),
                "flashloan_fee_wei": str(row["flashloan_fee_wei"]),
                "gas_cost_profit_token_wei_observed": str(row["gas_cost_profit_token_wei"]),
                "protocols": sorted(row["protocols"]),
                "pool_keys": sorted(row["pool_keys"]),
                "router_ids": sorted(row["routers"]),
                "directed_pairs": sorted(row["directed_pairs"]),
                "legs": [
                    {
                        "dex": str(leg.get("dex") or ""),
                        "venue": str(leg.get("venue") or ""),
                        "token_in": str(leg.get("token_in") or ""),
                        "token_out": str(leg.get("token_out") or ""),
                        "amount_in": str(leg.get("amount_in") or ""),
                        "min_out": str(leg.get("min_out") or ""),
                        "data": str(leg.get("data") or ""),
                    }
                    for leg in row["legs"]
                ],
                "component_revalidated": bool(row["revalidated"]),
                "component_authoritative": bool(row["authoritative"]),
                "component_valid": bool(row["valid"]),
                "component_repayment_valid": bool(row["repayment_valid"]),
            }
            for row in parts
        ],
    }


def build_gas_adjusted_split_frontier(
    size_matrix: Sequence[Mapping[str, Any]],
    *,
    chain_id: int,
    max_routes: int = _DEFAULT_MAX_ROUTES,
    max_candidates_per_amount: int = _DEFAULT_MAX_CANDIDATES_PER_AMOUNT,
    max_search_states: int = _DEFAULT_MAX_SEARCH_STATES,
    max_plans: int = 8,
) -> Dict[str, Any]:
    """Estimate best gas-adjusted partitions using only explicit quote/cost evidence.

    Outputs are research candidates only. They are never promoted to an executable
    Opportunity: the deployed ABI-v2 executor cannot execute independent routes.
    """
    maximum_routes = max(2, min(int(max_routes), 3))
    search_limit = max(100, min(int(max_search_states), 10_000))
    candidates_by_token = _prepare_candidate_buckets(
        size_matrix,
        chain_id=int(chain_id),
        max_per_amount=max(1, min(int(max_candidates_per_amount), 12)),
    )
    plans: List[Dict[str, Any]] = []
    evaluated = 0
    truncated_searches = 0
    eligible_routes = sum(len(rows) for rows in candidates_by_token.values())

    for token, candidates in sorted(candidates_by_token.items()):
        target_amounts = sorted({int(row["amount_in"]) for row in candidates})
        for target_amount in target_amounts:
            singles = [row for row in candidates if int(row["amount_in"]) == target_amount]
            best_single_net = max(
                (int(row["single_route_net_wei"]) for row in singles),
                default=None,
            )
            amount_pool = [row for row in candidates if int(row["amount_in"]) <= target_amount]
            amount_pool.sort(
                key=lambda row: (
                    -int(row["single_route_net_wei"]),
                    -int(row["gross_profit_wei"]),
                    int(row["amount_in"]),
                    str(row["route_id"]),
                )
            )
            states_seen = 0
            combinations_evaluated = 0
            best_for_target: Dict[str, Any] | None = None

            def walk(
                start: int,
                remaining: int,
                parts: List[Dict[str, Any]],
                used_routes: set[str],
                used_pools: set[str],
            ) -> None:
                nonlocal evaluated, states_seen, combinations_evaluated, truncated_searches, best_for_target
                if states_seen >= search_limit:
                    return
                states_seen += 1
                if remaining == 0:
                    if len(parts) < 2:
                        return
                    evaluated += 1
                    combinations_evaluated += 1
                    model = _evaluate_split(parts)
                    model["borrow_token"] = token
                    model["best_single_route_net_wei_at_target"] = (
                        str(best_single_net) if best_single_net is not None else None
                    )
                    improvement = (
                        int(model["economic_after_cost_profit_wei"]) - best_single_net
                        if best_single_net is not None else None
                    )
                    model["improvement_over_best_single_wei"] = (
                        str(improvement) if improvement is not None else None
                    )
                    model["better_than_best_single_estimate"] = (
                        improvement is not None and improvement > 0
                    )
                    model["composite_route_key"] = "|".join(model["route_ids"])
                    if (
                        best_for_target is None
                        or int(model["economic_after_cost_profit_wei"])
                        > int(best_for_target["economic_after_cost_profit_wei"])
                    ):
                        best_for_target = model
                    return
                if len(parts) >= maximum_routes:
                    return
                for idx in range(start, len(amount_pool)):
                    row = amount_pool[idx]
                    row_amount = int(row["amount_in"])
                    if row_amount > remaining:
                        continue
                    route_id = str(row["route_id"])
                    if route_id in used_routes:
                        continue
                    if used_pools.intersection(row["pool_keys"]):
                        continue
                    walk(
                        idx + 1,
                        remaining - row_amount,
                        [*parts, row],
                        used_routes | {route_id},
                        used_pools | set(row["pool_keys"]),
                    )
                    if states_seen >= search_limit:
                        return

            walk(0, target_amount, [], set(), set())
            if states_seen >= search_limit:
                truncated_searches += 1
            if best_for_target is not None:
                best_for_target["search_states"] = states_seen
                best_for_target["split_combinations_evaluated_for_target"] = combinations_evaluated
                best_for_target["search_truncated"] = states_seen >= search_limit
                best_for_target["selection_basis"] = "gas_adjusted_split_economic_diagnostic"
                plans.append(best_for_target)

    plans.sort(
        key=lambda row: (
            int(row["economic_after_cost_profit_wei"]),
            int(row.get("improvement_over_best_single_wei") or 0),
            int(row.get("gross_profit_wei") or 0),
        ),
        reverse=True,
    )
    plans = plans[:max(1, min(int(max_plans), 32))]
    return {
        "enabled": True,
        "mode": "bounded_gas_adjusted_split_diagnostic",
        "chain_id": int(chain_id),
        "eligible_route_amount_evidence": int(eligible_routes),
        "split_combinations_evaluated": int(evaluated),
        "search_states_limit_per_target": int(search_limit),
        "search_truncated_targets": int(truncated_searches),
        "max_routes_per_split": int(maximum_routes),
        "max_candidates_per_amount": int(max(1, min(int(max_candidates_per_amount), 12))),
        "positive_after_cost_estimates": sum(
            int(row.get("economic_after_cost_profit_wei") or 0) > 0 for row in plans
        ),
        "plans": plans,
        "execution_supported": False,
        "required_executor_abi_version": 3,
        "execution_authority_granted": False,
        "reason_code": (
            "executor_abi_v2_supports_one_sequential_route_only"
            if eligible_routes else "no_routes_with_complete_positive_gross_and_gas_cost_evidence"
        ),
        "cost_model": {
            "gross_profit_units": "borrow_token_wei",
            "flashloan_fee_units": "borrow_token_wei",
            "gas_cost_conversion": "profit_token_wei",
            "gas_cost_policy": "one shared l2 overhead plus per-route leg estimates; max observed gas price and conversion ratio; sum component L1 fees as a planning proxy",
            "split_extra_route_gas_units_estimate": int(_EXTRA_SPLIT_ROUTE_GAS_UNITS),
            "split_extra_route_gas_units_is_upper_bound": False,
            "base_l1_fee_policy": "sum exact-calldata fees observed for individual ABI-v2 routes; heuristic proxy for a future split ABI, not exact ABI-v3 pricing",
            "future_split_calldata_cost_is_authoritative": False,
            "flashloan_fee_policy": "sum exact sampled portion fees plus one-wei-per-extra-route rounding reserve",
            "pool_policy": "reject plans that reuse a normalized pool key",
            "candidate_diversity_policy": "highest-net route first; alternatives may trade at most 50 bps of net value for new protocol/pool identity, then net ranks again",
            "candidate_diversity_tolerance_bps": 50,
            "all_results_diagnostic_only": True,
        },
    }
