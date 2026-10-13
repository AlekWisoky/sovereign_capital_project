from __future__ import annotations

from typing import Any, Dict, List, Tuple


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


def _edge_pool_address(edge: Any) -> str:
    dex = str(getattr(edge, "dex", "") or "").lower()
    params = getattr(edge, "params", {}) or {}
    if dex == "curve":
        address = str(getattr(edge, "venue", "") or params.get("pool") or "")
    elif dex == "balancer":
        address = str(params.get("pool_address") or "")
    else:
        address = str(params.get("pool") or "")
    address = address.strip().lower()
    if address.startswith("0x") and len(address) == 42:
        return address
    return ""


def _edge_family_key(edge: Any) -> str:
    """Return venue-family identity for balanced bounded exploration."""
    dex = str(getattr(edge, "dex", "unknown") or "unknown").strip().lower()
    params = getattr(edge, "params", {}) or {}
    if dex == "constant_product":
        venue_name = str(params.get("venue_name") or "").strip().lower()
        if venue_name:
            return venue_name
    return dex


def _sample_exploration_by_family(
    edges: List[Any],
    *,
    limit: int,
    current_block: int,
) -> List[Any]:
    """Round-robin across venue families instead of sampling the graph prefix."""
    buckets: Dict[str, List[Any]] = {}
    for edge in list(edges or []):
        buckets.setdefault(_edge_family_key(edge), []).append(edge)
    families = sorted(buckets)
    if not families or int(limit) <= 0:
        return []
    offset = max(0, int(current_block)) % len(families)
    families = families[offset:] + families[:offset]
    selected: List[Any] = []
    max_rows = max(len(buckets[family]) for family in families)
    for row_index in range(max_rows):
        for family in families:
            if len(selected) >= int(limit):
                return selected
            bucket = buckets[family]
            if row_index < len(bucket):
                selected.append(bucket[row_index])
    return selected


def _prioritize_edges(
    cache: Any,
    edges: List[Any],
    *,
    current_block: int,
) -> Tuple[List[Any], Dict[str, Any]]:
    scored: List[Tuple[int, int, int, Any]] = []
    dirty_count = 0
    affected_tokens: set[str] = set()
    dirty_addresses: set[str] = set()
    for address, state in cache._states.items():
        age = max(0, int(current_block) - int(state.last_block or 0))
        if address in cache._dirty and int(state.last_block) and age <= 2:
            dirty_addresses.add(address)
            if state.token0:
                affected_tokens.add(str(state.token0).lower())
            if state.token1:
                affected_tokens.add(str(state.token1).lower())

    affected_subgraph_edges = 0
    for order, edge in enumerate(list(edges or [])):
        address = cache._edge_pool_address(edge)
        priority = cache.edge_priority(edge, current_block=int(current_block))
        state = cache._states.get(address) if address else None
        last_block = int(state.last_block) if state is not None else 0
        edge_tokens = {
            str(getattr(edge, "token_in", "") or "").lower(),
            str(getattr(edge, "token_out", "") or "").lower(),
        }
        edge_tokens.discard("")
        if address in dirty_addresses:
            priority = max(priority, 5)
            dirty_count += 1
        elif affected_tokens and edge_tokens & affected_tokens:
            priority = max(priority, 4)
            affected_subgraph_edges += 1
        scored.append((priority, last_block, -order, edge))
    scored.sort(
        key=lambda item: (int(item[0]), int(item[1]), int(item[2])),
        reverse=True,
    )
    ordered = [item[3] for item in scored]
    return ordered, {
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
        "candidate_generation_mode": str(
            cache._last_candidate_metrics.get("candidate_generation_mode") or ""
        ),
        "candidate_edge_count": int(cache._last_candidate_metrics.get("candidate_edge_count", 0) or 0),
        "candidate_edges_full": int(cache._last_candidate_metrics.get("candidate_edges_full", 0) or 0),
        "candidate_edges_pruned": int(cache._last_candidate_metrics.get("candidate_edges_pruned", 0) or 0),
        "exploration_edge_count": int(cache._last_candidate_metrics.get("exploration_edge_count", 0) or 0),
        "hot_subgraph_edge_count": int(cache._last_candidate_metrics.get("hot_subgraph_edge_count", 0) or 0),
        "fresh_dirty_pool_count": int(cache._last_candidate_metrics.get("fresh_dirty_pool_count", 0) or 0),
        "candidate_affected_token_count": int(cache._last_candidate_metrics.get("affected_token_count", 0) or 0),
    }


def _edge_priority(cache: Any, edge: Any, *, current_block: int) -> int:
    address = cache._edge_pool_address(edge)
    if not address:
        return 1
    state = cache._states.get(address)
    if state is None or not int(state.last_block):
        return 1
    age = max(0, int(current_block) - int(state.last_block))
    if address in cache._dirty and age <= 2:
        return 4
    if age <= 2:
        return 3
    if age <= 5:
        return 2
    return 1


def _fresh_dirty_frontier(
    cache: Any,
    *,
    current_block: int,
) -> Tuple[set[str], set[str]]:
    dirty_pools: set[str] = set()
    affected_tokens: set[str] = set()
    for address, state in cache._states.items():
        if address not in cache._dirty or not int(state.last_block):
            continue
        age = max(0, int(current_block) - int(state.last_block))
        if age > 2:
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
    *,
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


def _bounded_candidate_subset(
    full: List[Any],
    hot: List[Any],
    cold: List[Any],
    *,
    cap: int,
    ratio: float,
    current_block: int,
) -> Tuple[List[Any], List[Any]]:
    exploration_count = min(len(cold), max(8, int(round(len(full) * ratio))))
    exploration = _sample_exploration_by_family(
        cold,
        limit=exploration_count,
        current_block=int(current_block),
    )
    reserve = (
        min(len(exploration), max(8, cap // 4))
        if len(hot) + len(exploration) > cap and cold
        else 0
    )
    selected_hot = hot[:max(0, cap - reserve)]
    exploration_budget = max(0, cap - len(selected_hot))
    selected_exploration = exploration[:exploration_budget]
    combined: List[Any] = []
    for edge in [*selected_hot, *selected_exploration]:
        if edge not in combined:
            combined.append(edge)
    combined = combined[:cap]
    if not combined and full:
        combined = full[:cap]
    return combined, selected_exploration


def _candidate_edges(
    cache: Any,
    edges: List[Any],
    *,
    current_block: int,
    max_candidates: int = 768,
    exploration_ratio: float = 0.10,
) -> Tuple[List[Any], Dict[str, Any]]:
    """Return a bounded event-driven hot subgraph plus venue-balanced exploration."""
    full = list(edges or [])
    cap = max(32, min(2048, int(max_candidates)))
    ratio = max(0.02, min(0.50, float(exploration_ratio)))
    fresh_dirty_pools, affected_tokens = _fresh_dirty_frontier(
        cache, current_block=int(current_block)
    )
    if not fresh_dirty_pools:
        ordered, priority = cache.prioritize_edges(
            full, current_block=int(current_block)
        )
        priority["candidate_generation_mode"] = "full_graph"
        priority["candidate_edge_count"] = int(len(ordered))
        priority["candidate_edges_pruned"] = 0
        priority["exploration_edge_count"] = 0
        cache._last_candidate_metrics = dict(priority)
        return ordered, priority

    hot, cold = _partition_candidate_edges(
        cache,
        full,
        fresh_dirty_pools=fresh_dirty_pools,
        affected_tokens=affected_tokens,
    )
    combined, selected_exploration = _bounded_candidate_subset(
        full,
        hot,
        cold,
        cap=cap,
        ratio=ratio,
        current_block=int(current_block),
    )
    combined, priority = cache.prioritize_edges(
        combined, current_block=int(current_block)
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
