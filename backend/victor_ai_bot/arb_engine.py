from __future__ import annotations

import asyncio
import time, hashlib, os
from dataclasses import dataclass
from bisect import bisect_left
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from .cache import PerBlockCache
from .models import Opportunity, Route, RouteLeg
from .quote_univ3 import quote_exact_input_single, quote_exact_input_single_batch
from .quote_curve import quote_curve, quote_curve_many
from .quote_balancer import (
    build_balancer_query_batchswap_calldata,
    quote_balancer_given_in,
    quote_balancer_given_in_many,
)
from .quote_aerodrome import quote_aerodrome, quote_aerodrome_many
from .quote_slipstream import quote_slipstream, quote_slipstream_many
from .quote_camelot_algebra import quote_camelot_algebra, quote_camelot_algebra_many
from .quote_camelot_v2 import quote_camelot_v2, quote_camelot_v2_many
from .quote_constant_product import quote_constant_product, quote_constant_product_many
from .gas_model import estimate_route_gas_units, estimate_gas_cost_wei_from_cfg
from .route_encoding import EncLeg, route_id_hex
from .opportunity_density import scan_efficiency_snapshot


_SAFE_EDGE_QUOTE_EXCEPTIONS = (
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    OverflowError,
    RuntimeError,
    TimeoutError,
    TypeError,
    ValueError,
)
_SAFE_POOL_KEY_EXCEPTIONS = (AttributeError, OverflowError, TypeError, ValueError)
_SAFE_AUX_DECODE_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS = (
    AttributeError,
    OverflowError,
    TypeError,
    ValueError,
    ZeroDivisionError,
)


def _aux_u256_to_b32_hex(n: int) -> str:
    return "0x" + (n & ((1 << 256) - 1)).to_bytes(32, "big").hex()


def aux_univ3_fee(fee: int) -> str:
    # low 24 bits
    return _aux_u256_to_b32_hex(int(fee) & 0xFFFFFF)


def aux_curve(i: int, j: int, underlying: bool) -> str:
    # low bits: i (8) | j (8) | underlying (1 at bit16)
    v = (int(i) & 0xFF) | ((int(j) & 0xFF) << 8) | ((1 if underlying else 0) << 16)
    return _aux_u256_to_b32_hex(v)


def aux_curve_from_meta(meta: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Build Curve aux data from quote metadata when available.

    Important: quoting may use `get_dy_underlying` even if the configured edge
    is marked as non-underlying (or vice versa). The quote function records
    `used_underlying` and the i/j indices.
    """
    i = meta.get("i", params.get("i", 0))
    j = meta.get("j", params.get("j", 0))
    underlying = meta.get("used_underlying", params.get("underlying", False))
    return aux_curve(int(i), int(j), bool(underlying))




def _record_size_economic_diagnostic(
    metrics: Dict[str, Any],
    *,
    route_id: str,
    amount_in: int,
    gross_profit_wei: int,
    flashloan_fee_wei: int,
    gas_cost_wei: int,
    reason: str,
    legs: Optional[List[Dict[str, Any]]] = None,
    max_samples: int = 16,
    gas_cost_profit_token_wei: int | None = None,
) -> None:
    """Retain bounded economic near-misses without promoting them to opportunities.

    Route details are diagnostic evidence only and never grant execution authority.
    """
    diagnostic_legs = [dict(leg) for leg in (legs or []) if isinstance(leg, dict)][:3]
    terminal_amount_out = 0
    if diagnostic_legs:
        for leg in reversed(diagnostic_legs):
            for key in ("quoted_amount_out", "amount_out_wei", "amount_out"):
                try:
                    value = int(leg.get(key) or 0)
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    terminal_amount_out = value
                    break
            if terminal_amount_out > 0:
                break

    gas_conversion_available = bool(
        gas_cost_profit_token_wei is not None
        and int(gas_cost_profit_token_wei) > 0
    )
    gross_after_fee_upper_bound = int(gross_profit_wei) - int(flashloan_fee_wei)
    row = {
        "route_id": str(route_id),
        "amount_in": str(max(0, int(amount_in))),
        "amount_out_wei": str(max(0, terminal_amount_out)),
        "gross_profit_wei": str(int(gross_profit_wei)),
        "flashloan_fee_wei": str(max(0, int(flashloan_fee_wei))),
        "gas_cost_wei": str(max(0, int(gas_cost_wei))),
        "gas_cost_profit_token_wei": (
            str(max(0, int(gas_cost_profit_token_wei)))
            if gas_cost_profit_token_wei is not None
            else ""
        ),
        "gas_cost_conversion_available": gas_conversion_available,
        # For telemetry compatibility this retains the old upper-bound value
        # when conversion is missing. Consumers must use the explicit flag and
        # must not treat this field as a signed after-cost estimate in that case.
        "after_cost_profit_wei": str(
            int(gross_profit_wei)
            - int(flashloan_fee_wei)
            - (
                int(gas_cost_profit_token_wei)
                if gas_conversion_available
                else 0
            )
        ),
        "after_cost_profit_is_upper_bound": not gas_conversion_available,
        "gross_minus_flashloan_fee_upper_bound_wei": (
            str(gross_after_fee_upper_bound)
            if not gas_conversion_available
            else ""
        ),
        "revalidated": False,
        "authoritative": False,
        "reason": str(reason or "non_positive_gross_profit"),
        "diagnostic_only": True,
        "legs": diagnostic_legs,
    }
    samples = list(metrics.get("size_economic_diagnostics") or [])
    samples.append(row)
    # Preserve the complete bounded size curve for each route. A single global
    # top-N list can erase a route's zero/negative size points when another
    # route has a larger gross near-miss, making economic-optimum modeling
    # incomplete. Bound both per-route and total telemetry volume.
    per_route: Dict[str, List[Dict[str, Any]]] = {}
    for sample in samples:
        key = str(sample.get("route_id") or "")
        if not key:
            continue
        per_route.setdefault(key, []).append(sample)
    per_route_limit = max(1, int(max_samples))
    # Keep complete bounded curves for the strongest route families, while
    # retaining a hard total cap so telemetry cannot grow with route-universe
    # size. Ranking route families by their best gross sample preserves the
    # historical "closest gross routes" behavior when there are many routes.
    ranked_routes = sorted(
        per_route.values(),
        key=lambda route_samples: max(
            (int(item.get("gross_profit_wei") or 0) for item in route_samples),
            default=0,
        ),
        reverse=True,
    )
    max_routes = 16
    retained: List[Dict[str, Any]] = []
    for route_samples in ranked_routes[:max_routes]:
        route_samples.sort(
            key=lambda item: int(item.get("gross_profit_wei") or 0),
            reverse=True,
        )
        retained.extend(route_samples[:per_route_limit])
    retained.sort(key=lambda item: int(item.get("gross_profit_wei") or 0), reverse=True)
    total_limit = per_route_limit * max_routes
    metrics["size_economic_diagnostics"] = retained[:total_limit]

def _now_ms() -> int:
    return int(time.time() * 1000)


def _id(parts: List[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _apply_slippage(amount: int, slippage_bps: int) -> int:
    return max(0, amount * (10_000 - slippage_bps) // 10_000)


@dataclass(frozen=True)
class Edge:
    dex: str
    venue: str
    token_in: str
    token_out: str
    params: Dict[str, Any]


def _edge_protocol_identity(edge: Edge) -> str | None:
    """Return the canonical protocol family represented by an execution edge."""
    protocol = str(getattr(edge, "dex", "") or "").strip().lower()
    return protocol or None


def _edge_pool_identity(edge: Edge) -> str | None:
    """Resolve pool identity without confusing a shared router with a pool.

    Explicit pool addresses and Balancer pool IDs are authoritative. For
    configured families whose pool is deterministically identified by its
    factory/pair/fee-or-mode tuple, derive a normalized fallback key. Unknown
    identities return None and are not counted as verified pool diversity.
    """
    protocol = _edge_protocol_identity(edge)
    if not protocol:
        return None
    raw_params = getattr(edge, "params", {}) or {}
    params = raw_params if isinstance(raw_params, dict) else {}
    pool_id = str(params.get("pool_id") or "").strip().lower()
    if pool_id:
        return f"{protocol}:pool_id:{pool_id}"
    pool = str(params.get("pool") or "").strip().lower()
    if not pool and protocol == "curve":
        # Curve edges address the pool directly; venue is not a router here.
        pool = str(getattr(edge, "venue", "") or "").strip().lower()
    if pool:
        return f"{protocol}:pool:{pool}"

    token_in = str(getattr(edge, "token_in", "") or "").strip().lower()
    token_out = str(getattr(edge, "token_out", "") or "").strip().lower()
    if not token_in or not token_out:
        return None
    pair = "|".join(sorted((token_in, token_out)))
    required_fields = {
        "univ3": ("fee",),
        "aerodrome": ("factory", "stable"),
        "slipstream": ("factory", "tick_spacing"),
        "camelot_algebra": ("factory", "tick_spacing"),
        "camelot_v2": ("factory",),
        "constant_product": ("factory", "venue_name"),
    }.get(protocol)
    if required_fields is None:
        return None

    normalized = {
        key: str(params[key]).strip().lower()
        for key in ("factory", "fee", "tick_spacing", "stable", "venue_name")
        if key in params and params[key] not in (None, "")
    }
    if not all(normalized.get(key) for key in required_fields):
        return None
    dimensions = "|".join(f"{key}={normalized[key]}" for key in sorted(normalized))
    return f"{protocol}:pair:{pair}:{dimensions}"


def _edge_directed_pair_identity(edge: Edge) -> tuple[str, str] | None:
    token_in = str(getattr(edge, "token_in", "") or "").strip().lower()
    token_out = str(getattr(edge, "token_out", "") or "").strip().lower()
    if not token_in or not token_out or token_in == token_out:
        return None
    return token_in, token_out


def _edge_router_identity(edge: Edge) -> str | None:
    """Return router identity, excluding protocols whose venue is the pool."""
    protocol = _edge_protocol_identity(edge)
    if not protocol or protocol == "curve":
        return None
    router = str(getattr(edge, "venue", "") or "").strip().lower()
    return router or None


def _edge_diversity_novelty(
    edge: Edge,
    *,
    active_protocols: set[str],
    active_pools: set[str],
    active_routers: set[str],
) -> Tuple[int, int, int]:
    """Return independent protocol-, pool-, and router-novelty dimensions."""
    protocol = _edge_protocol_identity(edge)
    pool = _edge_pool_identity(edge)
    router = _edge_router_identity(edge)
    return (
        int(bool(protocol) and protocol not in active_protocols),
        int(pool is not None and pool not in active_pools),
        int(router is not None and router not in active_routers),
    )


def _frontier_quote_quality_directed_pair_group_count(
    candidates: Sequence[Tuple[int, Edge]],
    quoted_output_by_edge: Mapping[str, Any],
) -> int:
    """Count quote-covered directed pairs while respecting (discovery_order, Edge) records."""
    return len({
        (str(edge.token_in).lower(), str(edge.token_out).lower())
        for _order, edge in candidates
        if edge_key(edge) in quoted_output_by_edge
    })


def _quote_outputs_by_pair(
    candidates: Sequence[Tuple[int, Edge]],
    quoted: Mapping[str, int],
) -> Dict[Tuple[str, str], List[int]]:
    outputs: Dict[Tuple[str, str], List[int]] = {}
    for _order, edge in candidates:
        pair = _edge_directed_pair_identity(edge)
        output = quoted.get(edge_key(edge))
        if pair is not None and output is not None:
            outputs.setdefault(pair, []).append(int(output))
    return outputs


def _quote_quality_rank(output: int, unique_outputs: Sequence[int]) -> int:
    if len(unique_outputs) <= 1:
        return 5_000
    rank = bisect_left(unique_outputs, int(output))
    return int(rank * 10_000 / (len(unique_outputs) - 1))


def _pair_quote_percentiles(
    pair: Tuple[str, str],
    candidates: Sequence[Tuple[int, Edge]],
    outputs: Sequence[int],
    quoted: Mapping[str, int],
) -> Dict[Tuple[str, str, str], int]:
    unique_outputs = sorted(set(outputs))
    matching = [
        (edge, int(quoted[edge_key(edge)]))
        for _order, edge in candidates
        if _edge_directed_pair_identity(edge) == pair
        and edge_key(edge) in quoted
    ]
    return {
        (pair[0], pair[1], edge_key(edge)): _quote_quality_rank(output, unique_outputs)
        for edge, output in matching
    }


def _frontier_quote_quality_percentiles(
    candidates: Sequence[Tuple[int, Edge]],
    quoted: Mapping[str, int],
) -> Dict[Tuple[str, str, str], int]:
    outputs_by_pair = _quote_outputs_by_pair(candidates, quoted)
    percentiles: Dict[Tuple[str, str, str], int] = {}
    for pair, outputs in outputs_by_pair.items():
        percentiles.update(_pair_quote_percentiles(pair, candidates, outputs, quoted))
    return percentiles


@dataclass(frozen=True)
class _FrontierSelectionContext:
    active_protocols_by_token: Dict[str, set[str]]
    active_pools_by_token: Dict[str, set[str]]
    active_routers_by_token: Dict[str, set[str]]
    per_token_cap: int
    quote_quality_by_edge: Dict[Tuple[str, str, str], int]


def _frontier_identity_sets(
    edge: Edge,
    already_selected: Sequence[Edge],
    context: _FrontierSelectionContext,
) -> Tuple[set[str], set[str], set[str]]:
    token = str(edge.token_in)
    protocols = set(context.active_protocols_by_token.get(token, set()))
    pools = set(context.active_pools_by_token.get(token, set()))
    routers = set(context.active_routers_by_token.get(token, set()))
    for chosen in already_selected:
        protocol = _edge_protocol_identity(chosen)
        pool = _edge_pool_identity(chosen)
        router = _edge_router_identity(chosen)
        if protocol:
            protocols.add(protocol)
        if pool:
            pools.add(pool)
        if router:
            routers.add(router)
    return protocols, pools, routers


def _frontier_candidate_score(
    order: int,
    edge: Edge,
    selected_by_token: Dict[str, List[Edge]],
    context: _FrontierSelectionContext,
) -> Tuple[int, int, int, int, int] | None:
    token = str(edge.token_in)
    bucket = selected_by_token.get(token, [])
    if len(bucket) >= max(0, int(context.per_token_cap)):
        return None
    protocols, pools, routers = _frontier_identity_sets(edge, bucket, context)
    protocol_new, pool_new, router_new = _edge_diversity_novelty(
        edge,
        active_protocols=protocols,
        active_pools=pools,
        active_routers=routers,
    )
    pair = _edge_directed_pair_identity(edge)
    quote_quality = (
        context.quote_quality_by_edge.get((pair[0], pair[1], edge_key(edge)), 0)
        if pair is not None else 0
    )
    return quote_quality, protocol_new, pool_new, router_new, -int(order)


def _best_frontier_candidate_index(
    pending: Sequence[Tuple[int, Edge]],
    selected_by_token: Dict[str, List[Edge]],
    context: _FrontierSelectionContext,
) -> int | None:
    best_index = None
    best_score = None
    for candidate_index, (order, edge) in enumerate(pending):
        score = _frontier_candidate_score(order, edge, selected_by_token, context)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best_index = candidate_index
            best_score = score
    return best_index


def _select_three_leg_frontier_edges(
    candidates: List[Tuple[int, Edge]],
    *,
    active_protocols_by_token: Dict[str, set[str]],
    active_pools_by_token: Dict[str, set[str]],
    active_routers_by_token: Dict[str, set[str]],
    per_token_cap: int,
    global_cap: int,
    quoted_output_by_edge: Optional[Dict[str, int]] = None,
    quote_quality_by_edge: Optional[Dict[Tuple[str, str, str], int]] = None,
) -> Tuple[List[Edge], Dict[str, List[Edge]]]:
    """Select a bounded, quote-aware edge frontier with independent identity axes."""
    pending = list(candidates)
    selected: List[Edge] = []
    selected_by_token: Dict[str, List[Edge]] = {}
    quoted = {
        str(key): int(value)
        for key, value in dict(quoted_output_by_edge or {}).items()
        if int(value) > 0
    }
    quality = dict(
        quote_quality_by_edge
        if quote_quality_by_edge is not None
        else _frontier_quote_quality_percentiles(pending, quoted)
    )
    context = _FrontierSelectionContext(
        active_protocols_by_token=active_protocols_by_token,
        active_pools_by_token=active_pools_by_token,
        active_routers_by_token=active_routers_by_token,
        per_token_cap=max(0, int(per_token_cap)),
        quote_quality_by_edge=quality,
    )
    while pending and len(selected) < max(0, int(global_cap)):
        best_index = _best_frontier_candidate_index(pending, selected_by_token, context)
        if best_index is None:
            break
        _order, edge = pending.pop(best_index)
        selected_by_token.setdefault(str(edge.token_in), []).append(edge)
        selected.append(edge)
    return selected, {token: list(items) for token, items in selected_by_token.items()}


async def quote_edge(
    rpc, cfg, cache: PerBlockCache, edge: Edge, amount_in: int
) -> Optional[Tuple[int, Dict[str, Any]]]:
    # cached per block per edge/amount
    ck = f"edge:{edge.dex}:{edge.venue}:{edge.token_in}:{edge.token_out}:{json_key(edge.params)}:{amount_in}"
    hit = cache.get(ck)
    if hit is not None:
        return hit
    out: Optional[Tuple[int, Dict[str, Any]]] = None
    try:
        if edge.dex == "univ3":
            fee = int(edge.params.get("fee", 3000))
            q = await quote_exact_input_single(
                rpc, cfg.chain.univ3_quoter_v2, edge.token_in, edge.token_out, fee, amount_in
            )
            if q:
                out = (q.amount_out, {"gas_estimate": q.gas_estimate, "fee": fee})
        elif edge.dex == "curve":
            pool = edge.venue
            i = int(edge.params["i"])
            j = int(edge.params["j"])
            underlying = bool(edge.params.get("underlying", False))
            q = await quote_curve(rpc, pool, i, j, amount_in, prefer_underlying=underlying)
            if q:
                out = (q.amount_out, {"used_underlying": q.used_underlying, "i": i, "j": j})
        elif edge.dex == "constant_product":
            q = await quote_constant_product(rpc, edge.venue, edge.token_in, edge.token_out, amount_in)
            if q:
                out = (q.amount_out, {"fee_model": "router_observed", "pool": str(edge.params.get("pool") or "")})
        elif edge.dex == "balancer":
            pool_id = edge.params["pool_id"]
            q = await quote_balancer_given_in(
                rpc, cfg.chain.balancer_vault, pool_id, edge.token_in, edge.token_out, amount_in
            )
            if q:
                out = (q.amount_out, {"pool_id": pool_id})
        elif edge.dex == "aerodrome":
            q = await quote_aerodrome(
                rpc, cfg.chain.aerodrome_router,
                edge.token_in, edge.token_out, int(amount_in),
                stable=bool(edge.params.get("stable", False)),
                factory=str(edge.params.get("factory") or ""),
            )
            if q:
                out = (q.amount_out, {"stable": bool(q.stable), "factory": str(q.factory)})
        elif edge.dex == "slipstream":
            q = await quote_slipstream(
                rpc, cfg.chain.slipstream_quoter_v2,
                edge.token_in, edge.token_out,
                int(edge.params.get("tick_spacing", 0)), int(amount_in),
            )
            if q:
                out = (
                    q.amount_out,
                    {
                        "gas_estimate": int(q.gas_estimate),
                        "tick_spacing": int(q.tick_spacing),
                        "factory": str(edge.params.get("factory") or ""),
                    },
                )
        elif edge.dex == "camelot_algebra":
            q = await quote_camelot_algebra(
                rpc, cfg.chain.camelot_algebra_quoter_v2,
                edge.token_in, edge.token_out, int(amount_in),
            )
            if q:
                out = (
                    q.amount_out,
                    {
                        "gas_estimate": int(q.gas_estimate),
                        "fee": int(q.fee),
                        "factory": str(edge.params.get("factory") or ""),
                    },
                )
        elif edge.dex == "camelot_v2":
            q = await quote_camelot_v2(
                rpc, cfg.chain.camelot_v2_router,
                edge.token_in, edge.token_out, int(amount_in),
            )
            if q:
                out = (
                    q.amount_out,
                    {"fee_model": "router_observed", "pool": str(edge.params.get("pool") or "")},
                )
        elif edge.dex == "constant_product":
            q = await quote_constant_product(
                rpc, edge.venue, edge.token_in, edge.token_out, int(amount_in),
            )
            if q:
                out = (
                    q.amount_out,
                    {
                        "fee_model": "router_observed",
                        "pool": str(edge.params.get("pool") or ""),
                        "venue_name": str(edge.params.get("venue_name") or ""),
                    },
                )
    except _SAFE_EDGE_QUOTE_EXCEPTIONS:
        out = None
    cache.set(ck, out)
    return out


def json_key(d: Dict[str, Any]) -> str:
    # stable key without importing json module (avoid overhead)
    items = sorted((str(k), str(v)) for k, v in d.items())
    return ",".join([f"{k}={v}" for k, v in items])


def edge_key(e: Edge) -> str:
    return f"{e.dex}:{e.venue}:{e.token_in}:{e.token_out}:{json_key(e.params)}"


def _route_universe_snapshot(
    cfg: Any,
    edges: List[Edge],
    *,
    adjacency: Optional[Dict[str, List[Edge]]] = None,
    max_edges_per_token: Optional[int] = None,
    pruned_edges: Optional[List[Edge]] = None,
    edge_build_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Describe the candidate graph before quote/economic filtering."""
    by_dex: Dict[str, int] = {}
    by_family: Dict[str, int] = {}
    undirected_v3: set[tuple[str, str, int]] = set()
    directed_pairs: set[tuple[str, str]] = set()
    tokens: set[str] = set()
    for edge in edges:
        dex = str(edge.dex)
        by_dex[dex] = int(by_dex.get(dex, 0)) + 1
        family = (
            str(edge.params.get("venue_name") or "").strip().lower()
            if dex == "constant_product"
            else dex
        ) or dex
        by_family[family] = int(by_family.get(family, 0)) + 1
        a = str(edge.token_in).lower()
        b = str(edge.token_out).lower()
        tokens.update((a, b))
        directed_pairs.add((a, b))
        if dex == "univ3":
            lo, hi = sorted((a, b))
            undirected_v3.add((lo, hi, int(edge.params.get("fee", 3000))))
    reverse_pairs = sum(1 for a, b in directed_pairs if (b, a) in directed_pairs)
    token_universe = {str(token).lower() for token in (getattr(getattr(cfg, "chain", None), "token_universe", []) or []) if token}
    possible_v3 = (len(token_universe) * (len(token_universe) - 1) // 2) * 4
    actual_v3 = len(undirected_v3)
    snapshot: Dict[str, Any] = {
        "configured_token_count": len(token_universe),
        "active_token_count": len(tokens),
        "active_tokens": sorted(tokens),
        "edges_by_dex": dict(sorted(by_dex.items())),
        "edges_by_family": dict(sorted(by_family.items())),
        "edge_build_diagnostics": dict(edge_build_diagnostics or {}),
        "unique_directed_pairs": len(directed_pairs),
        "directed_pairs_with_reverse": int(reverse_pairs),
        "reverse_pair_coverage_ratio": float(reverse_pairs) / float(len(directed_pairs)) if directed_pairs else 0.0,
        "univ3_unique_pool_count": actual_v3,
        "univ3_possible_configured_pair_fee_count": int(possible_v3),
        "univ3_configured_pair_fee_coverage_ratio": float(actual_v3) / float(possible_v3) if possible_v3 else 0.0,
    }
    if adjacency is not None:
        active = sum(len(items) for items in adjacency.values())
        snapshot["three_leg_adjacency_edges"] = int(active)
        snapshot["three_leg_max_edges_per_token"] = int(max_edges_per_token or 0)
        pruned = list(pruned_edges or [])
        snapshot["three_leg_edges_pruned_by_token_cap"] = int(max(0, len(pruned)))
        snapshot["three_leg_pruned_edges"] = [
            {
                "edge_id": edge_key(edge),
                "dex": str(edge.dex),
                "venue": str(edge.venue),
                "token_in": str(edge.token_in),
                "token_out": str(edge.token_out),
                "pool": (
                    str(edge.params.get("pool"))
                    if edge.params.get("pool")
                    else (
                        str(edge.params.get("pool_id"))
                        if edge.params.get("pool_id")
                        else None
                    )
                ),
                "params": {
                    str(k): v for k, v in dict(edge.params or {}).items()
                    if str(k) in {"fee", "pool", "pool_id", "factory", "i", "j", "underlying", "tick_spacing"}
                },
            }
            for edge in pruned[:80]
        ]
        snapshot["three_leg_pruned_edges_truncated"] = bool(len(pruned) > 80)
    return snapshot


async def _safe_venue_quote_batch(
    family: str,
    quote_call: Any,
    *,
    expected_count: int,
    diagnostics: Dict[str, Any],
) -> List[Any]:
    """Isolate adapter failures and preserve one result slot per requested edge.

    A transient failure in one DEX adapter must not abort unrelated venue batches.
    Cancellation is deliberately propagated so the parent scan deadline remains
    enforceable. Exception details are reduced to stable, non-sensitive classes.
    """
    expected = max(0, int(expected_count))

    def _failure_count() -> int:
        raw = diagnostics.get("failure_reasons") or {}
        if not isinstance(raw, Mapping):
            return 0
        total = 0
        for value in raw.values():
            try:
                total += max(0, int(value or 0))
            except (TypeError, ValueError, OverflowError):
                continue
        return total

    _failure_count_before = _failure_count()
    try:
        raw_results = await quote_call
    except asyncio.CancelledError:
        raise
    except _SAFE_EDGE_QUOTE_EXCEPTIONS as exc:
        # If an adapter records failures before raising, only classify the
        # unaccounted remainder; the abandoned batch has no usable result map.
        newly_classified = max(0, _failure_count() - _failure_count_before)
        missing_failure_count = max(0, expected - newly_classified)
        reasons = diagnostics.setdefault("failure_reasons", {})
        reason = f"quote_batch_exception_{str(family or 'unknown').strip().lower()[:48]}"
        reasons[reason] = int(reasons.get(reason, 0) or 0) + missing_failure_count
        exception_types = diagnostics.setdefault("batch_exception_types", {})
        exception_types[reason] = type(exc).__name__.lower()[:48]
        return [None] * expected

    try:
        results = list(raw_results or [])
    except (TypeError, ValueError):
        results = []

    if len(results) < expected:
        missing = expected - len(results)
        reasons = diagnostics.setdefault("failure_reasons", {})
        reason = f"quote_batch_missing_results_{str(family or 'unknown').strip().lower()[:48]}"
        reasons[reason] = int(reasons.get(reason, 0) or 0) + missing
        return [*results, *([None] * missing)]
    if len(results) > expected:
        diagnostics["quote_batch_extra_results"] = int(
            diagnostics.get("quote_batch_extra_results", 0) or 0
        ) + (len(results) - expected)
        return results[:expected]
    return results


def _edge_quote_cache_key(edge: Edge, amount_in: int) -> str:
    """Match the per-block quote cache key used by every venue adapter."""
    return (
        f"edge:{edge.dex}:{edge.venue}:{edge.token_in}:{edge.token_out}:"
        f"{json_key(edge.params)}:{int(amount_in)}"
    )


async def quote_edges_batch(
    rpc,
    cfg,
    cache: PerBlockCache,
    edges: List[Edge],
    amount_in: int,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[Tuple[int, Dict[str, Any]]]]:
    """Batch-quote many edges for the same amount_in.

    Highest-ROI speedup: many quote calls become a handful of batched JSON-RPC requests.

    Returns a mapping edge_key(edge) -> (amount_out, meta) or None
    """
    out: Dict[str, Optional[Tuple[int, Dict[str, Any]]]] = {}
    if metrics is None:
        metrics = {}
    quote_diagnostics: Dict[str, Any] = {}
    batch_successes = 0
    metrics.setdefault("quote_failure_reasons", {})
    metrics.setdefault("quote_failure_reasons_by_adapter", {})
    metrics.setdefault("quote_query_revert_decoded", 0)
    for metric_name in (
        "quote_attempts_by_family",
        "quote_network_requests_by_family",
        "quote_successes_by_family",
        "quote_failures_by_family",
        "quote_cancelled_by_family",
        "quote_adapter_unavailable_by_family",
    ):
        metrics.setdefault(metric_name, {})
    adapter_unavailable_count = 0
    query_revert_count_merged = 0

    def _increment_family_metric(metric_name: str, edge: Edge) -> None:
        family = _scan_edge_family(edge)
        values = metrics.setdefault(metric_name, {})
        values[family] = int(values.get(family, 0) or 0) + 1
    missing_univ3: List[Tuple[int, Edge]] = []
    missing_curve: List[Tuple[int, Edge]] = []
    missing_bal: List[Tuple[int, Edge]] = []
    missing_aero: List[Tuple[int, Edge]] = []
    missing_slipstream: List[Tuple[int, Edge]] = []
    missing_camelot_algebra: List[Tuple[int, Edge]] = []
    missing_camelot_v2: List[Tuple[int, Edge]] = []
    missing_constant_product: List[Tuple[int, Edge]] = []

    # read cache first
    for idx, e in enumerate(edges):
        ek = edge_key(e)
        ck = _edge_quote_cache_key(e, amount_in)
        hit = cache.get(ck)
        if hit is not None:
            out[ek] = hit
            metrics["cache_hits"] = int(metrics.get("cache_hits", 0)) + 1
            continue
        if e.dex == "univ3":
            missing_univ3.append((idx, e))
        elif e.dex == "curve":
            missing_curve.append((idx, e))
        elif e.dex == "balancer":
            missing_bal.append((idx, e))
        elif e.dex == "aerodrome":
            missing_aero.append((idx, e))
        elif e.dex == "slipstream":
            missing_slipstream.append((idx, e))
        elif e.dex == "camelot_algebra":
            missing_camelot_algebra.append((idx, e))
        elif e.dex == "camelot_v2":
            missing_camelot_v2.append((idx, e))
        elif e.dex == "constant_product":
            missing_constant_product.append((idx, e))
        else:
            out[ek] = None

    metrics.setdefault("failed_quote_edge_samples", [])
    successful_edges = metrics.setdefault("_successful_quote_edge_keys", set())
    successful_pools = metrics.setdefault("_successful_quote_pool_keys", set())
    successful_pairs = metrics.setdefault("_successful_quote_pair_keys", set())

    def _record_success_edge(edge: Edge) -> None:
        nonlocal batch_successes
        batch_successes += 1
        _increment_family_metric("quote_successes_by_family", edge)
        if isinstance(successful_edges, set):
            successful_edges.add(edge_key(edge))
        if isinstance(successful_pools, set):
            pool = str(edge.params.get("pool") or edge.params.get("pool_id") or edge.venue or "").lower()
            successful_pools.add(f"{edge.dex}:{pool}")
        if isinstance(successful_pairs, set):
            successful_pairs.add(f"{edge.token_in.lower()}:{edge.token_out.lower()}")

    def _record_failed_edge(edge: Edge) -> None:
        _increment_family_metric("quote_failures_by_family", edge)
        samples = metrics["failed_quote_edge_samples"]
        if len(samples) < 256:
            samples.append(edge_key(edge))

    # Validate Balancer request payloads before marking the batch as dispatched.
    # A malformed pool ID/token pair is a local quote failure, not an RPC
    # network request, and must not abort valid Balancer siblings.
    local_validation_failures = 0
    valid_balancer: List[Tuple[int, Edge]] = []
    for index, edge in missing_bal:
        try:
            build_balancer_query_batchswap_calldata(
                str(edge.params.get("pool_id") or ""),
                str(edge.token_in),
                str(edge.token_out),
                int(amount_in),
            )
        except (TypeError, ValueError, OverflowError):
            local_validation_failures += 1
            _increment_family_metric("quote_attempts_by_family", edge)
            metrics["quote_requests"] = int(metrics.get("quote_requests", 0) or 0) + 1
            _record_failed_edge(edge)
            out[edge_key(edge)] = None
            quote_diagnostics.setdefault("failure_reasons", {})
            reasons = quote_diagnostics["failure_reasons"]
            reasons["invalid_balancer_request"] = int(
                reasons.get("invalid_balancer_request", 0) or 0
            ) + 1
            reasons_by_adapter = metrics.setdefault("quote_failure_reasons_by_adapter", {})
            adapter_reasons = reasons_by_adapter.setdefault("balancer", {})
            adapter_reasons["invalid_balancer_request"] = int(
                adapter_reasons.get("invalid_balancer_request", 0) or 0
            ) + 1
            continue
        valid_balancer.append((index, edge))
    missing_bal = valid_balancer

    def _merge_partial_quote_diagnostics(*, include_adapter_unavailable: bool) -> None:
        nonlocal query_revert_count_merged
        accumulated = {
            str(key): max(0, int(value or 0))
            for key, value in dict(metrics.get("quote_failure_reasons") or {}).items()
        }
        for reason, count in dict(quote_diagnostics.get("failure_reasons") or {}).items():
            accumulated[str(reason)] = accumulated.get(str(reason), 0) + max(0, int(count or 0))
        if include_adapter_unavailable and adapter_unavailable_count:
            accumulated["quote_adapter_unavailable"] = (
                accumulated.get("quote_adapter_unavailable", 0) + adapter_unavailable_count
            )
        metrics["quote_failure_reasons"] = accumulated
        current_query_reverts = max(
            0, int(quote_diagnostics.get("query_revert_decoded", 0) or 0)
        )
        query_revert_delta = max(0, current_query_reverts - query_revert_count_merged)
        if query_revert_delta:
            metrics["quote_query_revert_decoded"] = (
                int(metrics.get("quote_query_revert_decoded", 0) or 0)
                + query_revert_delta
            )
        query_revert_count_merged = max(
            query_revert_count_merged, current_query_reverts
        )

    def _record_adapter_failure_reasons(
        adapter: str,
        before: Mapping[str, Any],
    ) -> None:
        current = dict(quote_diagnostics.get("failure_reasons") or {})
        adapter_name = str(adapter or "unknown").strip().lower()[:64] or "unknown"
        deltas: Dict[str, int] = {}
        for reason, raw_count in current.items():
            try:
                delta = max(0, int(raw_count or 0) - int(before.get(reason, 0) or 0))
            except (TypeError, ValueError, OverflowError):
                continue
            if delta:
                key = str(reason or "unknown")[:96]
                deltas[key] = deltas.get(key, 0) + delta
        if not deltas:
            return
        by_adapter = metrics.setdefault("quote_failure_reasons_by_adapter", {})
        target = by_adapter.setdefault(adapter_name, {})
        for reason, delta in deltas.items():
            target[reason] = int(target.get(reason, 0) or 0) + int(delta)

    async def _run_quote_family_batch(
        family: str,
        family_edges: Sequence[Edge],
        quote_call: Any,
    ) -> List[Any]:
        # Count work only when this family is actually dispatched. Previously all
        # families were pre-counted before the first await, so cancellation of an
        # early batch falsely reported later families as network attempts.
        for edge in family_edges:
            _increment_family_metric("quote_attempts_by_family", edge)
            _increment_family_metric("quote_network_requests_by_family", edge)
        metrics["quote_requests"] = int(metrics.get("quote_requests", 0) or 0) + len(family_edges)
        if family_edges:
            metrics["network_batches"] = int(metrics.get("network_batches", 0) or 0) + 1
        before_reasons = dict(quote_diagnostics.get("failure_reasons") or {})
        try:
            result = await quote_call
        except asyncio.CancelledError:
            _record_adapter_failure_reasons(family, before_reasons)
            for edge in family_edges:
                _increment_family_metric("quote_cancelled_by_family", edge)
            metrics["quote_cancelled"] = int(metrics.get("quote_cancelled", 0) or 0) + len(family_edges)
            # Retain failure classifications from completed subcalls, but do not
            # label interrupted quote results as RPC reverts or zero-output failures.
            _merge_partial_quote_diagnostics(include_adapter_unavailable=True)
            raise
        _record_adapter_failure_reasons(family, before_reasons)
        return result

    adapter_groups = (
        (missing_univ3, bool(getattr(cfg.chain, "univ3_quoter_v2", ""))),
        (missing_curve, True),
        (missing_bal, bool(getattr(cfg.chain, "balancer_vault", ""))),
        (missing_aero, bool(getattr(cfg.chain, "aerodrome_router", ""))),
        (missing_slipstream, bool(getattr(cfg.chain, "slipstream_quoter_v2", ""))),
        (missing_camelot_algebra, bool(getattr(cfg.chain, "camelot_algebra_quoter_v2", ""))),
        (missing_camelot_v2, bool(getattr(cfg.chain, "camelot_v2_router", ""))),
        (missing_constant_product, True),
    )
    for group, adapter_available in adapter_groups:
        for _, edge in group:
            available = bool(adapter_available)
            if edge.dex == "constant_product":
                available = available and bool(edge.venue)
            if available:
                continue
            # A missing adapter is a known local failure, not an RPC request.
            _increment_family_metric("quote_attempts_by_family", edge)
            metrics["quote_requests"] = int(metrics.get("quote_requests", 0) or 0) + 1
            adapter_unavailable_count += 1
            _increment_family_metric("quote_adapter_unavailable_by_family", edge)
            _record_failed_edge(edge)
            out[edge_key(edge)] = None

    # UniV3 batch
    if missing_univ3 and getattr(cfg.chain, "univ3_quoter_v2", ""):
        reqs = []
        order: List[Edge] = []
        for _, e in missing_univ3:
            fee = int(e.params.get("fee", 3000))
            reqs.append((e.token_in, e.token_out, fee, int(amount_in), 0))
            order.append(e)
        quotes = await _run_quote_family_batch(
            "univ3",
            order,
            _safe_venue_quote_batch(
                "univ3",
                quote_exact_input_single_batch(
                    rpc, cfg.chain.univ3_quoter_v2, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (
                    int(q.amount_out),
                    {"gas_estimate": int(q.gas_estimate), "fee": int(e.params.get("fee", 3000))},
                )
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    # Curve batch (two-stage underlying fallback inside quote_curve_many)
    if missing_curve:
        reqs = []
        order = []
        for _, e in missing_curve:
            pool = e.venue
            i = int(e.params.get("i", 0))
            j = int(e.params.get("j", 0))
            underlying = bool(e.params.get("underlying", False))
            reqs.append((pool, i, j, int(amount_in), underlying))
            order.append(e)
        quotes = await _run_quote_family_batch(
            "curve",
            order,
            _safe_venue_quote_batch(
                "curve",
                quote_curve_many(rpc, reqs, diagnostics=quote_diagnostics),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (
                    int(q.amount_out),
                    {
                        "used_underlying": bool(q.used_underlying),
                        "i": int(e.params.get("i", 0)),
                        "j": int(e.params.get("j", 0)),
                    },
                )
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    # Aerodrome V1 batch
    if missing_aero and getattr(cfg.chain, "aerodrome_router", ""):
        reqs = [
            (e.token_in, e.token_out, int(amount_in), bool(e.params.get("stable", False)), str(e.params.get("factory") or ""))
            for _, e in missing_aero
        ]
        order = [e for _, e in missing_aero]
        quotes = await _run_quote_family_batch(
            "aerodrome",
            order,
            _safe_venue_quote_batch(
                "aerodrome",
                quote_aerodrome_many(
                    rpc, cfg.chain.aerodrome_router, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            out[ek] = None if q is None else (q.amount_out, {"stable": q.stable, "factory": q.factory})
            cache.set(ck, out[ek])
            if q is not None:
                _record_success_edge(e)
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
            else:
                _record_failed_edge(e)

    # Slipstream CL batch. tickSpacing is the native pool key, not a synthetic fee tier.
    if missing_slipstream and getattr(cfg.chain, "slipstream_quoter_v2", ""):
        reqs = [
            (e.token_in, e.token_out, int(e.params.get("tick_spacing", 0)), int(amount_in))
            for _, e in missing_slipstream
        ]
        order = [e for _, e in missing_slipstream]
        quotes = await _run_quote_family_batch(
            "slipstream",
            order,
            _safe_venue_quote_batch(
                "slipstream",
                quote_slipstream_many(
                    rpc, cfg.chain.slipstream_quoter_v2, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (
                    int(q.amount_out),
                    {"gas_estimate": int(q.gas_estimate), "tick_spacing": int(q.tick_spacing), "factory": str(e.params.get("factory") or "")},
                )
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    # Camelot AMMv3 / Algebra batch. Algebra returns its current dynamic fee.
    if missing_camelot_algebra and getattr(cfg.chain, "camelot_algebra_quoter_v2", ""):
        reqs = [(e.token_in, e.token_out, int(amount_in)) for _, e in missing_camelot_algebra]
        order = [e for _, e in missing_camelot_algebra]
        quotes = await _run_quote_family_batch(
            "camelot_algebra",
            order,
            _safe_venue_quote_batch(
                "camelot_algebra",
                quote_camelot_algebra_many(
                    rpc, cfg.chain.camelot_algebra_quoter_v2, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (
                    int(q.amount_out),
                    {"gas_estimate": int(q.gas_estimate), "fee": int(q.fee), "factory": str(e.params.get("factory") or "")},
                )
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    # Camelot V2 constant-product batch. Router getAmountsOut is canonical and
    # captures the pair's current directional fee rather than assuming a fixed
    # fee in the economic model.
    if missing_camelot_v2 and getattr(cfg.chain, "camelot_v2_router", ""):
        reqs = [(e.token_in, e.token_out, int(amount_in)) for _, e in missing_camelot_v2]
        order = [e for _, e in missing_camelot_v2]
        quotes = await _run_quote_family_batch(
            "camelot_v2",
            order,
            _safe_venue_quote_batch(
                "camelot_v2",
                quote_camelot_v2_many(
                    rpc, cfg.chain.camelot_v2_router, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (int(q.amount_out), {"fee_model": "router_observed", "pool": str(e.params.get("pool") or "")})
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    # Generic constant-product batch. Routers are grouped so multiple
    # configured V2-family venues are quoted in parallel while preserving
    # venue-specific pool identity in the route graph.
    if missing_constant_product:
        by_router: Dict[str, List[Edge]] = {}
        for _, e in missing_constant_product:
            by_router.setdefault(str(e.venue), []).append(e)
        for router, grouped in by_router.items():
            reqs = [(e.token_in, e.token_out, int(amount_in)) for e in grouped]
            quotes = await _run_quote_family_batch(
                "constant_product",
                grouped,
                _safe_venue_quote_batch(
                    "constant_product",
                    quote_constant_product_many(
                        rpc, router, reqs, diagnostics=quote_diagnostics
                    ),
                    expected_count=len(grouped),
                    diagnostics=quote_diagnostics,
                ),
            )
            for e, q in zip(grouped, quotes):
                ek = edge_key(e)
                ck = _edge_quote_cache_key(e, amount_in)
                if q:
                    metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                    val = (int(q.amount_out), {"fee_model": "router_observed", "pool": str(e.params.get("pool") or ""), "venue_name": str(e.params.get("venue_name") or "")})
                    out[ek] = val
                    cache.set(ck, val)
                    _record_success_edge(e)
                else:
                    out[ek] = None
                    cache.set(ck, None)
                    _record_failed_edge(e)

    # Balancer batch
    if missing_bal and getattr(cfg.chain, "balancer_vault", ""):
        reqs = []
        order = []
        for _, e in missing_bal:
            pool_id = str(e.params.get("pool_id") or "")
            reqs.append((pool_id, e.token_in, e.token_out, int(amount_in)))
            order.append(e)
        quotes = await _run_quote_family_batch(
            "balancer",
            order,
            _safe_venue_quote_batch(
                "balancer",
                quote_balancer_given_in_many(
                    rpc, cfg.chain.balancer_vault, reqs, diagnostics=quote_diagnostics
                ),
                expected_count=len(order),
                diagnostics=quote_diagnostics,
            ),
        )
        for e, q in zip(order, quotes):
            ek = edge_key(e)
            ck = _edge_quote_cache_key(e, amount_in)
            if q:
                metrics["quote_successes"] = int(metrics.get("quote_successes", 0)) + 1
                val = (int(q.amount_out), {"pool_id": str(e.params.get("pool_id") or "")})
                out[ek] = val
                cache.set(ck, val)
                _record_success_edge(e)
            else:
                out[ek] = None
                cache.set(ck, None)
                _record_failed_edge(e)

    failure_counts = {
        str(k): int(v)
        for k, v in dict(quote_diagnostics.get("failure_reasons") or {}).items()
    }
    # A failed edge without a lower-layer classification is still a concrete
    # observation. Attribute the residual instead of silently losing it from
    # the quote failure denominator; never convert it into a successful quote.
    classified_failures = sum(max(0, int(v)) for v in failure_counts.values())
    requested_edge_count = local_validation_failures + sum(
        len(group)
        for group in (
            missing_univ3,
            missing_curve,
            missing_bal,
            missing_aero,
            missing_slipstream,
            missing_camelot_algebra,
            missing_camelot_v2,
            missing_constant_product,
        )
    )
    requested_failures = max(0, requested_edge_count - batch_successes)
    if adapter_unavailable_count:
        failure_counts["quote_adapter_unavailable"] = (
            int(failure_counts.get("quote_adapter_unavailable", 0) or 0)
            + int(adapter_unavailable_count)
        )
    classified_failures = sum(max(0, int(v)) for v in failure_counts.values())
    residual_unknown = max(0, requested_failures - classified_failures)
    if residual_unknown:
        failure_counts["unknown_quote_failure"] = int(
            failure_counts.get("unknown_quote_failure", 0) + residual_unknown
        )

    # quote_edges_batch is invoked repeatedly during two-leg and three-leg
    # evaluation. Preserve classifications from earlier batches instead of
    # replacing them with only the most recent batch's reasons.
    accumulated_failure_counts = {
        str(key): max(0, int(value))
        for key, value in dict(metrics.get("quote_failure_reasons") or {}).items()
    }
    for reason, count in failure_counts.items():
        accumulated_failure_counts[str(reason)] = (
            accumulated_failure_counts.get(str(reason), 0) + max(0, int(count))
        )
    metrics["quote_failure_reasons"] = accumulated_failure_counts
    metrics["quote_query_revert_decoded"] = (
        int(metrics.get("quote_query_revert_decoded", 0) or 0)
        + max(0, int(quote_diagnostics.get("query_revert_decoded", 0) or 0))
    )
    metrics["failed_quote_edge_count"] = int(len(metrics.get("failed_quote_edge_samples") or []))
    # Coverage sets intentionally persist across all quote batches for a scan;
    # the caller finalizes them once after both first- and second-leg phases.
    metrics["quote_fallback_attempts"] = int(quote_diagnostics.get("fallback_attempts", 0) or 0)
    metrics["quote_fallback_successes"] = int(quote_diagnostics.get("fallback_successes", 0) or 0)
    # ensure all are present
    for e in edges:
        ek = edge_key(e)
        out.setdefault(ek, None)
    return out


def _quote_family_metric_snapshot(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    """Publish bounded venue-family quote counters from one scan's accumulator."""
    metric_names = (
        "quote_attempts_by_family",
        "quote_network_requests_by_family",
        "quote_successes_by_family",
        "quote_failures_by_family",
        "quote_cancelled_by_family",
        "quote_adapter_unavailable_by_family",
    )
    snapshot: Dict[str, Any] = {}
    for metric_name in metric_names:
        raw = metrics.get(metric_name)
        counters = raw if isinstance(raw, Mapping) else {}
        normalized: Dict[str, int] = {}
        for family, count in counters.items():
            name = str(family or "").strip().lower()[:64]
            if not name:
                continue
            try:
                value = max(0, int(count or 0))
            except (TypeError, ValueError, OverflowError):
                continue
            normalized[name] = normalized.get(name, 0) + value
        snapshot[metric_name] = normalized
    try:
        snapshot["quote_query_revert_decoded"] = max(
            0, int(metrics.get("quote_query_revert_decoded", 0) or 0)
        )
    except (TypeError, ValueError, OverflowError):
        snapshot["quote_query_revert_decoded"] = 0
    return snapshot

def _quote_failure_reason_snapshot(metrics: Mapping[str, Any]) -> Dict[str, Dict[str, Dict[str, int]]]:
    """Publish bounded low-cardinality failure causes grouped by adapter."""
    raw = metrics.get("quote_failure_reasons_by_adapter")
    adapters = raw if isinstance(raw, Mapping) else {}
    normalized: Dict[str, Dict[str, int]] = {}
    for adapter, reasons in adapters.items():
        adapter_name = str(adapter or "unknown").strip().lower()[:64] or "unknown"
        source = reasons if isinstance(reasons, Mapping) else {}
        target: Dict[str, int] = {}
        for reason, count in source.items():
            name = str(reason or "unknown").strip().lower()[:96] or "unknown"
            try:
                value = max(0, int(count or 0))
            except (TypeError, ValueError, OverflowError):
                continue
            target[name] = target.get(name, 0) + value
        normalized[adapter_name] = target
    return {"quote_failure_reasons_by_adapter": normalized}


def _finalize_quote_coverage(metrics: Dict[str, Any]) -> None:
    for public_name, internal_name in (
        ("successful_quote_edge_count", "_successful_quote_edge_keys"),
        ("successful_quote_pool_count", "_successful_quote_pool_keys"),
        ("successful_quote_pair_count", "_successful_quote_pair_keys"),
    ):
        values = metrics.get(internal_name)
        metrics[public_name] = int(len(values)) if isinstance(values, set) else 0
        metrics.pop(internal_name, None)


def _scan_edge_family(edge: Edge) -> str:
    """Identify a venue family for bounded provider-comparison sampling."""
    family = str(getattr(edge, "dex", "") or "unknown").strip().lower()
    if family == "constant_product":
        params = getattr(edge, "params", {}) or {}
        venue_name = str(params.get("venue_name") or "").strip().lower()
        if venue_name:
            return venue_name
    return family


def _representative_scan_edge_subset(edges: List[Edge], cap: int) -> List[Edge]:
    """Take a family-balanced subset while preserving order within each family."""
    buckets: Dict[str, List[Edge]] = {}
    for edge in list(edges or []):
        buckets.setdefault(_scan_edge_family(edge), []).append(edge)
    families = list(buckets)
    selected: List[Edge] = []
    limit = max(0, int(cap))
    row_count = max((len(bucket) for bucket in buckets.values()), default=0)
    for row_index in range(row_count):
        for family in families:
            bucket = buckets[family]
            if row_index < len(bucket):
                selected.append(bucket[row_index])
            if len(selected) >= limit:
                return selected
    return selected


def _apply_scan_edge_cap(
    edges: List[Edge],
    max_scan_edges: Optional[int],
    metrics: Dict[str, Any],
) -> List[Edge]:
    """Bound a caller's scan graph without changing canonical route construction.

    Provider comparison uses a bounded, venue-family-balanced sample so the
    provider race cannot monopolize the chain scan. The selected provider later
    runs without this cap and performs the full economic frontier.
    """
    selected = list(edges)
    metrics["scan_edges_before_cap"] = int(len(selected))
    if max_scan_edges in (None, ""):
        metrics["scan_edges_selected"] = int(len(selected))
        return selected
    try:
        cap = max(1, int(max_scan_edges))
    except (TypeError, ValueError):
        cap = len(selected)
    metrics["scan_edge_cap"] = int(cap)
    if len(selected) > cap:
        selected = _representative_scan_edge_subset(selected, cap)
        metrics["scan_edge_selection_policy"] = "round_robin_by_venue_family"
    metrics["scan_edges_selected"] = int(len(selected))
    metrics["scan_edges_capped"] = int(max(0, len(edges) - len(selected)))
    return selected


def build_edges(
    cfg,
    *,
    extra_v3_pairs: Optional[List[dict]] = None,
    extra_curve_pools: Optional[List[dict]] = None,
    extra_balancer_pools: Optional[List[dict]] = None,
    extra_aerodrome_pools: Optional[List[dict]] = None,
    extra_slipstream_pools: Optional[List[dict]] = None,
    extra_camelot_algebra_pools: Optional[List[dict]] = None,
    extra_camelot_v2_pools: Optional[List[dict]] = None,
    extra_constant_product_pools: Optional[List[dict]] = None,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> List[Edge]:
    edges: List[Edge] = []
    chain = cfg.chain
    flags = getattr(cfg, "flags", None)
    pool_inputs = {
        "univ3": list(getattr(chain, "v3_pairs", []) or []) + list(extra_v3_pairs or []),
        "curve": list(getattr(chain, "curve_pools", []) or []) + list(extra_curve_pools or []),
        "balancer": list(getattr(chain, "balancer_pools", []) or []) + list(extra_balancer_pools or []),
        "aerodrome": list(getattr(chain, "aerodrome_pools", []) or []) + list(extra_aerodrome_pools or []),
        "slipstream": list(getattr(chain, "slipstream_pools", []) or []) + list(extra_slipstream_pools or []),
        "camelot_algebra": list(getattr(chain, "camelot_algebra_pools", []) or []) + list(extra_camelot_algebra_pools or []),
        "camelot_v2": list(getattr(chain, "camelot_v2_pools", []) or []) + list(extra_camelot_v2_pools or []),
        "constant_product": list(getattr(chain, "constant_product_pools", []) or []) + list(extra_constant_product_pools or []),
    }
    configured_cp = {
        (str(v.get("name") or "").lower(), str(v.get("router") or "").lower())
        for v in (getattr(chain, "constant_product_venues", []) or [])
        if isinstance(v, dict)
    }
    family_prerequisites = {
        "univ3": {"enabled": bool(getattr(chain, "univ3_quoter_v2", "")), "required": "univ3_quoter_v2"},
        "curve": {"enabled": bool(getattr(flags, "enable_curve_autogen", True)), "required": "enable_curve_autogen"},
        "balancer": {
            "enabled": bool(getattr(flags, "enable_balancer_autogen", True)) and bool(getattr(chain, "balancer_vault", "")),
            "feature_enabled": bool(getattr(flags, "enable_balancer_autogen", True)),
            "vault_configured": bool(getattr(chain, "balancer_vault", "")),
            "required": "enable_balancer_autogen + balancer_vault",
        },
        "aerodrome": {"enabled": bool(getattr(chain, "aerodrome_router", "")), "required": "aerodrome_router"},
        "slipstream": {"enabled": bool(getattr(chain, "slipstream_quoter_v2", "")), "required": "slipstream_quoter_v2"},
        "camelot_algebra": {"enabled": bool(getattr(chain, "camelot_algebra_quoter_v2", "")), "required": "camelot_algebra_quoter_v2"},
        "camelot_v2": {"enabled": bool(getattr(chain, "camelot_v2_router", "")), "required": "camelot_v2_router"},
        "constant_product": {
            "enabled": True,
            "configured_venue_count": len(configured_cp),
            "venue_filter_enabled": bool(configured_cp),
        },
    }
    blocked_by_configuration = {}
    for family, rows in pool_inputs.items():
        prerequisite = family_prerequisites[family]
        if rows and not prerequisite["enabled"]:
            blocked_by_configuration[family] = (
                "family_disabled" if family == "curve" and not prerequisite["enabled"]
                else "balancer_feature_disabled" if family == "balancer" and not prerequisite["feature_enabled"]
                else "balancer_vault_missing" if family == "balancer" and not prerequisite["vault_configured"]
                else str(prerequisite.get("required") or "required_configuration_missing")
            )
    if cfg.chain.univ3_quoter_v2:
        # For execution we prefer SwapRouter; for quoting we use QuoterV2.
        # Safe default: if swap router is missing, we keep venue as quoter and
        # runtime will mark can_execute=false.
        v3_exec_venue = cfg.chain.univ3_swap_router or cfg.chain.univ3_quoter_v2
        v3_pairs = list(cfg.chain.v3_pairs or [])
        if extra_v3_pairs:
            # Discovered pools are additive and bounded; scanner de-dupes below.
            v3_pairs.extend(list(extra_v3_pairs))
        for p in v3_pairs:
            edges.append(
                Edge(
                    "univ3",
                    v3_exec_venue,
                    p["token_in"],
                    p["token_out"],
                    {
                        "fee": int(p.get("fee", 3000)),
                        **({"pool": str(p.get("pool"))} if p.get("pool") else {}),
                    },
                )
            )
            # auto reverse
            edges.append(
                Edge(
                    "univ3",
                    v3_exec_venue,
                    p["token_out"],
                    p["token_in"],
                    {
                        "fee": int(p.get("fee", 3000)),
                        **({"pool": str(p.get("pool"))} if p.get("pool") else {}),
                    },
                )
            )
    if bool(getattr(cfg.flags, "enable_curve_autogen", True)):
        curve_pools = list(cfg.chain.curve_pools or [])
        if extra_curve_pools:
            curve_pools.extend(list(extra_curve_pools))
        for p in curve_pools:
            pool = p["pool"]
            edges.append(
                Edge(
                    "curve",
                    pool,
                    p.get("token_in", ""),
                    p.get("token_out", ""),
                    {
                        "i": int(p["i"]),
                        "j": int(p["j"]),
                        "underlying": bool(p.get("underlying", False)),
                    },
                )
            )
            edges.append(
                Edge(
                    "curve",
                    pool,
                    p.get("token_out", ""),
                    p.get("token_in", ""),
                    {
                        "i": int(p["j"]),
                        "j": int(p["i"]),
                        "underlying": bool(p.get("underlying", False)),
                    },
                )
            )
    if bool(getattr(cfg.flags, "enable_balancer_autogen", True)) and cfg.chain.balancer_vault:
        balancer_pools = list(cfg.chain.balancer_pools or [])
        if extra_balancer_pools:
            balancer_pools.extend(list(extra_balancer_pools))
        for p in balancer_pools:
            edges.append(
                Edge(
                    "balancer",
                    cfg.chain.balancer_vault,
                    p["token_in"],
                    p["token_out"],
                    {"pool_id": p["pool_id"]},
                )
            )
            edges.append(
                Edge(
                    "balancer",
                    cfg.chain.balancer_vault,
                    p["token_out"],
                    p["token_in"],
                    {"pool_id": p["pool_id"]},
                )
            )
    if getattr(cfg.chain, "aerodrome_router", ""):
        aerodrome_pools = list(getattr(cfg.chain, "aerodrome_pools", []) or [])
        if extra_aerodrome_pools:
            aerodrome_pools.extend(list(extra_aerodrome_pools))
        for p in aerodrome_pools:
            params = {
                "stable": bool(p.get("stable", False)),
                "factory": str(p.get("factory") or getattr(cfg.chain, "aerodrome_default_factory", "")),
                **({"pool": str(p.get("pool"))} if p.get("pool") else {}),
            }
            if not params["factory"]:
                continue
            edges.append(Edge("aerodrome", str(cfg.chain.aerodrome_router), p["token_in"], p["token_out"], params))
            edges.append(Edge("aerodrome", str(cfg.chain.aerodrome_router), p["token_out"], p["token_in"], params))
    if getattr(cfg.chain, "slipstream_quoter_v2", ""):
        slipstream_pools = list(getattr(cfg.chain, "slipstream_pools", []) or [])
        if extra_slipstream_pools:
            slipstream_pools.extend(list(extra_slipstream_pools))
        for p in slipstream_pools:
            tick_spacing = int(p.get("tick_spacing", 0))
            if tick_spacing <= 0:
                continue
            params = {
                "tick_spacing": tick_spacing,
                "factory": str(p.get("factory") or ""),
                **({"pool": str(p.get("pool"))} if p.get("pool") else {}),
            }
            if not params["factory"]:
                continue
            venue = str(getattr(cfg.chain, "slipstream_swap_router", "") or getattr(cfg.chain, "slipstream_quoter_v2", ""))
            edges.append(Edge("slipstream", venue, p["token_in"], p["token_out"], params))
            edges.append(Edge("slipstream", venue, p["token_out"], p["token_in"], params))
    if getattr(cfg.chain, "camelot_algebra_quoter_v2", ""):
        camelot_pools = list(getattr(cfg.chain, "camelot_algebra_pools", []) or [])
        if extra_camelot_algebra_pools:
            camelot_pools.extend(list(extra_camelot_algebra_pools))
        for p in camelot_pools:
            factory = str(p.get("factory") or getattr(cfg.chain, "camelot_algebra_factory", "") or "")
            spacing = int(p.get("tick_spacing", 0) or 0)
            if not factory or spacing <= 0:
                continue
            params = {"factory": factory, "tick_spacing": spacing}
            if p.get("pool"):
                params["pool"] = str(p.get("pool"))
            venue = str(getattr(cfg.chain, "camelot_algebra_swap_router", "") or getattr(cfg.chain, "camelot_algebra_quoter_v2", ""))
            edges.append(Edge("camelot_algebra", venue, p["token_in"], p["token_out"], params))
            edges.append(Edge("camelot_algebra", venue, p["token_out"], p["token_in"], params))
    if getattr(cfg.chain, "camelot_v2_router", ""):
        camelot_v2_pools = list(getattr(cfg.chain, "camelot_v2_pools", []) or [])
        if extra_camelot_v2_pools:
            camelot_v2_pools.extend(list(extra_camelot_v2_pools))
        for p in camelot_v2_pools:
            factory = str(p.get("factory") or getattr(cfg.chain, "camelot_v2_factory", "") or "")
            if not factory:
                continue
            params = {"factory": factory}
            if p.get("pool"):
                params["pool"] = str(p.get("pool"))
            venue = str(cfg.chain.camelot_v2_router)
            edges.append(Edge("camelot_v2", venue, p["token_in"], p["token_out"], params))
            edges.append(Edge("camelot_v2", venue, p["token_out"], p["token_in"], params))

    constant_product_pools = list(getattr(cfg.chain, "constant_product_pools", []) or [])
    if extra_constant_product_pools:
        constant_product_pools.extend(list(extra_constant_product_pools))
    for p in constant_product_pools:
        name = str(p.get("venue_name") or p.get("name") or "").lower()
        router = str(p.get("router") or "")
        factory = str(p.get("factory") or "")
        if not name or not router or not factory:
            continue
        if configured_cp and (name, router.lower()) not in configured_cp:
            continue
        params = {"pool": str(p.get("pool") or ""), "factory": factory, "venue_name": name}
        edges.append(Edge("constant_product", router, p["token_in"], p["token_out"], params))
        edges.append(Edge("constant_product", router, p["token_out"], p["token_in"], params))

    generated_edge_count = len(edges)
    # remove empty-token curve edges if unspecified
    edges = [e for e in edges if e.token_in and e.token_out]
    token_valid_edge_count = len(edges)
    # de-dupe
    seen = set()
    out = []
    for e in edges:
        k = (e.dex, e.venue, e.token_in, e.token_out, tuple(sorted(e.params.items())))
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    if diagnostics is not None:
        by_family: Dict[str, int] = {}
        for edge in out:
            family = _scan_edge_family(edge)
            by_family[family] = int(by_family.get(family, 0)) + 1
        cp_rejections: Dict[str, int] = {}
        for pool in pool_inputs["constant_product"]:
            name = str(pool.get("venue_name") or pool.get("name") or "").lower()
            router = str(pool.get("router") or "")
            factory = str(pool.get("factory") or "")
            if not name or not router or not factory:
                reason = "missing_name_router_or_factory"
            elif configured_cp and (name, router.lower()) not in configured_cp:
                reason = "venue_not_configured"
            elif not pool.get("token_in") or not pool.get("token_out"):
                reason = "missing_token_pair"
            else:
                continue
            cp_rejections[reason] = int(cp_rejections.get(reason, 0)) + 1
        balancer_rejections: Dict[str, int] = {}
        for pool in pool_inputs["balancer"]:
            if not family_prerequisites["balancer"]["enabled"]:
                continue
            if not pool.get("pool_id") or not pool.get("token_in") or not pool.get("token_out"):
                balancer_rejections["missing_pool_id_or_token_pair"] = int(
                    balancer_rejections.get("missing_pool_id_or_token_pair", 0)
                ) + 1
        diagnostics.clear()
        diagnostics.update({
            "input_pool_counts_by_family": {
                family: len(rows) for family, rows in pool_inputs.items()
            },
            "family_prerequisites": family_prerequisites,
            "blocked_by_configuration": blocked_by_configuration,
            "pool_validation_rejections_by_family": {
                key: value for key, value in {
                    "constant_product": cp_rejections,
                    "balancer": balancer_rejections,
                }.items() if value
            },
            "generated_edge_count_before_token_validation": int(generated_edge_count),
            "edge_count_after_token_validation": int(token_valid_edge_count),
            "edge_count_after_deduplication": int(len(out)),
            "edges_by_family_after_build": dict(sorted(by_family.items())),
        })
    return out


def _classify_two_leg_family(legs: List[Edge], stable_tokens: set[str]) -> str | None:
    e1, e2 = legs
    if (
        e1.dex == "univ3"
        and e2.dex == "univ3"
        and int(e1.params.get("fee", 3000)) != int(e2.params.get("fee", 3000))
        and {e1.token_in.lower(), e1.token_out.lower()}
        == {e2.token_in.lower(), e2.token_out.lower()}
    ):
        return "univ3_fee_tier_arb"
    dexes = {str(e1.dex), str(e2.dex)}
    tokens = {str(e.token_in).lower() for e in legs} | {str(e.token_out).lower() for e in legs}
    if dexes == {"univ3", "curve"}:
        return "stablecoin_dislocation" if stable_tokens and tokens & stable_tokens else "univ3_curve"
    if dexes == {"univ3", "balancer"}:
        return "univ3_balancer"
    if dexes == {"univ3", "slipstream"}:
        return "univ3_slipstream"
    if dexes == {"aerodrome", "slipstream"}:
        return "aerodrome_slipstream"
    if dexes == {"univ3", "camelot_algebra"}:
        return "univ3_camelot_algebra"
    if dexes == {"camelot_algebra", "slipstream"}:
        return "camelot_algebra_slipstream"
    return None


def _classify_route_family(cfg: Any, legs: List[Edge], *, route_type: str) -> str:
    """Name the opportunity shape; downstream strategy governance remains authoritative."""
    stable_tokens = {
        str(getattr(cfg.chain, "usdc", "") or "").lower(),
        str(getattr(cfg.chain, "usdt", "") or "").lower(),
    }
    stable_tokens.discard("")
    tokens = {str(e.token_in).lower() for e in legs} | {str(e.token_out).lower() for e in legs}

    if route_type == "2leg" and len(legs) == 2:
        family = _classify_two_leg_family(legs, stable_tokens)
        if family:
            return family

    if route_type == "3leg" and len(legs) == 3:
        weth = str(getattr(cfg.chain, "weth", "") or "").lower()
        if weth and weth in tokens and stable_tokens and tokens & stable_tokens:
            return "three_leg_stable_eth_loop"

    return "flash_arb"


def _is_same_pool_roundtrip(e1: Edge, e2: Edge) -> bool:
    """Return True only when both legs expose a reliable pool identity."""
    if str(e1.dex) != str(e2.dex):
        return False

    dex = str(e1.dex)
    if dex == "univ3":
        # The venue is normally the shared SwapRouter/Quoter, not the pool.
        # Without explicit pool metadata we cannot safely conclude that two
        # reverse edges hit the same pool; treating the router as the pool
        # would incorrectly discard legitimate cross-pool opportunities.
        p1 = str(e1.params.get("pool") or "").strip().lower()
        p2 = str(e2.params.get("pool") or "").strip().lower()
        if not p1 or not p2:
            return False
        return p1 == p2 and int(e1.params.get("fee", 3000)) == int(e2.params.get("fee", 3000))

    if dex == "curve":
        p1 = str(e1.venue or e1.params.get("pool") or "").strip().lower()
        p2 = str(e2.venue or e2.params.get("pool") or "").strip().lower()
        if not p1 or not p2:
            return False
        return p1 == p2 and bool(e1.params.get("underlying", False)) == bool(
            e2.params.get("underlying", False)
        )

    if dex == "balancer":
        p1 = str(e1.params.get("pool_id") or "").strip().lower()
        p2 = str(e2.params.get("pool_id") or "").strip().lower()
        return bool(p1 and p2 and p1 == p2)

    if dex == "aerodrome":
        p1 = str(e1.params.get("pool") or "").strip().lower()
        p2 = str(e2.params.get("pool") or "").strip().lower()
        return bool(p1 and p2 and p1 == p2 and bool(e1.params.get("stable", False)) == bool(e2.params.get("stable", False)) and str(e1.params.get("factory") or "").lower() == str(e2.params.get("factory") or "").lower())

    if dex == "slipstream":
        p1 = str(e1.params.get("pool") or "").strip().lower()
        p2 = str(e2.params.get("pool") or "").strip().lower()
        return bool(p1 and p2 and p1 == p2 and int(e1.params.get("tick_spacing", 0)) == int(e2.params.get("tick_spacing", 0)))

    if dex in {"camelot_algebra", "constant_product"}:
        p1 = str(e1.params.get("pool") or "").strip().lower()
        p2 = str(e2.params.get("pool") or "").strip().lower()
        return bool(p1 and p2 and p1 == p2)

    return False


def _pool_keys_for_leg(
    dex: str, token_in: str, token_out: str, params: Dict[str, Any], aux_hex: str
) -> str:
    """Stable conflict key used by portfolio optimizer.

    Key must be protocol-specific and avoid over-conflating pools.
    - UniswapV3: (token0, token1, fee)
    - Curve: (pool, i, j, underlying)
    - Balancer: (pool_id)

    Note: we intentionally do not include SwapRouter address for UniV3.
    """
    try:
        if dex == "univ3":
            fee = int(params.get("fee", 3000))
            a = token_in.lower()
            b = token_out.lower()
            if a > b:
                a, b = b, a
            return f"univ3:{a}:{b}:{fee}"
        if dex == "curve":
            pool = str(params.get("pool") or params.get("venue") or "")
            i = int(params.get("i", 0))
            j = int(params.get("j", 0))
            u = 1 if bool(params.get("underlying", False)) else 0
            return f"curve:{pool.lower()}:{i}:{j}:{u}"
        if dex == "balancer":
            pid = str(params.get("pool_id") or aux_hex or "")
            return f"bal:{pid.lower()}"
        if dex == "aerodrome":
            pool = str(params.get("pool") or "")
            return f"aero:{pool.lower()}"
        if dex == "slipstream":
            pool = str(params.get("pool") or "")
            spacing = int(params.get("tick_spacing", 0))
            return f"slipstream:{pool.lower()}:{spacing}"
        if dex == "camelot_algebra":
            pool = str(params.get("pool") or "")
            return f"camelot_algebra:{pool.lower()}"
        if dex == "constant_product":
            pool = str(params.get("pool") or "")
            return f"constant_product:{pool.lower()}"
    except _SAFE_POOL_KEY_EXCEPTIONS:
        return f"{dex}:{token_in.lower()}:{token_out.lower()}:{json_key(params)}"
    # fallback (worst-case): route-level uniqueness
    return f"{dex}:{token_in.lower()}:{token_out.lower()}:{json_key(params)}"



def _prefilter_reverse_candidates(
    revs: List[Edge],
    *,
    qmap1: Dict[str, Optional[Tuple[int, Dict[str, Any]]]],
    max_candidates: int,
    pool_event_cache: Any = None,
    current_block: int = 0,
) -> Tuple[List[Edge], Dict[str, int]]:
    """Bound reverse-leg quoting while preserving independent diversity axes.

    All reverse legs share the same token pair, so the base-size quote is a
    useful first-order price signal. Select one candidate per protocol, then
    distinct known pools, then distinct routers, before filling the remaining
    cap by quote score. Unknown pool identity is never misreported as pool
    diversity; every candidate still remains eligible for the final fill.
    """
    cap = max(3, min(12, int(max_candidates)))
    scored: List[Tuple[int, int, str, str, str, int, Edge]] = []
    for order, edge in enumerate(list(revs or [])):
        base_quote = qmap1.get(edge_key(edge))
        local_output = int(base_quote[0]) if base_quote else -1
        priority = 1
        if pool_event_cache is not None:
            try:
                priority = int(
                    pool_event_cache.edge_priority(
                        edge, current_block=int(current_block)
                    )
                )
            except (AttributeError, TypeError, ValueError):
                priority = 1
        protocol = _edge_protocol_identity(edge) or ""
        pool = _edge_pool_identity(edge) or ""
        router = _edge_router_identity(edge) or ""
        scored.append((local_output, priority, protocol, pool, router, -order, edge))

    scored.sort(
        key=lambda item: (item[0], item[1], item[3], item[4], item[5]),
        reverse=True,
    )
    selected: List[Edge] = []
    selected_ids: set[str] = set()

    def add_phase(predicate) -> None:
        for item in scored:
            edge = item[-1]
            ek = edge_key(edge)
            if ek in selected_ids or len(selected) >= cap:
                continue
            if not predicate(item):
                continue
            selected.append(edge)
            selected_ids.add(ek)

    protocols: set[str] = set()

    def _new_protocol(item: Tuple[int, int, str, str, str, int, Edge]) -> bool:
        protocol = item[2]
        if not protocol or protocol in protocols:
            return False
        protocols.add(protocol)
        return True

    add_phase(_new_protocol)

    pools: set[str] = set()

    def _new_pool(item: Tuple[int, int, str, str, str, int, Edge]) -> bool:
        pool = item[3]
        if not pool or pool in pools:
            return False
        pools.add(pool)
        return True

    add_phase(_new_pool)

    routers: set[str] = set()

    def _new_router(item: Tuple[int, int, str, str, str, int, Edge]) -> bool:
        router = item[4]
        if not router or router in routers:
            return False
        routers.add(router)
        return True

    add_phase(_new_router)
    add_phase(lambda _item: True)

    picked = selected[:cap]
    return picked, {
        "total": int(len(revs)),
        "selected": int(len(picked)),
        "filtered": int(max(0, len(revs) - len(picked))),
        "base_quote_available": int(
            sum(1 for edge in revs if qmap1.get(edge_key(edge)))
        ),
        "protocols_selected": int(
            len({_edge_protocol_identity(edge) for edge in picked if _edge_protocol_identity(edge)})
        ),
        "pools_selected": int(
            len({_edge_pool_identity(edge) for edge in picked if _edge_pool_identity(edge)})
        ),
        "routers_selected": int(
            len({_edge_router_identity(edge) for edge in picked if _edge_router_identity(edge)})
        ),
    }


def _count_triangle_completions(
    edge: Edge,
    adjacency: Mapping[str, Sequence[Edge]],
    by_pair: Mapping[Tuple[str, str], Sequence[Edge]],
) -> int:
    return sum(
        len(by_pair.get((second.token_out, edge.token_in), ()))
        for second in adjacency.get(edge.token_out, ())
        if second.token_out != edge.token_in
    )


def _triangle_edge_group_potential(
    item: Tuple[int, List[Edge]],
    *,
    adjacency: Mapping[str, Sequence[Edge]],
    by_pair: Mapping[Tuple[str, str], Sequence[Edge]],
) -> tuple[int, int]:
    _, grouped_edges = item
    return (
        sum(_count_triangle_completions(edge, adjacency, by_pair) for edge in grouped_edges),
        len(grouped_edges),
    )


def _round_robin_route_group_edges(edges: Sequence[Edge]) -> List[Edge]:
    """Interleave source-token/protocol families without changing their inner priority."""
    buckets: Dict[Tuple[str, str], List[Edge]] = {}
    for edge in edges:
        protocol = _edge_protocol_identity(edge) or str(edge.dex or "").strip().lower()
        key = (str(edge.token_in or "").strip().lower(), protocol)
        buckets.setdefault(key, []).append(edge)
    ordered: List[Edge] = []
    families = list(buckets.values())
    depth = 0
    while True:
        added = False
        for family in families:
            if depth < len(family):
                ordered.append(family[depth])
                added = True
        if not added:
            return ordered
        depth += 1


def _route_group_parallelism() -> int:
    """Bound concurrent route quote batches to protect provider rate limits."""
    try:
        requested = int(os.environ.get("VICTOR_ROUTE_GROUP_PARALLELISM", "3") or 3)
    except (TypeError, ValueError, OverflowError):
        requested = 3
    return max(1, min(4, requested))


def _first_leg_quote_budget_ms(time_budget_ms: int) -> int:
    """Reserve most of the shared scan window for route-group evaluation."""
    total_ms = max(1, int(time_budget_ms))
    if total_ms <= 1:
        return total_ms
    return max(1, min(total_ms - 1, (total_ms * 40) // 100))


def _consume_bounded_quote_result(
    result: Any,
    quote_map: Dict[str, Optional[Tuple[int, Dict[str, Any]]]],
) -> tuple[int, int]:
    """Accumulate a completed first-leg batch without hiding cancellation."""
    if isinstance(result, asyncio.CancelledError):
        raise result
    if isinstance(result, Exception):
        return 0, 1
    if isinstance(result, BaseException):
        raise result
    quote_map.update(dict(result or {}))
    return 1, 0


async def _wait_for_quote_tasks_until_deadline(
    tasks: Sequence[asyncio.Task],
    *,
    deadline: float,
) -> tuple[set, set]:
    """Wait only until the phase deadline and always drain unfinished tasks."""
    done: set = set()
    pending: set = set(tasks)
    try:
        remaining_s = max(0.0, deadline - time.perf_counter())
        done, pending = await asyncio.wait(
            tasks,
            timeout=remaining_s,
            return_when=asyncio.ALL_COMPLETED,
        )
    finally:
        unfinished = [task for task in tasks if not task.done()]
        for task in unfinished:
            task.cancel()
        if unfinished:
            await asyncio.gather(*unfinished, return_exceptions=True)
    return done, pending


def _consume_quote_task_results(
    tasks: Sequence[asyncio.Task],
    done: set,
    quote_map: Dict[str, Optional[Tuple[int, Dict[str, Any]]]],
) -> tuple[int, int]:
    """Retain finished results and count per-batch failures consistently."""
    completed = failed = 0
    for task in tasks:
        if task not in done:
            continue
        if task.cancelled():
            raise asyncio.CancelledError()
        task_error = task.exception()
        result = task.result() if task_error is None else task_error
        batch_completed, batch_failed = _consume_bounded_quote_result(result, quote_map)
        completed += batch_completed
        failed += batch_failed
    return completed, failed


async def _quote_edge_groups_in_bounded_waves(
    rpc: Any,
    cfg: Any,
    cache: PerBlockCache,
    edge_groups: Sequence[Tuple[int, List[Edge]]],
    *,
    deadline: float,
    block_number: int,
    parallelism: int,
    metrics: Dict[str, Any],
) -> tuple[Dict[str, Optional[Tuple[int, Dict[str, Any]]]], Dict[str, Any]]:
    """Quote prioritized amount groups under a hard phase deadline.

    Results from batches completed by the deadline are retained. In-flight
    batches are cancelled when the deadline expires and later waves are not
    started. The caller budgets this phase separately from route evaluation.
    Rotating the starting group by block prevents persistent starvation.
    """
    ordered = list(edge_groups)
    if ordered:
        offset = max(0, int(block_number)) % len(ordered)
        ordered = ordered[offset:] + ordered[:offset]
    limit = max(1, min(4, int(parallelism)))
    quote_map: Dict[str, Optional[Tuple[int, Dict[str, Any]]]] = {}
    completed = failed = skipped = waves = cancelled = 0
    recovered_after_cancellation = 0
    for wave_start in range(0, len(ordered), limit):
        if time.perf_counter() >= deadline:
            skipped = len(ordered) - wave_start
            break
        wave = ordered[wave_start:wave_start + limit]
        task_groups: Dict[asyncio.Task, Tuple[int, List[Edge]]] = {}
        tasks: List[asyncio.Task] = []
        for amount, edges in wave:
            task = asyncio.create_task(
                quote_edges_batch(rpc, cfg, cache, edges, int(amount), metrics=metrics)
            )
            tasks.append(task)
            task_groups[task] = (int(amount), list(edges))
        done, pending = await _wait_for_quote_tasks_until_deadline(
            tasks,
            deadline=deadline,
        )
        waves += 1
        batch_completed, batch_failed = _consume_quote_task_results(
            tasks,
            done,
            quote_map,
        )
        completed += batch_completed
        failed += batch_failed

        pending_count = len(pending)
        if pending_count:
            cancelled += pending_count
            # A cancelled quote_edges_batch can already have completed one or
            # more venue-family subcalls and written their valid outputs to the
            # block-scoped cache. Its coroutine cannot return the partially built
            # map after cancellation, so recover only successful cache entries
            # for the exact edge + notional. Missing/failed/in-flight quotes
            # remain absent and are never promoted to successes.
            for task in pending:
                amount, edges = task_groups[task]
                for edge in edges:
                    cache_key = _edge_quote_cache_key(edge, amount)
                    try:
                        cached = cache.get(cache_key)
                    except (AttributeError, KeyError, OSError, TypeError, ValueError):
                        cached = None
                    if cached is None:
                        continue
                    quote_map[edge_key(edge)] = cached
                    recovered_after_cancellation += 1

        next_start = wave_start + len(wave)
        if pending_count or (
            next_start < len(ordered) and time.perf_counter() >= deadline
        ):
            skipped = len(ordered) - next_start
            break

    deadline_exceeded = bool(
        cancelled or time.perf_counter() >= deadline or skipped
    )
    return quote_map, {
        "batches_total": int(len(ordered)),
        "batches_completed": int(completed),
        "batches_failed": int(failed),
        "batches_cancelled": int(cancelled),
        "batches_skipped_budget": int(skipped),
        "waves_started": int(waves),
        "parallelism_limit": int(limit),
        "partial_quote_edges_recovered_after_cancellation": int(recovered_after_cancellation),
        "deadline_exceeded": deadline_exceeded,
        "ordering": "route_potential_priority_then_block_rotated",
    }

async def _quote_two_leg_route_group_wave(
    rpc: Any,
    cfg: Any,
    cache: PerBlockCache,
    groups: Sequence[Mapping[str, Any]],
    *,
    metrics: Dict[str, Any],
    deadline: Optional[float] = None,
) -> tuple[List[Dict[str, Optional[Tuple[int, Dict[str, Any]]]]], int, int]:
    """Quote one route-group wave, coalescing identical amount/edge-set requests.

    When a deadline is supplied, requests use the same bounded scheduler as
    triangle final-leg work. Completed maps are retained and only exact cached
    successes are recovered after cancellation; no quote is synthesized.
    """
    requests = [(int(group["out1"]), list(group["revs"])) for group in groups]
    signatures: List[Tuple[int, Tuple[str, ...]]] = []
    unique_requests: Dict[Tuple[int, Tuple[str, ...]], Tuple[int, List[Edge]]] = {}
    for amount, edges in requests:
        signature = (amount, tuple(sorted(edge_key(edge) for edge in edges)))
        signatures.append(signature)
        unique_requests.setdefault(signature, (amount, edges))

    if deadline is None:
        unique_results = await asyncio.gather(*(
            quote_edges_batch(rpc, cfg, cache, edges, amount, metrics=metrics)
            for amount, edges in unique_requests.values()
        ))
        result_by_signature = dict(zip(unique_requests.keys(), unique_results))
        return (
            [result_by_signature[signature] for signature in signatures],
            len(unique_requests),
            len(requests) - len(unique_requests),
        )

    jobs = [
        (signature, amount, edges)
        for signature, (amount, edges) in unique_requests.items()
    ]
    result_by_signature, schedule = await _quote_edge_jobs_in_bounded_waves(
        rpc,
        cfg,
        cache,
        jobs,
        deadline=float(deadline),
        parallelism=_route_group_parallelism(),
        metrics=metrics,
    )
    return (
        [result_by_signature.get(signature, {}) for signature in signatures],
        int(schedule["batches_completed"]),
        max(0, len(requests) - len(unique_requests)),
    )


def _recover_cached_edge_quotes(
    cache: PerBlockCache,
    amount_in: int,
    edges: Sequence[Edge],
) -> Dict[str, Optional[Tuple[int, Dict[str, Any]]]]:
    """Recover valid quotes cached for this exact edge and input amount."""
    recovered: Dict[str, Optional[Tuple[int, Dict[str, Any]]]] = {}
    for edge in edges:
        try:
            cached = cache.get(_edge_quote_cache_key(edge, int(amount_in)))
        except (AttributeError, KeyError, OSError, TypeError, ValueError):
            continue
        if not isinstance(cached, tuple) or len(cached) < 2 or not isinstance(cached[1], dict):
            continue
        try:
            amount_out = int(cached[0])
        except (TypeError, ValueError, OverflowError):
            continue
        if amount_out > 0:
            recovered[edge_key(edge)] = (amount_out, dict(cached[1]))
    return recovered


def _recover_skipped_edge_jobs(
    jobs: Sequence[Tuple[Tuple[int, Tuple[str, ...]], int, List[Edge]]],
    cache: PerBlockCache,
    results: Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]],
) -> int:
    """Reuse exact-key cached quotes for skipped jobs without dispatching RPCs."""
    recovered_count = 0
    for signature, amount_in, edges in jobs:
        recovered = _recover_cached_edge_quotes(cache, amount_in, edges)
        if recovered:
            results[signature] = recovered
            recovered_count += len(recovered)
    return recovered_count


def _collect_quote_edge_job_results(
    tasks: Sequence[asyncio.Task],
    done: set,
    task_jobs: Mapping[asyncio.Task, Tuple[Tuple[int, Tuple[str, ...]], int, List[Edge]]],
    cache: PerBlockCache,
) -> Tuple[Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]], Dict[str, int]]:
    """Collect completed quote jobs, recovering only exact cached values after cancellation."""
    results: Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]] = {}
    completed = failed = cancelled = recovered = 0
    for task in tasks:
        if task not in done:
            continue
        signature, amount_in, edges = task_jobs[task]
        if task.cancelled():
            cancelled += 1
            partial = _recover_cached_edge_quotes(cache, amount_in, edges)
            if partial:
                results[signature] = partial
                recovered += len(partial)
            continue
        error = task.exception()
        if error is not None:
            if isinstance(error, _SAFE_EDGE_QUOTE_EXCEPTIONS):
                failed += 1
                continue
            raise error
        results[signature] = dict(task.result() or {})
        completed += 1
    return results, {
        "batches_completed": completed,
        "batches_failed": failed,
        "batches_cancelled": cancelled,
        "edges_recovered_after_cancellation": recovered,
    }


async def _quote_edge_job_wave(
    rpc: Any,
    cfg: Any,
    cache: PerBlockCache,
    wave: Sequence[Tuple[Tuple[int, Tuple[str, ...]], int, List[Edge]]],
    *,
    deadline: float,
    metrics: Dict[str, Any],
) -> Tuple[Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]], Dict[str, int]]:
    """Execute one bounded quote wave and account for drained/cancelled jobs."""
    tasks: List[asyncio.Task] = []
    task_jobs: Dict[asyncio.Task, Tuple[Tuple[int, Tuple[str, ...]], int, List[Edge]]] = {}
    for job in wave:
        signature, amount_in, edges = job
        task = asyncio.create_task(
            quote_edges_batch(rpc, cfg, cache, edges, int(amount_in), metrics=metrics)
        )
        tasks.append(task)
        task_jobs[task] = job

    done, pending = await _wait_for_quote_tasks_until_deadline(tasks, deadline=deadline)
    results, counts = _collect_quote_edge_job_results(tasks, done, task_jobs, cache)
    recovered_pending = 0
    for task in pending:
        signature, amount_in, edges = task_jobs[task]
        recovered = _recover_cached_edge_quotes(cache, amount_in, edges)
        if recovered:
            results[signature] = recovered
            recovered_pending += len(recovered)

    return results, {
        "batches_completed": counts["batches_completed"],
        "batches_failed": counts["batches_failed"],
        "batches_cancelled": counts["batches_cancelled"] + len(pending),
        "pending_batches": len(pending),
        "edges_recovered_after_cancellation": (
            counts["edges_recovered_after_cancellation"] + recovered_pending
        ),
    }


def _quote_job_wave_plan(
    cursor: int,
    total: int,
    *,
    deadline: float,
    parallelism: int,
    allow_one_after_deadline: bool,
    grace_used: bool,
) -> Tuple[int, float, bool, bool]:
    """Return wave size, wait deadline, grace state and skip decision."""
    remaining = max(0, int(total) - int(cursor))
    now = time.perf_counter()
    if remaining == 0:
        return 0, float(deadline), grace_used, True
    if now < deadline:
        return min(remaining, max(1, min(4, int(parallelism)))), deadline, grace_used, False
    if allow_one_after_deadline and not grace_used:
        return 1, now + 0.5, True, False
    return 0, float(deadline), grace_used, True


def _record_quote_job_schedule(
    metrics: Dict[str, Any],
    totals: Mapping[str, int],
    *,
    skipped: int,
    recovered_cancelled: int,
    recovered_skipped: int,
    waves: int,
    deadline: float,
) -> Dict[str, Any]:
    """Publish consistent bounded-wave counters and return one schedule snapshot."""
    metric_counts = {
        "route_group_quote_batches_completed": totals["completed"],
        "route_group_quote_batches_failed": totals["failed"],
        "route_group_quote_batches_cancelled": totals["cancelled"],
        "route_group_quote_batches_skipped_budget": skipped,
        "route_group_quote_waves_started": waves,
        "route_group_quote_edges_recovered_after_cancellation": recovered_cancelled,
        "route_group_quote_edges_recovered_from_cache_when_skipped": recovered_skipped,
    }
    for key, count in metric_counts.items():
        metrics[key] = max(0, int(metrics.get(key, 0) or 0)) + max(0, int(count))
    cancelled = totals["cancelled"]
    deadline_exceeded = bool(cancelled or skipped or time.perf_counter() >= deadline)
    return {
        "batches_total": int(totals["total"]),
        "batches_completed": int(totals["completed"]),
        "batches_failed": int(totals["failed"]),
        "batches_cancelled": int(cancelled),
        "batches_skipped_budget": int(skipped),
        "waves_started": int(waves),
        "parallelism_limit": int(totals["parallelism"]),
        "partial_quote_edges_recovered_after_cancellation": int(recovered_cancelled),
        "edges_recovered_from_cache_when_skipped": int(recovered_skipped),
        "deadline_exceeded": deadline_exceeded,
    }


async def _quote_edge_jobs_in_bounded_waves(
    rpc: Any,
    cfg: Any,
    cache: PerBlockCache,
    jobs: Sequence[Tuple[Tuple[int, Tuple[str, ...]], int, List[Edge]]],
    *,
    deadline: float,
    parallelism: int,
    metrics: Dict[str, Any],
    allow_one_after_deadline: bool = False,
) -> tuple[Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]], Dict[str, Any]]:
    """Quote unique jobs in bounded waves; optionally finish one funded final-leg batch."""
    ordered = list(jobs)
    limit = max(1, min(4, int(parallelism)))
    results: Dict[Tuple[int, Tuple[str, ...]], Dict[str, Optional[Tuple[int, Dict[str, Any]]]]] = {}
    totals = {"total": len(ordered), "parallelism": limit, "completed": 0, "failed": 0, "cancelled": 0}
    skipped = recovered_cancelled = recovered_skipped = waves = cursor = 0
    grace_used = False

    while cursor < len(ordered):
        wave_size, wait_deadline, grace_used, stop = _quote_job_wave_plan(
            cursor, len(ordered), deadline=deadline, parallelism=limit,
            allow_one_after_deadline=allow_one_after_deadline, grace_used=grace_used,
        )
        if stop:
            remaining = ordered[cursor:]
            skipped += len(remaining)
            recovered_skipped += _recover_skipped_edge_jobs(remaining, cache, results)
            break

        wave = ordered[cursor:cursor + wave_size]
        wave_results, counts = await _quote_edge_job_wave(
            rpc, cfg, cache, wave, deadline=wait_deadline, metrics=metrics
        )
        waves += 1
        results.update(wave_results)
        for key in ("completed", "failed", "cancelled"):
            totals[key] += counts["batches_" + key]
        recovered_cancelled += counts["edges_recovered_after_cancellation"]
        cursor += len(wave)

        if counts["pending_batches"]:
            remaining = ordered[cursor:]
            skipped += len(remaining)
            recovered_skipped += _recover_skipped_edge_jobs(remaining, cache, results)
            break

    schedule = _record_quote_job_schedule(
        metrics, totals, skipped=skipped, recovered_cancelled=recovered_cancelled,
        recovered_skipped=recovered_skipped, waves=waves, deadline=deadline,
    )
    return results, schedule


@dataclass
class _TwoLegRouteProcessingContext:
    cfg: Any
    block_number: int
    slippage_bps: int
    observed_gas_price_wei: Optional[int]
    metrics: Dict[str, Any]
    opportunities: List[Opportunity]


def _route_aux_for_edge(edge: Edge, meta: Mapping[str, Any]) -> str:
    if edge.dex == "univ3":
        return aux_univ3_fee(int(meta.get("fee", edge.params.get("fee", 3000))))
    if edge.dex == "curve":
        return aux_curve_from_meta(dict(meta), edge.params)
    if edge.dex == "balancer":
        return str(edge.params.get("pool_id") or "0x")
    if edge.dex == "aerodrome":
        raw = int(str(edge.params.get("factory") or "0"), 16)
        raw |= (1 if bool(edge.params.get("stable", False)) else 0) << 160
        return _aux_u256_to_b32_hex(raw)
    if edge.dex == "slipstream":
        return _aux_u256_to_b32_hex(int(edge.params.get("tick_spacing", 0)) & 0xFFFFFF)
    if edge.dex == "camelot_algebra":
        return "0x"
    if edge.dex in {"camelot_v2", "constant_product"}:
        return _aux_u256_to_b32_hex(int(str(edge.params.get("factory") or "0"), 16))
    return "0x"


@dataclass(frozen=True)
class _TwoLegCandidateFacts:
    group: Mapping[str, Any]
    edge: Edge
    amount_out: int
    meta: Dict[str, Any]
    gross_profit: int
    min_out_first: int
    min_out_final: int
    aux_first: str
    aux_second: str
    route_id: str


def _record_non_positive_two_leg(
    context: _TwoLegRouteProcessingContext,
    facts: _TwoLegCandidateFacts,
) -> bool:
    if facts.gross_profit > 0 or os.environ.get("VICTOR_DEBUG_OPPS", "").strip() == "1":
        return False
    group, e2, meta2 = facts.group, facts.edge, facts.meta
    e1 = group["e1"]
    amount_in = int(group["effective_amount_in"])
    out1 = int(group["out1"])
    meta1 = group["meta1"]
    gas_cost = int(estimate_gas_cost_wei_from_cfg(
        context.cfg,
        estimate_route_gas_units({"leg1": meta1, "leg2": meta2, "venues": [e1.dex, e2.dex]}),
        observed_gas_price_wei=context.observed_gas_price_wei,
    ))
    flashloan_fee = (
        amount_in * int(getattr(getattr(context.cfg, "execution", None), "flashloan_fee_bps", 0) or 0)
    ) // 10_000
    _record_size_economic_diagnostic(
        context.metrics,
        route_id=facts.route_id,
        amount_in=amount_in,
        gross_profit_wei=int(facts.gross_profit),
        flashloan_fee_wei=int(flashloan_fee),
        gas_cost_wei=int(gas_cost),
        reason="non_positive_gross_profit",
        legs=[
            {"dex": str(e1.dex), "venue": str(e1.venue), "token_in": str(e1.token_in), "token_out": str(e1.token_out), "fee": int(meta1.get("fee", e1.params.get("fee", 0) or 0)), "pool": str(e1.params.get("pool") or e1.venue), "amount_in": str(amount_in), "quoted_amount_out": str(out1), "min_out": str(facts.min_out_first), "slippage_reserve": str(max(0, out1 - facts.min_out_first)), "quote_meta": dict(meta1), "edge_params": dict(e1.params), "data": str(facts.aux_first)},
            {"dex": str(e2.dex), "venue": str(e2.venue), "token_in": str(e2.token_in), "token_out": str(e2.token_out), "fee": int(meta2.get("fee", e2.params.get("fee", 0) or 0)), "pool": str(e2.params.get("pool") or e2.venue), "amount_in": str(out1), "quoted_amount_out": str(facts.amount_out), "min_out": str(facts.min_out_final), "slippage_reserve": str(max(0, facts.amount_out - facts.min_out_final)), "quote_meta": dict(meta2), "edge_params": dict(e2.params), "data": str(facts.aux_second)},
        ],
    )
    context.metrics["route_rejections_non_positive_gross_profit"] = int(
        context.metrics.get("route_rejections_non_positive_gross_profit", 0)
    ) + 1
    return True


def _append_two_leg_opportunity(
    context: _TwoLegRouteProcessingContext,
    facts: _TwoLegCandidateFacts,
) -> None:
    cfg = context.cfg
    group, e2 = facts.group, facts.edge
    e1 = group["e1"]
    amount_in = int(group["effective_amount_in"])
    out1 = int(group["out1"])
    meta1, meta2 = group["meta1"], facts.meta
    venues = [e1.dex, e2.dex]
    route_meta = {"leg1": meta1, "leg2": meta2, "venues": venues}
    gas_units = estimate_route_gas_units(route_meta)
    gas_cost = estimate_gas_cost_wei_from_cfg(
        cfg, gas_units, observed_gas_price_wei=context.observed_gas_price_wei
    )
    pool_keys = [
        _pool_keys_for_leg(
            e1.dex, e1.token_in, e1.token_out,
            {"fee": meta1.get("fee", e1.params.get("fee", 3000)), "pool": e1.venue, **e1.params},
            facts.aux_first,
        ),
        _pool_keys_for_leg(
            e2.dex, e2.token_in, e2.token_out,
            {"fee": meta2.get("fee", e2.params.get("fee", 3000)), "pool": e2.venue, **e2.params},
            facts.aux_second,
        ),
    ]
    opportunity_id = _id([
        cfg.chain.name, "2leg", facts.route_id, str(amount_in), str(context.block_number)
    ])
    context.opportunities.append(
        Opportunity(
            id=opportunity_id,
            chain=cfg.chain.name,
            strategy=f"two-leg:{e1.dex}->{e2.dex}",
            expected_profit_raw=str(facts.gross_profit),
            expected_profit_usd="0",
            route=Route(legs=[
                RouteLeg(
                    dex=e1.dex, venue=e1.venue, token_in=e1.token_in, token_out=e1.token_out,
                    amount_in=str(amount_in), min_out=str(facts.min_out_first), data=facts.aux_first,
                ),
                RouteLeg(
                    dex=e2.dex, venue=e2.venue, token_in=e2.token_in, token_out=e2.token_out,
                    amount_in=str(out1), min_out=str(facts.min_out_final), data=facts.aux_second,
                ),
            ]),
            min_outs=[str(facts.min_out_first), str(facts.min_out_final)],
            route_id=facts.route_id,
            can_execute=False,
            created_at_ms=_now_ms(),
            meta={
                "out1": str(out1),
                "out2": str(facts.amount_out),
                "leg1": meta1,
                "leg2": meta2,
                "route_type": "2leg",
                "route_edge_params": [dict(e1.params), dict(e2.params)],
                "route_family": _classify_route_family(cfg, [e1, e2], route_type="2leg"),
                "venues": venues,
                "pool_keys": pool_keys,
                "gas_estimate_units": str(gas_units),
                "gas_cost_estimate_wei": str(gas_cost),
                "profit_after_gas_estimate_wei": str(int(facts.gross_profit) - int(gas_cost)),
            },
        )
    )


def _consume_two_leg_quote_result(
    context: _TwoLegRouteProcessingContext,
    group: Mapping[str, Any],
    e2: Edge,
    qmap2: Mapping[str, Optional[Tuple[int, Dict[str, Any]]]],
) -> None:
    """Turn a completed quote into diagnostic or gross opportunity evidence."""
    cfg = context.cfg
    block_number = context.block_number
    slippage_bps = context.slippage_bps
    observed_gas_price_wei = context.observed_gas_price_wei
    metrics = context.metrics
    opps = context.opportunities
    e1 = group["e1"]
    effective_amount_in = int(group["effective_amount_in"])
    out1 = int(group["out1"])
    meta1 = group["meta1"]
    q2 = qmap2.get(edge_key(e2))
    if not q2:
        metrics["route_rejections_second_leg_quote_unavailable"] = int(metrics.get("route_rejections_second_leg_quote_unavailable", 0)) + 1
        return
    out2, meta2 = q2
    gross_profit = out2 - effective_amount_in
    # min_outs for legs include slippage haircut
    min1 = _apply_slippage(out1, slippage_bps)
    min2 = _apply_slippage(out2, slippage_bps)
        
    aux1 = _route_aux_for_edge(e1, meta1)
    aux2 = _route_aux_for_edge(e2, meta2)

    rid = route_id_hex(
        [
            EncLeg(
                dex=e1.dex,
                venue=e1.venue,
                token_in=e1.token_in,
                token_out=e1.token_out,
                aux=aux1,
            ),
            EncLeg(
                dex=e2.dex,
                venue=e2.venue,
                token_in=e2.token_in,
                token_out=e2.token_out,
                aux=aux2,
            ),
        ]
    )
        
    facts = _TwoLegCandidateFacts(
        group=group,
        edge=e2,
        amount_out=int(out2),
        meta=dict(meta2),
        gross_profit=int(gross_profit),
        min_out_first=int(min1),
        min_out_final=int(min2),
        aux_first=aux1,
        aux_second=aux2,
        route_id=rid,
    )
    if _record_non_positive_two_leg(context, facts):
        return
    _append_two_leg_opportunity(context, facts)




async def find_two_leg_opportunities(
    rpc,
    cfg,
    cache: PerBlockCache,
    block_number: int,
    *,
    amount_in: int,
    slippage_bps: int,
    time_budget_ms: int = 2000,
    max_opps: int = 50,
    telemetry: Optional[Dict[str, Any]] = None,
    max_reverse_candidates: Optional[int] = None,
    extra_v3_pairs: Optional[List[dict]] = None,
    extra_curve_pools: Optional[List[dict]] = None,
    extra_balancer_pools: Optional[List[dict]] = None,
    extra_aerodrome_pools: Optional[List[dict]] = None,
    extra_slipstream_pools: Optional[List[dict]] = None,
    extra_camelot_algebra_pools: Optional[List[dict]] = None,
    extra_camelot_v2_pools: Optional[List[dict]] = None,
    extra_constant_product_pools: Optional[List[dict]] = None,
    amount_in_by_token: Optional[Dict[str, int]] = None,
    observed_gas_price_wei: Optional[int] = None,
    pool_event_cache: Any = None,
    max_scan_edges: Optional[int] = None,
) -> List[Opportunity]:
    t_start = time.perf_counter()
    route_deadline = t_start + max(1, int(time_budget_ms)) / 1000.0
    first_leg_quote_budget_ms = _first_leg_quote_budget_ms(time_budget_ms)
    first_leg_quote_deadline = min(
        route_deadline, t_start + first_leg_quote_budget_ms / 1000.0
    )
    metrics: Dict[str, int] = {}
    edge_build_diagnostics: Dict[str, Any] = {}
    edges = build_edges(
        cfg,
        extra_v3_pairs=extra_v3_pairs,
        extra_curve_pools=extra_curve_pools,
        extra_balancer_pools=extra_balancer_pools,
        extra_aerodrome_pools=extra_aerodrome_pools,
        extra_slipstream_pools=extra_slipstream_pools,
        extra_camelot_algebra_pools=extra_camelot_algebra_pools,
        extra_camelot_v2_pools=extra_camelot_v2_pools,
        extra_constant_product_pools=extra_constant_product_pools,
        diagnostics=edge_build_diagnostics,
    )
    pool_event_metrics: Dict[str, Any] = {}
    if pool_event_cache is not None:
        try:
            full_edge_count = len(edges)
            pool_event_cache.refresh_edges(
                edges,
                balancer_vault=str(getattr(cfg.chain, "balancer_vault", "") or ""),
            )
            edges, pool_event_metrics = pool_event_cache.candidate_edges(
                edges,
                current_block=int(block_number),
                max_candidates=int(
                    os.environ.get("VICTOR_EVENT_CANDIDATE_MAX", "768") or 768
                ),
                exploration_ratio=float(
                    os.environ.get("VICTOR_EVENT_EXPLORATION_RATIO", "0.10") or 0.10
                ),
            )
            pool_event_metrics["full_edge_count"] = int(full_edge_count)
        except (AttributeError, TypeError, ValueError):
            pool_event_metrics = {}
    edges = _apply_scan_edge_cap(edges, max_scan_edges, metrics)
    # Route evaluation must retain the immutable route universe even when the
    # selected-provider full scan feeds this function only one bounded edge slice.
    # Otherwise a reverse leg in another slice disappears and a valid cross-pool
    # two-leg route is structurally invisible.
    route_edges = list(edges)
    route_universe_edges_fn = getattr(pool_event_cache, "route_universe_edges", None)
    if callable(route_universe_edges_fn):
        try:
            candidate_route_edges = list(route_universe_edges_fn() or [])
            if candidate_route_edges:
                route_edges = candidate_route_edges
        except (AttributeError, TypeError, ValueError):
            route_edges = list(edges)
    by_pair: Dict[Tuple[str, str], List[Edge]] = {}
    route_universe = _route_universe_snapshot(
        cfg, route_edges, edge_build_diagnostics=edge_build_diagnostics
    )
    for e in route_edges:
        by_pair.setdefault((e.token_in, e.token_out), []).append(e)

    opps: List[Opportunity] = []
    # Batch quote all first-leg edges at base amount (biggest ROI speedup).
    # Quote acquisition can legitimately exceed the route-evaluation budget on a
    # slow provider. The old wall-clock check immediately after this await could
    # therefore discard every route before considering even one successful quote.
    quote_phase_started = time.perf_counter()
    normalized_amounts = {
        str(token).lower(): max(1, int(value))
        for token, value in dict(amount_in_by_token or {}).items()
        if str(token) and int(value) > 0
    }
    edge_groups: Dict[int, List[Edge]] = {}
    for edge in edges:
        effective_amount = int(normalized_amounts.get(str(edge.token_in).lower(), int(amount_in)))
        edge_groups.setdefault(effective_amount, []).append(edge)
    configured_reverse_candidates = (
        max_reverse_candidates
        if max_reverse_candidates not in (None, "")
        else int(os.environ.get("VICTOR_MAX_REVERSE_CANDIDATES", "8") or 8)
    )
    max_reverse_candidates = max(
        3,
        min(12, int(configured_reverse_candidates)),
    )
    ordered_edge_groups = sorted(
        edge_groups.items(),
        key=lambda item: (
            sum(len(by_pair.get((edge.token_out, edge.token_in), [])) for edge in item[1]),
            len(item[1]),
        ),
        reverse=True,
    )
    qmap1, first_leg_quote_schedule = await _quote_edge_groups_in_bounded_waves(
        rpc,
        cfg,
        cache,
        ordered_edge_groups,
        deadline=first_leg_quote_deadline,
        block_number=int(block_number),
        parallelism=_route_group_parallelism(),
        metrics=metrics,
    )
    route_eval_started = time.perf_counter()
    route_groups_evaluated = 0
    route_budget_exhausted = bool(time.perf_counter() >= route_deadline)
    prepared_route_groups: List[Dict[str, Any]] = []
    # Interleave token/protocol families before budgeting. This is only a
    # scheduling fairness policy; route economics still determine ranking.
    for e1 in _round_robin_route_group_edges(edges):
        if time.perf_counter() >= route_deadline:
            route_budget_exhausted = True
            break
        revs = by_pair.get((e1.token_out, e1.token_in), [])
        if not revs:
            metrics["route_rejections_no_reverse_route"] = int(metrics.get("route_rejections_no_reverse_route", 0)) + 1
            continue

        filtered_revs = [
            e2 for e2 in revs if not _is_same_pool_roundtrip(e1, e2)
        ]
        skipped_same_pool = len(revs) - len(filtered_revs)
        if skipped_same_pool:
            metrics["route_rejections_same_pool_roundtrip"] = int(
                metrics.get("route_rejections_same_pool_roundtrip", 0)
            ) + int(skipped_same_pool)
        revs = filtered_revs
        if not revs:
            continue
        metrics["candidate_count"] = int(metrics.get("candidate_count", 0)) + len(revs)
        revs, reverse_prefilter = _prefilter_reverse_candidates(
            revs,
            qmap1=qmap1,
            max_candidates=max_reverse_candidates,
            pool_event_cache=pool_event_cache,
            current_block=int(block_number),
        )
        metrics["reverse_candidates_total"] = int(
            metrics.get("reverse_candidates_total", 0)
        ) + int(reverse_prefilter["total"])
        metrics["reverse_candidates_selected"] = int(
            metrics.get("reverse_candidates_selected", 0)
        ) + int(reverse_prefilter["selected"])
        metrics["reverse_candidates_filtered"] = int(
            metrics.get("reverse_candidates_filtered", 0)
        ) + int(reverse_prefilter["filtered"])
        if normalized_amounts:
            effective_amount_in = int(normalized_amounts.get(str(e1.token_in).lower(), 0))
            if effective_amount_in <= 0:
                metrics["route_rejections_input_notional_unavailable"] = int(
                    metrics.get("route_rejections_input_notional_unavailable", 0)
                ) + 1
                continue
        else:
            effective_amount_in = int(amount_in)
        q1 = qmap1.get(edge_key(e1))
        if not q1:
            metrics["route_rejections_first_leg_quote_unavailable"] = int(metrics.get("route_rejections_first_leg_quote_unavailable", 0)) + 1
            continue
        out1, meta1 = q1
        prepared_route_groups.append({
            "e1": e1,
            "revs": revs,
            "effective_amount_in": effective_amount_in,
            "out1": out1,
            "meta1": meta1,
        })

    route_group_parallelism = _route_group_parallelism()
    route_quote_waves_started = 0
    completed_route_quote_batches = 0
    coalesced_route_quote_batches = 0
    processing_context = _TwoLegRouteProcessingContext(
        cfg=cfg,
        block_number=int(block_number),
        slippage_bps=int(slippage_bps),
        observed_gas_price_wei=observed_gas_price_wei,
        metrics=metrics,
        opportunities=opps,
    )
    for wave_start in range(0, len(prepared_route_groups), route_group_parallelism):
        if time.perf_counter() >= route_deadline:
            route_budget_exhausted = True
            break
        wave = prepared_route_groups[wave_start:wave_start + route_group_parallelism]
        qmaps2, physical_batches, coalesced_batches = await _quote_two_leg_route_group_wave(
            rpc, cfg, cache, wave, metrics=metrics, deadline=route_deadline
        )
        route_quote_waves_started += 1
        completed_route_quote_batches += int(physical_batches)
        coalesced_route_quote_batches += int(coalesced_batches)
        for group, qmap2 in zip(wave, qmaps2):
            route_groups_evaluated += 1
            for e2 in group["revs"]:
                _consume_two_leg_quote_result(processing_context, group, e2, qmap2)

        if (
            wave_start + route_group_parallelism < len(prepared_route_groups)
            and time.perf_counter() >= route_deadline
        ):
            route_budget_exhausted = True
            break
    if route_groups_evaluated < len(prepared_route_groups) or time.perf_counter() >= route_deadline:
        route_budget_exhausted = True
    _finalize_quote_coverage(metrics)
    if telemetry is not None:
        telemetry["quote_phase_ms"] = float(
            (route_eval_started - quote_phase_started) * 1000.0
        )
        telemetry["route_evaluation_ms"] = float(
            (time.perf_counter() - route_eval_started) * 1000.0
        )
        telemetry["route_budget_elapsed_ms"] = float(
            (time.perf_counter() - t_start) * 1000.0
        )
        telemetry["route_budget_deadline_ms"] = int(max(1, int(time_budget_ms)))
        telemetry["route_groups_evaluated"] = int(route_groups_evaluated)
        telemetry["route_group_schedule"] = {
            "block_number": int(block_number),
            "groups_prepared": len(prepared_route_groups),
            "groups_completed": int(route_groups_evaluated),
            "quote_batches_completed_and_consumed": int(
                first_leg_quote_schedule["batches_completed"]
                + completed_route_quote_batches
            ),
            "first_leg_quote_batches_total": int(first_leg_quote_schedule["batches_total"]),
            "first_leg_quote_batches_completed": int(first_leg_quote_schedule["batches_completed"]),
            "first_leg_quote_batches_failed": int(first_leg_quote_schedule["batches_failed"]),
            "first_leg_quote_batches_cancelled": int(first_leg_quote_schedule["batches_cancelled"]),
            "first_leg_quote_batches_skipped_budget": int(first_leg_quote_schedule["batches_skipped_budget"]),
            "first_leg_quote_edges_recovered_after_cancellation": int(
                first_leg_quote_schedule.get("partial_quote_edges_recovered_after_cancellation", 0)
            ),
            "first_leg_quote_budget_ms": int(first_leg_quote_budget_ms),
            "first_leg_quote_budget_exhausted": bool(first_leg_quote_schedule["deadline_exceeded"]),
            "first_leg_quote_waves_started": int(first_leg_quote_schedule["waves_started"]),
            "first_leg_quote_parallelism_limit": int(first_leg_quote_schedule["parallelism_limit"]),
            "first_leg_deadline_exceeded": bool(first_leg_quote_schedule["deadline_exceeded"]),
            "first_leg_quote_ordering": str(first_leg_quote_schedule["ordering"]),
            "route_group_quote_batches_completed_and_consumed": int(completed_route_quote_batches),
            "route_group_quote_batches_failed": int(metrics.get("route_group_quote_batches_failed", 0) or 0),
            "route_group_quote_batches_cancelled": int(metrics.get("route_group_quote_batches_cancelled", 0) or 0),
            "route_group_quote_batches_skipped_budget": int(metrics.get("route_group_quote_batches_skipped_budget", 0) or 0),
            "route_group_quote_edges_recovered_after_cancellation": int(metrics.get("route_group_quote_edges_recovered_after_cancellation", 0) or 0),
            "route_group_quote_edges_recovered_from_cache_when_skipped": int(metrics.get("route_group_quote_edges_recovered_from_cache_when_skipped", 0) or 0),
            "route_group_quote_waves_started": int(metrics.get("route_group_quote_waves_started", 0) or 0),
            "route_group_waves_started": int(route_quote_waves_started),
            "duplicate_quote_batches_coalesced": int(coalesced_route_quote_batches),
            "parallelism_limit": int(route_group_parallelism),
            "waves_started": int(route_quote_waves_started),
            "ordering": "round_robin_source_token_protocol",
            "completed_wave_results_consumed_before_budget_stop": True,
        }
        telemetry["first_leg_quote_budget_ms"] = int(first_leg_quote_budget_ms)
        telemetry["first_leg_quote_budget_exhausted"] = bool(first_leg_quote_schedule["deadline_exceeded"])
        telemetry["first_leg_quote_batches_cancelled"] = int(first_leg_quote_schedule["batches_cancelled"])
        telemetry["route_budget_exhausted"] = bool(route_budget_exhausted)
        telemetry["route_budget_stop_reason"] = (
            "time_budget" if route_budget_exhausted else "completed"
        )
        telemetry["budget_exhausted_after_quote"] = bool(route_budget_exhausted)

    snapshot = scan_efficiency_snapshot(
        elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
        candidate_count=int(metrics.get("candidate_count", 0)),
        quote_requests=int(metrics.get("quote_requests", 0)),
        quote_successes=int(metrics.get("quote_successes", 0)),
        opportunity_count=len(opps),
        cache_hits=int(metrics.get("cache_hits", 0)),
        network_batches=int(metrics.get("network_batches", 0)),
    )
    for opportunity in opps:
        opportunity.meta["scan_efficiency"] = dict(snapshot)
    if telemetry is not None:
        telemetry.update({
            "elapsed_ms": float(snapshot["elapsed_ms"]),
            "candidate_count": int(snapshot["candidate_count"]),
            "quote_requests": int(snapshot["quote_requests"]),
            "quote_successes": int(snapshot["quote_successes"]),
            "quote_cancelled": int(metrics.get("quote_cancelled", 0) or 0),
            "quote_success_rate": float(snapshot["quote_success_rate"]),
            "cache_hits": int(snapshot["cache_hits"]),
            "network_batches": int(snapshot["network_batches"]),
            "routes_considered": int(snapshot["candidate_count"]),
            "edges_generated": len(edges),
            "route_universe": dict(route_universe),
            "gross_candidates": len(opps),
            "opportunity_count": len(opps),
            "quote_failure_reasons": dict(metrics.get("quote_failure_reasons") or {}),
            **_quote_family_metric_snapshot(metrics),
            **_quote_failure_reason_snapshot(metrics),
            "quote_fallback_attempts": int(metrics.get("quote_fallback_attempts", 0)),
            "quote_fallback_successes": int(metrics.get("quote_fallback_successes", 0)),
            "route_rejections": {
                str(k).replace("route_rejections_", ""): int(v)
                for k, v in metrics.items()
                if str(k).startswith("route_rejections_")
            },
            "size_economic_diagnostics": list(metrics.get("size_economic_diagnostics") or []),
            "reverse_leg_prefilter": {
                "max_candidates": int(max_reverse_candidates),
                "total": int(metrics.get("reverse_candidates_total", 0)),
                "selected": int(metrics.get("reverse_candidates_selected", 0)),
                "filtered": int(metrics.get("reverse_candidates_filtered", 0)),
            },
            "pool_event_state": dict(pool_event_metrics or {}),
            "scan_edges_before_cap": int(metrics.get("scan_edges_before_cap", len(edges))),
            "route_universe_edge_count": int(len(route_edges)),
            "scan_edge_cap": (
                int(metrics["scan_edge_cap"])
                if metrics.get("scan_edge_cap") not in (None, "")
                else None
            ),
            "scan_edges_selected": int(metrics.get("scan_edges_selected", len(edges))),
            "scan_edges_capped": int(metrics.get("scan_edges_capped", 0)),
        })
    # Rank completed routes by signed after-cost economics before gross
    # fallback. Validation authority remains a downstream execution gate.
    opps.sort(key=_opportunity_economic_sort_key, reverse=True)
    return opps[: max(1, int(max_opps))]


def _profitability_state(meta: Mapping[str, Any]) -> Dict[str, Any]:
    state = meta.get("profitability")
    if not isinstance(state, dict):
        state = meta.get("profitability_diagnostic")
    return state if isinstance(state, dict) else {}


def _canonical_after_cost_usd_micro(meta: Mapping[str, Any]) -> int | None:
    canonical = meta.get("canonical_after_fee_usd")
    if not isinstance(canonical, dict):
        return None
    try:
        raw = canonical.get("profit_after_costs_usd_micro")
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError, OverflowError):
        return None


def _raw_signed_economic_profit(
    opportunity: Opportunity,
    meta: Mapping[str, Any],
    state: Mapping[str, Any],
) -> int | None:
    economic = None
    for key in (
        "economic_profit_after_costs_wei",
        "economic_after_cost_profit_wei",
        "profit_after_costs_wei",
        "after_cost_profit_wei",
    ):
        raw = state.get(key, meta.get(key))
        if raw not in (None, ""):
            try:
                economic = int(raw)
                break
            except (TypeError, ValueError, OverflowError):
                continue
    if economic != -1 or str(state.get("reason") or "") != "does_not_repay_flashloan":
        return economic
    gas_token = state.get("gas_cost_profit_token_wei")
    if gas_token in (None, ""):
        return None
    try:
        gross_raw = state.get("gross_profit_wei")
        gross = (
            int(gross_raw)
            if gross_raw not in (None, "")
            else int(getattr(opportunity, "expected_profit_raw", 0) or 0)
        )
        return gross - int(state.get("flashloan_fee_wei") or 0) - int(gas_token)
    except (TypeError, ValueError, OverflowError):
        return None


def _route_borrow_token(opportunity: Opportunity, meta: Mapping[str, Any]) -> str:
    route = getattr(opportunity, "route", None)
    legs = list(getattr(route, "legs", []) or [])
    first_token = getattr(legs[0], "token_in", "") if legs else ""
    return str(first_token or meta.get("borrow_token") or "").strip().lower()


def _route_gross_profit(opportunity: Opportunity) -> int:
    try:
        return int(getattr(opportunity, "expected_profit_raw", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _authoritative_positive(state: Mapping[str, Any], profit: int | None) -> bool:
    return bool(
        state.get("revalidated") is True
        and state.get("authoritative") is True
        and state.get("valid") is True
        and state.get("repayment_valid") is True
        and profit is not None
        and profit > 0
    )


def _opportunity_economic_sort_key(
    opportunity: Opportunity,
) -> tuple[int, int, str, int, int, int, str]:
    """Rank by comparable USD net value, otherwise by token-local signed net."""
    meta_value = getattr(opportunity, "meta", {}) or {}
    meta = meta_value if isinstance(meta_value, dict) else {}
    state = _profitability_state(meta)
    usd_micro = _canonical_after_cost_usd_micro(meta)
    economic = _raw_signed_economic_profit(opportunity, meta, state)
    borrow_token = _route_borrow_token(opportunity, meta)
    gross = _route_gross_profit(opportunity)
    verified_usd = usd_micro is not None and _authoritative_positive(state, usd_micro)
    route_id = str(
        getattr(opportunity, "route_id", "") or getattr(opportunity, "id", "") or ""
    )
    if usd_micro is not None:
        return (1, usd_micro, "", 0, int(verified_usd), 0, route_id)
    return (
        0,
        0,
        borrow_token,
        int(economic or 0),
        int(_authoritative_positive(state, economic)),
        gross,
        route_id,
    )


def _prioritize_three_leg_adjacency(
    edges: List[Edge],
    *,
    max_edges_per_token: int,
) -> tuple[Dict[str, List[Edge]], List[Edge]]:
    """Bound triangle adjacency without letting discovery order hide cycles."""
    by_pair: Dict[Tuple[str, str], List[Edge]] = {}
    full_adj: Dict[str, List[Edge]] = {}
    for edge in edges:
        by_pair.setdefault((edge.token_in, edge.token_out), []).append(edge)
        full_adj.setdefault(edge.token_in, []).append(edge)

    cap = max(1, int(max_edges_per_token))
    active_edge_ids: set[int] = set()
    adj: Dict[str, List[Edge]] = {}
    for token_in, original in full_adj.items():
        scored: List[Tuple[int, int, Edge]] = []
        for order, edge in enumerate(original):
            direct_reverse = bool(by_pair.get((edge.token_out, edge.token_in)))
            triangle_close = False
            for middle in full_adj.get(edge.token_out, []):
                if middle.token_out == edge.token_in:
                    continue
                if by_pair.get((middle.token_out, edge.token_in)):
                    triangle_close = True
                    break
            score = 3 if direct_reverse else (2 if triangle_close else 1)
            scored.append((score, order, edge))
        scored.sort(key=lambda item: (-item[0], item[1]))
        kept = [item[2] for item in scored[:cap]]
        adj[token_in] = kept
        active_edge_ids.update(id(edge) for edge in kept)
    pruned = [edge for edge in edges if id(edge) not in active_edge_ids]
    return adj, pruned




def _build_three_leg_frontier(
    edges: Sequence[Edge],
    pruned_edges: Sequence[Edge],
    adj: Mapping[str, Sequence[Edge]],
    by_pair: Mapping[Tuple[str, str], Sequence[Edge]],
    first_leg_quotes: Mapping[str, Optional[Tuple[int, Dict[str, Any]]]],
    *,
    telemetry: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Edge]]:
    # Adaptive frontier: first-leg quotes have already been acquired for the
    # complete graph. Use a small supplemental budget to admit pruned edges only
    # when they are quote-viable, can close a triangle in the full graph, and add
    # venue diversity. The original per-token adjacency cap remains unchanged;
    # the frontier has its own hard global/per-token bounds.
    frontier_per_token = max(
        1,
        min(
            2,
            int(os.environ.get("VICTOR_THREE_LEG_FRONTIER_PER_TOKEN", "2") or 2),
        ),
    )
    frontier_global = max(
        0,
        min(
            32,
            int(os.environ.get("VICTOR_THREE_LEG_FRONTIER_MAX_EDGES", "24") or 24),
        ),
    )
    frontier_by_token: Dict[str, List[Edge]] = {}
    frontier_selected: List[Edge] = []
    active_venues_by_token = {
        token: {str(edge.venue).strip().lower() for edge in items if str(edge.venue or "").strip()}
        for token, items in adj.items()
    }
    active_protocols_by_token = {
        token: {
            protocol
            for edge in items
            if (protocol := _edge_protocol_identity(edge)) is not None
        }
        for token, items in adj.items()
    }
    active_pools_by_token = {
        token: {
            pool
            for edge in items
            if (pool := _edge_pool_identity(edge)) is not None
        }
        for token, items in adj.items()
    }
    active_routers_by_token = {
        token: {
            router
            for edge in items
            if (router := _edge_router_identity(edge)) is not None
        }
        for token, items in adj.items()
    }
    frontier_candidates: List[Tuple[int, Edge]] = []
    for order, edge in enumerate(pruned_edges):
        if not first_leg_quotes.get(edge_key(edge)):
            continue
        closes = any(
            bool(by_pair.get((middle.token_out, edge.token_in)))
            for middle in edges
            if middle.token_in == edge.token_out and middle.token_out != edge.token_in
        )
        if closes:
            frontier_candidates.append((order, edge))

    # Quote viability and cycle closure are hard gates. The selector recomputes
    # protocol, pool, and router novelty after each pick so duplicate diversity
    # gains cannot consume the bounded frontier quota.
    quoted_output_by_edge = {
        key: int(value[0])
        for key, value in first_leg_quotes.items()
        if value and int(value[0]) > 0
    }
    quote_quality_by_edge = _frontier_quote_quality_percentiles(
        frontier_candidates, quoted_output_by_edge
    )
    frontier_selected, frontier_by_token = _select_three_leg_frontier_edges(
        frontier_candidates,
        active_protocols_by_token=active_protocols_by_token,
        active_pools_by_token=active_pools_by_token,
        active_routers_by_token=active_routers_by_token,
        per_token_cap=frontier_per_token,
        global_cap=frontier_global,
        quoted_output_by_edge=quoted_output_by_edge,
        quote_quality_by_edge=quote_quality_by_edge,
    )

    frontier_adj: Dict[str, List[Edge]] = {
        token: list(items) for token, items in adj.items()
    }
    for token, items in frontier_by_token.items():
        frontier_adj.setdefault(token, []).extend(items)

    if telemetry is not None:
        active_directed_pairs = {
            (str(edge.token_in).lower(), str(edge.token_out).lower())
            for items in adj.values() for edge in items
        }
        frontier_directed_pairs = {
            pair for edge in frontier_selected
            if (pair := _edge_directed_pair_identity(edge)) is not None
        }
        new_directed_pairs = frontier_directed_pairs - active_directed_pairs
        selected_quote_percentiles = [
            quote_quality_by_edge.get((pair[0], pair[1], edge_key(edge)), 0)
            for edge in frontier_selected
            if (pair := _edge_directed_pair_identity(edge)) is not None
        ]
        new_protocols = {
            (edge.token_in, protocol)
            for edge in frontier_selected
            if (protocol := _edge_protocol_identity(edge)) is not None
            and protocol not in active_protocols_by_token.get(edge.token_in, set())
        }
        new_pools = {
            (edge.token_in, pool)
            for edge in frontier_selected
            if (pool := _edge_pool_identity(edge)) is not None
            and pool not in active_pools_by_token.get(edge.token_in, set())
        }
        new_routers = {
            (edge.token_in, router)
            for edge in frontier_selected
            if (router := _edge_router_identity(edge)) is not None
            and router not in active_routers_by_token.get(edge.token_in, set())
        }
        telemetry["three_leg_frontier"] = {
            "enabled": bool(frontier_selected),
            "initial_pruned_edges": int(len(pruned_edges)),
            "selected_edges": int(len(frontier_selected)),
            "per_token_cap": int(frontier_per_token),
            "global_cap": int(frontier_global),
            "quote_viable_edges": int(
                sum(1 for edge in pruned_edges if first_leg_quotes.get(edge_key(edge)))
            ),
            # Compatibility field retains the old raw venue-address meaning.
            # Prefer the three separate identity dimensions for new consumers.
            "venue_diversity_semantics": "legacy_edge_venue_address",
            "venue_diverse_edges": int(
                sum(
                    1
                    for edge in frontier_selected
                    if str(edge.venue).strip().lower()
                    not in active_venues_by_token.get(edge.token_in, set())
                )
            ),
            "protocol_diverse_edges": int(len(new_protocols)),
            "pool_diverse_edges": int(len(new_pools)),
            "router_diverse_edges": int(len(new_routers)),
            "directed_pair_diverse_edges": int(len(new_directed_pairs)),
            "directed_pair_identity": "token_in->token_out",
            "quote_quality_priority_used": bool(quoted_output_by_edge),
            "quote_quality_directed_pair_groups": _frontier_quote_quality_directed_pair_group_count(
                frontier_candidates,
                quoted_output_by_edge,
            ),
            "selected_mean_quote_quality_percentile_bps": (
                int(sum(selected_quote_percentiles) / len(selected_quote_percentiles))
                if selected_quote_percentiles else None
            ),
        }

    return frontier_adj


async def find_three_leg_opportunities(
    rpc,
    cfg,
    cache: PerBlockCache,
    block_number: int,
    *,
    amount_in: int,
    slippage_bps: int,
    time_budget_ms: int = 2200,
    max_opps: int = 40,
    telemetry: Optional[Dict[str, Any]] = None,
    max_reverse_candidates: Optional[int] = None,
    extra_v3_pairs: Optional[List[dict]] = None,
    extra_curve_pools: Optional[List[dict]] = None,
    extra_balancer_pools: Optional[List[dict]] = None,
    extra_aerodrome_pools: Optional[List[dict]] = None,
    extra_slipstream_pools: Optional[List[dict]] = None,
    extra_camelot_algebra_pools: Optional[List[dict]] = None,
    extra_camelot_v2_pools: Optional[List[dict]] = None,
    extra_constant_product_pools: Optional[List[dict]] = None,
    amount_in_by_token: Optional[Dict[str, int]] = None,
    observed_gas_price_wei: Optional[int] = None,
    pool_event_cache: Any = None,
    max_scan_edges: Optional[int] = None,
) -> List[Opportunity]:
    """Triangle / 3-hop cycle search A->B->C->A.

    Performance safety:
    - time budget enforced
    - adjacency limited per token
    - no discovery here; pass extra_v3_pairs from DiscoveryManager
    """
    t_start = time.perf_counter()
    route_deadline = t_start + max(1, int(time_budget_ms)) / 1000.0
    first_leg_quote_budget_ms = _first_leg_quote_budget_ms(time_budget_ms)
    first_leg_quote_deadline = min(
        route_deadline, t_start + first_leg_quote_budget_ms / 1000.0
    )
    metrics: Dict[str, int] = {}
    edge_build_diagnostics: Dict[str, Any] = {}
    edges = build_edges(
        cfg,
        extra_v3_pairs=extra_v3_pairs,
        extra_curve_pools=extra_curve_pools,
        extra_balancer_pools=extra_balancer_pools,
        extra_aerodrome_pools=extra_aerodrome_pools,
        extra_slipstream_pools=extra_slipstream_pools,
        extra_camelot_algebra_pools=extra_camelot_algebra_pools,
        extra_camelot_v2_pools=extra_camelot_v2_pools,
        extra_constant_product_pools=extra_constant_product_pools,
        diagnostics=edge_build_diagnostics,
    )
    pool_event_metrics: Dict[str, Any] = {}
    if pool_event_cache is not None:
        try:
            full_edge_count = len(edges)
            pool_event_cache.refresh_edges(
                edges,
                balancer_vault=str(getattr(cfg.chain, "balancer_vault", "") or ""),
            )
            edges, pool_event_metrics = pool_event_cache.candidate_edges(
                edges,
                current_block=int(block_number),
                max_candidates=int(
                    os.environ.get("VICTOR_EVENT_CANDIDATE_MAX", "768") or 768
                ),
                exploration_ratio=float(
                    os.environ.get("VICTOR_EVENT_EXPLORATION_RATIO", "0.10") or 0.10
                ),
            )
            pool_event_metrics["full_edge_count"] = int(full_edge_count)
        except (AttributeError, TypeError, ValueError):
            pool_event_metrics = {}
    edges = _apply_scan_edge_cap(edges, max_scan_edges, metrics)
    # A selected-provider chunk bounds which edges are initially quoted, not
    # which edges are allowed to define cycle topology. Three-leg search must
    # retain the immutable full graph for adjacency/reverse-leg lookup, matching
    # the two-leg scanner; otherwise a cycle spanning two chunks is invisible.
    scan_edges = list(edges)
    route_edges = list(scan_edges)
    route_universe_edges_fn = getattr(pool_event_cache, "route_universe_edges", None)
    if callable(route_universe_edges_fn):
        try:
            candidate_route_edges = list(route_universe_edges_fn() or [])
            if candidate_route_edges:
                route_edges = candidate_route_edges
        except (AttributeError, TypeError, ValueError):
            route_edges = list(scan_edges)

    # Keep first-leg quote work bounded to this tick's slice while deriving
    # adjacency and route closure from the complete immutable graph.
    max_edges_per_token = max(
        1, int(os.environ.get("VICTOR_MAX_EDGES_PER_TOKEN", "16") or 16)
    )
    adj, pruned_edges = _prioritize_three_leg_adjacency(
        route_edges,
        max_edges_per_token=max_edges_per_token,
    )
    by_pair: Dict[Tuple[str, str], List[Edge]] = {}
    for edge in route_edges:
        by_pair.setdefault((edge.token_in, edge.token_out), []).append(edge)
    route_universe = _route_universe_snapshot(
        cfg,
        route_edges,
        adjacency=adj,
        max_edges_per_token=max_edges_per_token,
        pruned_edges=pruned_edges,
        edge_build_diagnostics=edge_build_diagnostics,
    )

    opps: List[Opportunity] = []
    # Quote acquisition can legitimately consume most of the scan wall clock on
    # a slow provider. Start the bounded route-evaluation clock only after the
    # first-leg quote phase, matching the two-leg scanner.
    quote_phase_started = time.perf_counter()
    normalized_amounts = {
        str(token).lower(): max(1, int(value))
        for token, value in dict(amount_in_by_token or {}).items()
        if str(token) and int(value) > 0
    }
    edge_groups: Dict[int, List[Edge]] = {}
    for edge in scan_edges:
        effective_amount = int(normalized_amounts.get(str(edge.token_in).lower(), int(amount_in)))
        edge_groups.setdefault(effective_amount, []).append(edge)
    ordered_triangle_edge_groups = sorted(
        edge_groups.items(),
        key=lambda item: _triangle_edge_group_potential(
            item, adjacency=adj, by_pair=by_pair
        ),
        reverse=True,
    )
    qmap1_3, first_leg_quote_schedule = await _quote_edge_groups_in_bounded_waves(
        rpc,
        cfg,
        cache,
        ordered_triangle_edge_groups,
        deadline=first_leg_quote_deadline,
        block_number=int(block_number),
        parallelism=_route_group_parallelism(),
        metrics=metrics,
    )
    route_eval_started = time.perf_counter()
    route_groups_evaluated = 0
    route_budget_exhausted = bool(time.perf_counter() >= route_deadline)
    triangle_second_leg_quote_batches_completed = 0
    triangle_third_leg_quote_batches_total = 0
    triangle_third_leg_quote_batches_unique = 0
    triangle_third_leg_quote_batches_completed = 0
    triangle_third_leg_quote_batches_failed = 0
    triangle_third_leg_quote_batches_cancelled = 0
    triangle_third_leg_quote_batches_skipped_budget = 0
    triangle_third_leg_quote_edges_recovered_after_cancellation = 0
    triangle_third_leg_quote_edges_recovered_from_cache_when_skipped = 0
    triangle_third_leg_quote_waves_started = 0
    triangle_third_leg_quote_batches_coalesced = 0
    triangle_third_leg_quote_deadline_exceeded = False
    triangle_coalesced_quote_batches = 0
    triangle_quote_waves_started = 0

    frontier_adj = _build_three_leg_frontier(
        route_edges,
        pruned_edges,
        adj,
        by_pair,
        qmap1_3,
        telemetry=telemetry,
    )

    # Prepare viable first-edge groups in fair source-token/protocol order.
    triangle_route_groups: List[Dict[str, Any]] = []
    triangle_ordered_edges = _round_robin_route_group_edges(
        [edge for items in frontier_adj.values() for edge in items]
    )
    for e1 in triangle_ordered_edges:
        if time.perf_counter() >= route_deadline:
            route_budget_exhausted = True
            break
        if normalized_amounts:
            effective_amount_in = int(normalized_amounts.get(str(e1.token_in).lower(), 0))
            if effective_amount_in <= 0:
                metrics["route_rejections_input_notional_unavailable"] = int(
                    metrics.get("route_rejections_input_notional_unavailable", 0)
                ) + 1
                continue
        else:
            effective_amount_in = int(amount_in)
        q1 = qmap1_3.get(edge_key(e1))
        if not q1:
            continue
        out1, meta1 = q1
        e2_cands = [
            e2 for e2 in frontier_adj.get(e1.token_out, [])
            if e2.token_out != e1.token_in
        ]
        if not e2_cands:
            continue
        metrics["candidate_count"] = int(metrics.get("candidate_count", 0)) + len(e2_cands)
        triangle_route_groups.append({
            "e1": e1,
            "effective_amount_in": int(effective_amount_in),
            "out1": int(out1),
            "meta1": meta1,
            "revs": e2_cands,
        })

    configured_reverse_candidates = (
        max_reverse_candidates
        if max_reverse_candidates not in (None, "")
        else int(os.environ.get("VICTOR_MAX_REVERSE_CANDIDATES", "8") or 8)
    )
    max_reverse_candidates = max(3, min(12, int(configured_reverse_candidates)))

    triangle_route_parallelism = _route_group_parallelism()
    for wave_start in range(0, len(triangle_route_groups), triangle_route_parallelism):
        if time.perf_counter() >= route_deadline:
            route_budget_exhausted = True
            break
        wave = triangle_route_groups[wave_start:wave_start + triangle_route_parallelism]
        qmaps2, physical_batches, coalesced_batches = await _quote_two_leg_route_group_wave(
            rpc, cfg, cache, wave, metrics=metrics, deadline=route_deadline
        )
        triangle_quote_waves_started += 1
        triangle_second_leg_quote_batches_completed += int(physical_batches)
        triangle_coalesced_quote_batches += int(coalesced_batches)
        # Prepare all third-leg quote jobs for this bounded route-group wave
        # before making RPC calls. Previously every e2 candidate awaited its own
        # third-leg batch serially, which consumed the shared deadline one RPC at
        # a time even though second-leg groups were already parallelized.
        third_leg_plan_by_group_and_edge: Dict[Tuple[int, str], Tuple[Tuple[int, Tuple[str, ...]], List[Edge]]] = {}
        third_leg_jobs: Dict[Tuple[int, Tuple[str, ...]], Tuple[int, List[Edge]]] = {}
        third_leg_logical_batches = 0
        for group_index, (group, qmap2_3) in enumerate(zip(wave, qmaps2)):
            e1 = group["e1"]
            e2_cands = group["revs"]
            route_groups_evaluated += 1
            for e2 in e2_cands:
                q2 = qmap2_3.get(edge_key(e2))
                if not q2:
                    continue
                out2, _meta2 = q2
                revs = by_pair.get((e2.token_out, e1.token_in), [])
                if not revs:
                    continue
                e3_cands = list(revs[:max_reverse_candidates])
                if not e3_cands:
                    continue
                metrics["candidate_count"] = int(metrics.get("candidate_count", 0)) + len(e3_cands)
                signature = (
                    int(out2),
                    tuple(sorted(edge_key(edge) for edge in e3_cands)),
                )
                third_leg_plan_by_group_and_edge[(group_index, edge_key(e2))] = (
                    signature,
                    e3_cands,
                )
                third_leg_jobs.setdefault(signature, (int(out2), e3_cands))
                third_leg_logical_batches += 1

        third_leg_job_list = [
            (signature, amount_out, edges)
            for signature, (amount_out, edges) in third_leg_jobs.items()
        ]
        triangle_third_leg_quote_batches_total += int(third_leg_logical_batches)
        triangle_third_leg_quote_batches_unique += int(len(third_leg_job_list))
        third_leg_quote_maps, third_leg_schedule = await _quote_edge_jobs_in_bounded_waves(
            rpc,
            cfg,
            cache,
            third_leg_job_list,
            deadline=route_deadline,
            parallelism=triangle_route_parallelism,
            metrics=metrics,
            allow_one_after_deadline=True,
        )
        triangle_third_leg_quote_batches_completed += int(third_leg_schedule["batches_completed"])
        triangle_third_leg_quote_batches_failed += int(third_leg_schedule["batches_failed"])
        triangle_third_leg_quote_batches_cancelled += int(third_leg_schedule["batches_cancelled"])
        triangle_third_leg_quote_batches_skipped_budget += int(third_leg_schedule["batches_skipped_budget"])
        triangle_third_leg_quote_waves_started += int(third_leg_schedule["waves_started"])
        triangle_third_leg_quote_edges_recovered_after_cancellation += int(
            third_leg_schedule["partial_quote_edges_recovered_after_cancellation"]
        )
        triangle_third_leg_quote_edges_recovered_from_cache_when_skipped += int(
            third_leg_schedule["edges_recovered_from_cache_when_skipped"]
        )
        triangle_third_leg_quote_batches_coalesced += max(
            0, int(third_leg_logical_batches) - len(third_leg_jobs)
        )
        if third_leg_schedule["deadline_exceeded"]:
            triangle_third_leg_quote_deadline_exceeded = True
            route_budget_exhausted = True

        # Process every completed/recovered quote before honoring the budget
        # stop. Results are keyed by both amount and edge-set signature, so the
        # same edge quoted at two different intermediate amounts never aliases.
        for group_index, (group, qmap2_3) in enumerate(zip(wave, qmaps2)):
            e1 = group["e1"]
            effective_amount_in = int(group["effective_amount_in"])
            out1 = int(group["out1"])
            meta1 = group["meta1"]
            e2_cands = group["revs"]
            for e2 in e2_cands:
                q2 = qmap2_3.get(edge_key(e2))
                if not q2:
                    continue
                out2, meta2 = q2
                planned = third_leg_plan_by_group_and_edge.get((group_index, edge_key(e2)))
                if not planned:
                    continue
                signature, e3_cands = planned
                qmap3_3 = third_leg_quote_maps.get(signature, {})
                for e3 in e3_cands:
                    q3 = qmap3_3.get(edge_key(e3))
                    if not q3:
                        continue
                    out3, meta3 = q3
                    gross_profit = out3 - effective_amount_in
                    # slippage haircut
                    min1 = _apply_slippage(out1, slippage_bps)
                    min2 = _apply_slippage(out2, slippage_bps)
                    min3 = _apply_slippage(out3, slippage_bps)

                    def _aux_for(edge: Edge, meta: Dict[str, Any]) -> str:
                        if edge.dex == "univ3":
                            return aux_univ3_fee(int(meta.get("fee", edge.params.get("fee", 3000))))
                        if edge.dex == "curve":
                            return aux_curve_from_meta(meta, edge.params)
                        if edge.dex == "balancer":
                            return str(edge.params.get("pool_id") or "0x")
                        if edge.dex == "aerodrome":
                            factory = str(meta.get("factory", edge.params.get("factory", "")) or "")
                            stable = bool(meta.get("stable", edge.params.get("stable", False)))
                            raw = int(factory, 16) | ((1 if stable else 0) << 160)
                            return _aux_u256_to_b32_hex(raw)
                        if edge.dex == "slipstream":
                            return _aux_u256_to_b32_hex(int(meta.get("tick_spacing", edge.params.get("tick_spacing", 0))) & 0xFFFFFF)
                        return "0x"

                    aux1 = _aux_for(e1, meta1)
                    aux2 = _aux_for(e2, meta2)
                    aux3 = _aux_for(e3, meta3)

                    rid = route_id_hex(
                        [
                            EncLeg(
                                dex=e1.dex,
                                venue=e1.venue,
                                token_in=e1.token_in,
                                token_out=e1.token_out,
                                aux=aux1,
                            ),
                            EncLeg(
                                dex=e2.dex,
                                venue=e2.venue,
                                token_in=e2.token_in,
                                token_out=e2.token_out,
                                aux=aux2,
                            ),
                            EncLeg(
                                dex=e3.dex,
                                venue=e3.venue,
                                token_in=e3.token_in,
                                token_out=e3.token_out,
                                aux=aux3,
                            ),
                        ]
                    )

                    if gross_profit <= 0 and os.environ.get("VICTOR_DEBUG_OPPS", "").strip() != "1":
                        gas_cost_wei = int(
                            estimate_gas_cost_wei_from_cfg(
                                cfg,
                                estimate_route_gas_units(
                                    {
                                        "leg1": meta1,
                                        "leg2": meta2,
                                        "leg3": meta3,
                                        "venues": [e1.dex, e2.dex, e3.dex],
                                    }
                                ),
                                observed_gas_price_wei=observed_gas_price_wei,
                            )
                        )
                        flashloan_fee_wei = (
                            int(effective_amount_in) * int(getattr(getattr(cfg, "execution", None), "flashloan_fee_bps", 0) or 0)
                        ) // 10_000
                        _record_size_economic_diagnostic(
                            metrics,
                            route_id=rid,
                            amount_in=int(effective_amount_in),
                            gross_profit_wei=int(gross_profit),
                            flashloan_fee_wei=int(flashloan_fee_wei),
                            gas_cost_wei=int(gas_cost_wei),
                            reason="non_positive_gross_profit",
                            legs=[
                                {"dex": str(e1.dex), "venue": str(e1.venue), "token_in": str(e1.token_in), "token_out": str(e1.token_out), "fee": int(meta1.get("fee", e1.params.get("fee", 0) or 0)), "pool": str(e1.params.get("pool") or e1.venue), "amount_in": str(int(effective_amount_in)), "quoted_amount_out": str(int(out1)), "min_out": str(int(min1)), "slippage_reserve": str(max(0, int(out1) - int(min1))), "quote_meta": dict(meta1), "edge_params": dict(e1.params), "data": str(aux1)},
                                {"dex": str(e2.dex), "venue": str(e2.venue), "token_in": str(e2.token_in), "token_out": str(e2.token_out), "fee": int(meta2.get("fee", e2.params.get("fee", 0) or 0)), "pool": str(e2.params.get("pool") or e2.venue), "amount_in": str(int(out1)), "quoted_amount_out": str(int(out2)), "min_out": str(int(min2)), "slippage_reserve": str(max(0, int(out2) - int(min2))), "quote_meta": dict(meta2), "edge_params": dict(e2.params), "data": str(aux2)},
                                {"dex": str(e3.dex), "venue": str(e3.venue), "token_in": str(e3.token_in), "token_out": str(e3.token_out), "fee": int(meta3.get("fee", e3.params.get("fee", 0) or 0)), "pool": str(e3.params.get("pool") or e3.venue), "amount_in": str(int(out2)), "quoted_amount_out": str(int(out3)), "min_out": str(int(min3)), "slippage_reserve": str(max(0, int(out3) - int(min3))), "quote_meta": dict(meta3), "edge_params": dict(e3.params), "data": str(aux3)},
                            ]
                        )
                        continue

                    pool_keys = [
                        _pool_keys_for_leg(
                            e1.dex,
                            e1.token_in,
                            e1.token_out,
                            {
                                "fee": meta1.get("fee", e1.params.get("fee", 3000)),
                                "pool": e1.venue,
                                **e1.params,
                            },
                            aux1,
                        ),
                        _pool_keys_for_leg(
                            e2.dex,
                            e2.token_in,
                            e2.token_out,
                            {
                                "fee": meta2.get("fee", e2.params.get("fee", 3000)),
                                "pool": e2.venue,
                                **e2.params,
                            },
                            aux2,
                        ),
                        _pool_keys_for_leg(
                            e3.dex,
                            e3.token_in,
                            e3.token_out,
                            {
                                "fee": meta3.get("fee", e3.params.get("fee", 3000)),
                                "pool": e3.venue,
                                **e3.params,
                            },
                            aux3,
                        ),
                    ]

                    opp_id = _id([cfg.chain.name, "3leg", rid, str(effective_amount_in), str(block_number)])
                    opps.append(
                        Opportunity(
                            id=opp_id,
                            chain=cfg.chain.name,
                            strategy=f"tri:{e1.dex}->{e2.dex}->{e3.dex}",
                            expected_profit_raw=str(gross_profit),
                            expected_profit_usd="0",
                            route=Route(
                                legs=[
                                    RouteLeg(
                                        dex=e1.dex,
                                        venue=e1.venue,
                                        token_in=e1.token_in,
                                        token_out=e1.token_out,
                                        amount_in=str(effective_amount_in),
                                        min_out=str(min1),
                                        data=aux1,
                                    ),
                                    RouteLeg(
                                        dex=e2.dex,
                                        venue=e2.venue,
                                        token_in=e2.token_in,
                                        token_out=e2.token_out,
                                        amount_in=str(out1),
                                        min_out=str(min2),
                                        data=aux2,
                                    ),
                                    RouteLeg(
                                        dex=e3.dex,
                                        venue=e3.venue,
                                        token_in=e3.token_in,
                                        token_out=e3.token_out,
                                        amount_in=str(out2),
                                        min_out=str(min3),
                                        data=aux3,
                                    ),
                                ]
                            ),
                            min_outs=[str(min1), str(min2), str(min3)],
                            route_id=rid,
                            can_execute=False,
                            created_at_ms=_now_ms(),
                            meta={
                                "out1": str(out1),
                                "out2": str(out2),
                                "out3": str(out3),
                                "leg1": meta1,
                                "leg2": meta2,
                                "leg3": meta3,
                                "route_type": "3leg",
                                "route_edge_params": [dict(e1.params), dict(e2.params), dict(e3.params)],
                                "route_family": _classify_route_family(cfg, [e1, e2, e3], route_type="3leg"),
                                "venues": [e1.dex, e2.dex, e3.dex],
                                "pool_keys": pool_keys,
                                "gas_estimate_units": str(
                                    estimate_route_gas_units(
                                        {
                                            "leg1": meta1,
                                            "leg2": meta2,
                                            "leg3": meta3,
                                            "venues": [e1.dex, e2.dex, e3.dex],
                                        }
                                    )
                                ),
                                "gas_cost_estimate_wei": str(
                                    estimate_gas_cost_wei_from_cfg(
                                        cfg,
                                        estimate_route_gas_units(
                                            {
                                                "leg1": meta1,
                                                "leg2": meta2,
                                                "leg3": meta3,
                                                "venues": [e1.dex, e2.dex, e3.dex],
                                            }
                                        ),
                                    )
                                ),
                                "profit_after_gas_estimate_wei": str(
                                    int(gross_profit)
                                    - int(
                                        estimate_gas_cost_wei_from_cfg(
                                            cfg,
                                            estimate_route_gas_units(
                                                {
                                                    "leg1": meta1,
                                                    "leg2": meta2,
                                                    "leg3": meta3,
                                                    "venues": [e1.dex, e2.dex, e3.dex],
                                                }
                                            ),
                                        )
                                    )
                                ),
                            },
                        )
                    )
        if route_budget_exhausted:
            break
        if (
            wave_start + triangle_route_parallelism < len(triangle_route_groups)
            and time.perf_counter() >= route_deadline
        ):
            route_budget_exhausted = True
            break

    if time.perf_counter() >= route_deadline:
        route_budget_exhausted = True

    if telemetry is not None:
        telemetry["quote_phase_ms"] = float(
            (route_eval_started - quote_phase_started) * 1000.0
        )
        telemetry["route_evaluation_ms"] = float(
            (time.perf_counter() - route_eval_started) * 1000.0
        )
        telemetry["route_budget_elapsed_ms"] = float(
            (time.perf_counter() - t_start) * 1000.0
        )
        telemetry["route_budget_deadline_ms"] = int(max(1, int(time_budget_ms)))
        telemetry["route_groups_evaluated"] = int(route_groups_evaluated)
        telemetry["route_group_schedule"] = {
            "block_number": int(block_number),
            "groups_prepared": int(len(triangle_route_groups)),
            "groups_completed": int(route_groups_evaluated),
            "quote_batches_completed_and_consumed": int(
                first_leg_quote_schedule["batches_completed"]
                + triangle_second_leg_quote_batches_completed
                + triangle_third_leg_quote_batches_completed
            ),
            "first_leg_quote_batches_total": int(first_leg_quote_schedule["batches_total"]),
            "first_leg_quote_batches_completed": int(first_leg_quote_schedule["batches_completed"]),
            "first_leg_quote_batches_failed": int(first_leg_quote_schedule["batches_failed"]),
            "first_leg_quote_batches_cancelled": int(first_leg_quote_schedule["batches_cancelled"]),
            "first_leg_quote_batches_skipped_budget": int(first_leg_quote_schedule["batches_skipped_budget"]),
            "first_leg_quote_edges_recovered_after_cancellation": int(
                first_leg_quote_schedule.get("partial_quote_edges_recovered_after_cancellation", 0)
            ),
            "first_leg_quote_budget_ms": int(first_leg_quote_budget_ms),
            "first_leg_quote_budget_exhausted": bool(first_leg_quote_schedule["deadline_exceeded"]),
            "first_leg_quote_waves_started": int(first_leg_quote_schedule["waves_started"]),
            "first_leg_quote_parallelism_limit": int(first_leg_quote_schedule["parallelism_limit"]),
            "first_leg_deadline_exceeded": bool(first_leg_quote_schedule["deadline_exceeded"]),
            "first_leg_quote_ordering": str(first_leg_quote_schedule["ordering"]),
            "route_group_quote_batches_completed_and_consumed": int(
                triangle_second_leg_quote_batches_completed
                + triangle_third_leg_quote_batches_completed
            ),
            "route_group_quote_batches_coalesced": int(
                triangle_coalesced_quote_batches + triangle_third_leg_quote_batches_coalesced
            ),
            "route_group_quote_batches_failed": int(metrics.get("route_group_quote_batches_failed", 0) or 0),
            "route_group_quote_batches_cancelled": int(metrics.get("route_group_quote_batches_cancelled", 0) or 0),
            "route_group_quote_batches_skipped_budget": int(metrics.get("route_group_quote_batches_skipped_budget", 0) or 0),
            "route_group_quote_edges_recovered_after_cancellation": int(metrics.get("route_group_quote_edges_recovered_after_cancellation", 0) or 0),
            "route_group_quote_edges_recovered_from_cache_when_skipped": int(metrics.get("route_group_quote_edges_recovered_from_cache_when_skipped", 0) or 0),
            "route_group_quote_waves_started": int(metrics.get("route_group_quote_waves_started", 0) or 0),
            "third_leg_quote_batches_total": int(triangle_third_leg_quote_batches_total),
            "third_leg_quote_batches_unique": int(triangle_third_leg_quote_batches_unique),
            "third_leg_quote_batches_completed": int(triangle_third_leg_quote_batches_completed),
            "third_leg_quote_batches_failed": int(triangle_third_leg_quote_batches_failed),
            "third_leg_quote_batches_cancelled": int(triangle_third_leg_quote_batches_cancelled),
            "third_leg_quote_batches_skipped_budget": int(triangle_third_leg_quote_batches_skipped_budget),
            "third_leg_quote_batches_coalesced": int(triangle_third_leg_quote_batches_coalesced),
            "third_leg_quote_edges_recovered_after_cancellation": int(
                triangle_third_leg_quote_edges_recovered_after_cancellation
            ),
            "third_leg_quote_edges_recovered_from_cache_when_skipped": int(
                triangle_third_leg_quote_edges_recovered_from_cache_when_skipped
            ),
            "third_leg_quote_waves_started": int(triangle_third_leg_quote_waves_started),
            "third_leg_quote_parallelism_limit": int(triangle_route_parallelism),
            "third_leg_quote_deadline_exceeded": bool(triangle_third_leg_quote_deadline_exceeded),
            "route_group_quote_batches_coalesced_second_leg": int(triangle_coalesced_quote_batches),
            "route_group_quote_batches_coalesced_third_leg": int(triangle_third_leg_quote_batches_coalesced),
            "parallelism_limit": int(triangle_route_parallelism),
            "waves_started": int(triangle_quote_waves_started),
            "ordering": "round_robin_source_token_protocol",
            "completed_wave_results_consumed_before_budget_stop": True,
        }
        telemetry["first_leg_quote_budget_ms"] = int(first_leg_quote_budget_ms)
        telemetry["first_leg_quote_budget_exhausted"] = bool(first_leg_quote_schedule["deadline_exceeded"])
        telemetry["first_leg_quote_batches_cancelled"] = int(first_leg_quote_schedule["batches_cancelled"])
        telemetry["route_budget_exhausted"] = bool(route_budget_exhausted)
        telemetry["route_budget_stop_reason"] = (
            "time_budget" if route_budget_exhausted else "completed"
        )
        telemetry["budget_exhausted_after_quote"] = bool(route_budget_exhausted)

    snapshot = scan_efficiency_snapshot(
        elapsed_ms=(time.perf_counter() - t_start) * 1000.0,
        candidate_count=int(metrics.get("candidate_count", 0)),
        quote_requests=int(metrics.get("quote_requests", 0)),
        quote_successes=int(metrics.get("quote_successes", 0)),
        opportunity_count=len(opps),
        cache_hits=int(metrics.get("cache_hits", 0)),
        network_batches=int(metrics.get("network_batches", 0)),
    )
    for opportunity in opps:
        opportunity.meta["scan_efficiency"] = dict(snapshot)
    if telemetry is not None:
        telemetry.update({
            "elapsed_ms": float(snapshot["elapsed_ms"]),
            "candidate_count": int(snapshot["candidate_count"]),
            "quote_requests": int(snapshot["quote_requests"]),
            "quote_successes": int(snapshot["quote_successes"]),
            "quote_cancelled": int(metrics.get("quote_cancelled", 0) or 0),
            "quote_success_rate": float(snapshot["quote_success_rate"]),
            "cache_hits": int(snapshot["cache_hits"]),
            "network_batches": int(snapshot["network_batches"]),
            "routes_considered": int(snapshot["candidate_count"]),
            "edges_generated": len(scan_edges),
            "route_universe_edge_count": int(len(route_edges)),
            "route_universe": dict(route_universe),
            "gross_candidates": len(opps),
            "opportunity_count": len(opps),
            "quote_failure_reasons": dict(metrics.get("quote_failure_reasons") or {}),
            **_quote_family_metric_snapshot(metrics),
            **_quote_failure_reason_snapshot(metrics),
            "quote_fallback_attempts": int(metrics.get("quote_fallback_attempts", 0)),
            "quote_fallback_successes": int(metrics.get("quote_fallback_successes", 0)),
            "size_economic_diagnostics": list(metrics.get("size_economic_diagnostics") or []),
            "pool_event_state": dict(pool_event_metrics or {}),
            "scan_edges_before_cap": int(metrics.get("scan_edges_before_cap", len(edges))),
            "scan_edge_cap": (
                int(metrics["scan_edge_cap"])
                if metrics.get("scan_edge_cap") not in (None, "")
                else None
            ),
            "scan_edges_selected": int(metrics.get("scan_edges_selected", len(edges))),
            "scan_edges_capped": int(metrics.get("scan_edges_capped", 0)),
        })
    # Rank completed two-leg routes by comparable after-cost USD economics,
    # then use token-local net P&L only when conversion evidence is absent.
    opps.sort(key=_opportunity_economic_sort_key, reverse=True)
    return opps[: max(1, int(max_opps))]


async def requote_opportunity(
    rpc,
    cfg,
    cache: PerBlockCache,
    opp: Opportunity,
    *,
    new_amount_in: int,
    slippage_bps: int,
) -> Optional[Opportunity]:
    """Re-quote an existing route for a new borrow amount.

    This is used for borrow-sizing actions (RL) without increasing scan RPC load.
    It is only invoked for attempted trades.
    """
    if new_amount_in <= 0:
        return None
    legs = list(opp.route.legs or [])
    if not legs:
        return None

    def _decode_u256_b32(aux_hex: str) -> int:
        try:
            h = aux_hex[2:] if aux_hex.startswith("0x") else aux_hex
            b = bytes.fromhex(h.rjust(64, "0"))
            return int.from_bytes(b, "big")
        except _SAFE_AUX_DECODE_EXCEPTIONS:
            return 0

    edges: List[Edge] = []
    stored_params: List[Dict[str, Any]] = []
    if isinstance(getattr(opp, "meta", None), dict):
        raw_params = opp.meta.get("route_edge_params")
        if isinstance(raw_params, list):
            stored_params = [dict(item) for item in raw_params if isinstance(item, dict)]
    for index, lg in enumerate(legs):
        params: Dict[str, Any] = (
            dict(stored_params[index])
            if index < len(stored_params)
            else {}
        )
        if not params and lg.dex == "univ3":
            v = _decode_u256_b32(lg.data or "0x")
            params["fee"] = int(v & 0xFFFFFF) or 3000
        elif not params and lg.dex == "curve":
            v = _decode_u256_b32(lg.data or "0x")
            params["i"] = int(v & 0xFF)
            params["j"] = int((v >> 8) & 0xFF)
            params["underlying"] = bool((v >> 16) & 1)
        elif not params and lg.dex == "balancer":
            params["pool_id"] = str(lg.data or "0x")
        elif not params and lg.dex == "slipstream":
            v = _decode_u256_b32(lg.data or "0x")
            params["tick_spacing"] = int(v & 0xFFFFFF)
        edges.append(Edge(lg.dex, lg.venue, lg.token_in, lg.token_out, params))

    amount = int(new_amount_in)
    outs: List[int] = []
    metas: List[Dict[str, Any]] = []
    impact_bps_per_leg: List[int] = []
    applied_bps_per_leg: List[int] = []

    # Optional dynamic slippage model (preflight only).
    dyn = bool(getattr(getattr(cfg, "safety", None), "dynamic_slippage_enabled", False))
    probe_bps = (
        int(getattr(getattr(cfg, "safety", None), "dynamic_slippage_probe_bps", 0) or 0)
        if dyn
        else 0
    )
    impact_mult = float(
        getattr(getattr(cfg, "safety", None), "dynamic_slippage_impact_mult", 1.0) or 1.0
    )
    min_bps = int(getattr(getattr(cfg, "safety", None), "dynamic_slippage_min_bps", 0) or 0)
    max_bps = int(
        getattr(getattr(cfg, "safety", None), "dynamic_slippage_max_bps", slippage_bps)
        or slippage_bps
    )
    for e in edges:
        q = await quote_edge(rpc, cfg, cache, e, amount)
        if not q:
            return None
        out, meta = q

        leg_impact_bps = 0
        leg_slip_bps = int(slippage_bps)
        if dyn and probe_bps > 0 and int(amount) > 0 and int(out) > 0:
            try:
                amount_probe = int(amount * (10000 + probe_bps) // 10000)
                if amount_probe <= amount:
                    amount_probe = amount + 1
                q2 = await quote_edge(rpc, cfg, cache, e, int(amount_probe))
                if q2:
                    out_probe, _m2 = q2
                    out_probe_i = int(out_probe)
                    # impact ≈ 1 - (out_probe/amount_probe) / (out/amount)
                    num = int(out) * int(amount_probe) - int(out_probe_i) * int(amount)
                    den = int(out) * int(amount_probe)
                    if num > 0 and den > 0:
                        leg_impact_bps = int((num * 10000) // den)
            except _SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS:
                leg_impact_bps = 0

            try:
                leg_slip_bps = int(
                    round(float(slippage_bps) + float(leg_impact_bps) * float(impact_mult))
                )
                leg_slip_bps = max(int(min_bps), min(int(max_bps), int(leg_slip_bps)))
            except _SAFE_DYNAMIC_SLIPPAGE_EXCEPTIONS:
                leg_slip_bps = int(slippage_bps)

        outs.append(int(out))
        metas.append(meta)
        impact_bps_per_leg.append(int(leg_impact_bps))
        applied_bps_per_leg.append(int(leg_slip_bps))
        amount = int(out)

    out_final = outs[-1] if outs else 0
    if out_final <= 0:
        return None

    # Update opp in-place (safe: only used for the attempted execution).
    opp.route.legs[0].amount_in = str(new_amount_in)
    for i in range(len(legs)):
        if i == 0:
            opp.route.legs[i].amount_in = str(new_amount_in)
        else:
            opp.route.legs[i].amount_in = str(outs[i - 1])
        bps_i = int(applied_bps_per_leg[i]) if i < len(applied_bps_per_leg) else int(slippage_bps)
        opp.route.legs[i].min_out = str(_apply_slippage(outs[i], bps_i))
    opp.min_outs = [
        str(
            _apply_slippage(
                outs[i],
                int(applied_bps_per_leg[i]) if i < len(applied_bps_per_leg) else int(slippage_bps),
            )
        )
        for i in range(len(outs))
    ]
    opp.expected_profit_raw = str(int(out_final) - int(new_amount_in))
    if isinstance(opp.meta, dict):
        # keep existing meta keys; update outs + leg metas.
        for i, out in enumerate(outs):
            opp.meta[f"out{i+1}"] = str(out)
            opp.meta[f"leg{i+1}"] = metas[i]
        opp.meta["requoted_amount_in"] = str(int(new_amount_in))
        opp.meta["slippage_model"] = {
            "dynamic": bool(dyn),
            "base_bps": int(slippage_bps),
            "probe_bps": int(probe_bps),
            "impact_mult": float(impact_mult),
            "impact_bps_per_leg": [int(x) for x in impact_bps_per_leg],
            "applied_bps_per_leg": [int(x) for x in applied_bps_per_leg],
        }
    return opp
