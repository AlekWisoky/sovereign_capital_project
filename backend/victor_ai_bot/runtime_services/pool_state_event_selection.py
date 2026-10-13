from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class CandidateEdgeRequest:
    edges: List[Any]
    current_block: int
    max_candidates: int = 768
    exploration_ratio: float = 0.10


@dataclass(frozen=True)
class _PriorityContext:
    cache: Any
    current_block: int
    dirty_addresses: set[str]
    affected_tokens: set[str]


@dataclass(frozen=True)
class _CandidateSubsetRequest:
    full: List[Any]
    hot: List[Any]
    cold: List[Any]
    cap: int
    ratio: float
    current_block: int


def _raw_edge_pool_address(edge: Any) -> str:
    dex = str(getattr(edge, "dex", "") or "").lower()
    params = getattr(edge, "params", {}) or {}
    if dex == "curve":
        return str(getattr(edge, "venue", "") or params.get("pool") or "")
    if dex == "balancer":
        return str(params.get("pool_address") or "")
    return str(params.get("pool") or "")


def _normalize_pool_address(value: Any) -> str:
    address = str(value or "").strip().lower()
    if not address.startswith("0x"):
        return ""
    if len(address) != 42:
        return ""
    return address


def _edge_pool_address(edge: Any) -> str:
    return _normalize_pool_address(_raw_edge_pool_address(edge))


def _edge_identity(edge: Any) -> str:
    params = getattr(edge, "params", {}) or {}
    parts = (
        str(getattr(edge, "dex", "") or ""),
        str(getattr(edge, "venue", "") or ""),
        str(getattr(edge, "token_in", "") or ""),
        str(getattr(edge, "token_out", "") or ""),
        repr(sorted((str(k), str(v)) for k, v in dict(params).items())),
    )
    return "|".join(parts)


def _edge_family_key(edge: Any) -> str:
    dex = str(getattr(edge, "dex", "unknown") or "unknown").strip().lower()
    params = getattr(edge, "params", {}) or {}
    if dex == "constant_product":
        venue_name = str(params.get("venue_name") or "").strip().lower()
        if venue_name:
            return venue_name
    return dex


def _group_edges_by_family(edges: List[Any]) -> Dict[str, List[Any]]:
    buckets: Dict[str, List[Any]] = {}
    for edge in list(edges or []):
        buckets.setdefault(_edge_family_key(edge), []).append(edge)
    return buckets


def _round_robin_family_rows(
    buckets: Dict[str, List[Any]],
    *,
    limit: int,
    current_block: int,
) -> List[Any]:
    families = sorted(buckets)
    if not families or int(limit) <= 0:
        return []
    offset = max(0, int(current_block)) % len(families)
    families = families[offset:] + families[:offset]
    selected: List[Any] = []
    max_rows = max(len(buckets[family]) for family in families)
    for row_index in range(max_rows):
        for family in families:
            bucket = buckets[family]
            if row_index < len(bucket):
                selected.append(bucket[row_index])
                if len(selected) >= int(limit):
                    return selected
    return selected


def _sample_exploration_by_family(
    edges: List[Any],
    *,
    limit: int,
    current_block: int,
) -> List[Any]:
    return _round_robin_family_rows(
        _group_edges_by_family(edges),
        limit=int(limit),
        current_block=int(current_block),
    )


def _active_priority_frontier(
    cache: Any,
    *,
    current_block: int,
) -> Tuple[set[str], set[str]]:
    dirty_addresses: set[str] = set()
    affected_tokens: set[str] = set()
    for address, state in cache._states.items():
        age = max(0, int(current_block) - int(state.last_block or 0))
        if address not in cache._dirty or not int(state.last_block) or age > 2:
            continue
        dirty_addresses.add(address)
        if state.token0:
            affected_tokens.add(str(state.token0).lower())
        if state.token1:
            affected_tokens.add(str(state.token1).lower())
    return dirty_addresses, affected_tokens


def _score_priority_edge(
    context: _PriorityContext,
    order: int,
    edge: Any,
) -> Tuple[Tuple[int, int, int, Any], bool, bool]:
    cache = context.cache
    address = cache._edge_pool_address(edge)
    priority = cache.edge_priority(edge, current_block=context.current_block)
    state = cache._states.get(address) if address else None
    last_block = int(state.last_block) if state is not None else 0
    edge_tokens = {
        str(getattr(edge, "token_in", "") or "").lower(),
        str(getattr(edge, "token_out", "") or "").lower(),
    }
    edge_tokens.discard("")
    dirty_hit = address in context.dirty_addresses
    affected_hit = bool(context.affected_tokens and edge_tokens & context.affected_tokens)
    if dirty_hit:
        priority = max(priority, 5)
    elif affected_hit:
        priority = max(priority, 4)
    return (priority, last_block, -int(order), edge), dirty_hit, affected_hit


def _score_priority_edges(
    context: _PriorityContext,
    edges: List[Any],
) -> Tuple[List[Tuple[int, int, int, Any]], int, int]:
    scored: List[Tuple[int, int, int, Any]] = []
    dirty_count = 0
    affected_subgraph_edges = 0
    for order, edge in enumerate(list(edges or [])):
        row, dirty_hit, affected_hit = _score_priority_edge(context, order, edge)
        scored.append(row)
        dirty_count += int(dirty_hit)
        affected_subgraph_edges += int(affected_hit and not dirty_hit)
    return scored, dirty_count, affected_subgraph_edges


def _priority_metrics(
    cache: Any,
    *,
    dirty_count: int,
    affected_subgraph_edges: int,
    affected_tokens: set[str],
) -> Dict[str, Any]:
    return {
        "enabled": bool(cache._tracked),
        "tracked_pools": int(len(cache._tracked)),
        "tracked_states": int(sum(1 for state in cache._states.values() if state.last_block)),
        "dirty_edges": int(dirty_count),
        "affected_token_count": int(len(affected_tokens)),
        "affected_subgraph_edges": int(affected_subgraph_edges),
        "last_event_block": int(cache._last_seen_block),
        "event_count": int(cache._event_count),
        "connected": bool(cache._connected),
        "subscribed_address_count": int(cache._subscribed_address_count),
        "subscription_truncated": bool(cache._truncated),
        "last_error": str(cache._last_error or ""),
        "candidate_generation_mode": str(cache._last_candidate_metrics.get("candidate_generation_mode") or ""),
        "candidate_edge_count": int(cache._last_candidate_metrics.get("candidate_edge_count", 0) or 0),
        "candidate_edges_full": int(cache._last_candidate_metrics.get("candidate_edges_full", 0) or 0),
        "candidate_edges_pruned": int(cache._last_candidate_metrics.get("candidate_edges_pruned", 0) or 0),
        "exploration_edge_count": int(cache._last_candidate_metrics.get("exploration_edge_count", 0) or 0),
        "hot_subgraph_edge_count": int(cache._last_candidate_metrics.get("hot_subgraph_edge_count", 0) or 0),
        "fresh_dirty_pool_count": int(cache._last_candidate_metrics.get("fresh_dirty_pool_count", 0) or 0),
        "candidate_affected_token_count": int(cache._last_candidate_metrics.get("affected_token_count", 0) or 0),
    }


def _prioritize_edges(
    cache: Any,
    edges: List[Any],
    *,
    current_block: int,
) -> Tuple[List[Any], Dict[str, Any]]:
    dirty_addresses, affected_tokens = _active_priority_frontier(
        cache, current_block=int(current_block)
    )
    context = _PriorityContext(
        cache=cache,
        current_block=int(current_block),
        dirty_addresses=dirty_addresses,
        affected_tokens=affected_tokens,
    )
    scored, dirty_count, affected_subgraph_edges = _score_priority_edges(context, list(edges or []))
    scored.sort(key=lambda item: (int(item[0]), int(item[1]), int(item[2])), reverse=True)
    ordered = [item[3] for item in scored]
    return ordered, _priority_metrics(
        cache,
        dirty_count=dirty_count,
        affected_subgraph_edges=affected_subgraph_edges,
        affected_tokens=affected_tokens,
    )


def _fresh_dirty_frontier(
    cache: Any,
    *,
    current_block: int,
) -> Tuple[set[str], set[str]]:
    dirty_pools: set[str] = set()
    affected_tokens: set[str] = set()
    for address, state in cache._states.items():
        age = max(0, int(current_block) - int(state.last_block or 0))
        if address not in cache._dirty or not int(state.last_block) or age > 2:
            continue
        dirty_pools.add(address)
        if state.token0:
            affected_tokens.add(str(state.token0).lower())
        if state.token1:
            affected_tokens.add(str(state.token1).lower())
    return dirty_pools, affected_tokens


def _partition_candidate_edges(
    cache: Any,
    full: List[Any],
    fresh_dirty_pools: set[str],
    affected_tokens: set[str],
) -> Tuple[List[Any], List[Any]]:
    hot: List[Any] = []
    cold: List[Any] = []
    seen: set[str] = set()
    for edge in full:
        edge_id = cache._edge_identity(edge)
        if edge_id in seen:
            continue
        seen.add(edge_id)
        address = cache._edge_pool_address(edge)
        edge_tokens = {
            str(getattr(edge, "token_in", "") or "").lower(),
            str(getattr(edge, "token_out", "") or "").lower(),
        }
        edge_tokens.discard("")
        if address in fresh_dirty_pools or edge_tokens & affected_tokens:
            hot.append(edge)
        else:
            cold.append(edge)
    return hot, cold


def _bounded_candidate_subset(request: _CandidateSubsetRequest) -> Tuple[List[Any], List[Any]]:
    exploration_count = min(
        len(request.cold),
        max(8, int(round(len(request.full) * request.ratio))),
    )
    exploration = _sample_exploration_by_family(
        request.cold,
        limit=exploration_count,
        current_block=request.current_block,
    )
    reserve = (
        min(len(exploration), max(8, request.cap // 4))
        if len(request.hot) + len(exploration) > request.cap and request.cold
        else 0
    )
    selected_hot = request.hot[:max(0, request.cap - reserve)]
    exploration_budget = max(0, request.cap - len(selected_hot))
    selected_exploration = exploration[:exploration_budget]
    combined: List[Any] = []
    for edge in [*selected_hot, *selected_exploration]:
        if edge not in combined:
            combined.append(edge)
    combined = combined[:request.cap]
    if not combined and request.full:
        combined = request.full[:request.cap]
    return combined, selected_exploration


def _candidate_edges(cache: Any, request: CandidateEdgeRequest) -> Tuple[List[Any], Dict[str, Any]]:
    full = list(request.edges or [])
    cap = max(32, min(2048, int(request.max_candidates)))
    ratio = max(0.02, min(0.50, float(request.exploration_ratio)))
    fresh_dirty_pools, affected_tokens = _fresh_dirty_frontier(
        cache, current_block=int(request.current_block)
    )
    if not fresh_dirty_pools:
        ordered, priority = cache.prioritize_edges(
            full, current_block=int(request.current_block)
        )
        priority["candidate_generation_mode"] = "full_graph"
        priority["candidate_edge_count"] = int(len(ordered))
        priority["candidate_edges_pruned"] = 0
        priority["exploration_edge_count"] = 0
        cache._last_candidate_metrics = dict(priority)
        return ordered, priority

    hot, cold = _partition_candidate_edges(
        cache, full, fresh_dirty_pools, affected_tokens
    )
    subset_request = _CandidateSubsetRequest(
        full=full,
        hot=hot,
        cold=cold,
        cap=cap,
        ratio=ratio,
        current_block=int(request.current_block),
    )
    combined, selected_exploration = _bounded_candidate_subset(subset_request)
    combined, priority = cache.prioritize_edges(
        combined, current_block=int(request.current_block)
    )
    priority.update({
        "candidate_generation_mode": "dirty_subgraph",
        "candidate_edge_count": int(len(combined)),
        "candidate_edges_full": int(len(full)),
        "candidate_edges_pruned": int(max(0, len(full) - len(combined))),
        "exploration_edge_count": int(sum(1 for edge in selected_exploration if edge in combined)),
        "hot_subgraph_edge_count": int(len(hot)),
        "fresh_dirty_pool_count": int(len(fresh_dirty_pools)),
        "affected_token_count": int(len(affected_tokens)),
        "max_candidates": int(cap),
        "exploration_ratio": float(ratio),
    })
    cache._last_candidate_metrics = dict(priority)
    return combined, priority
