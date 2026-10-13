from __future__ import annotations

from typing import Any, Dict, List


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
    positions = {family: 0 for family in families}
    selected: List[Any] = []
    while len(selected) < int(limit):
        advanced = False
        for family in families:
            position = positions[family]
            bucket = buckets[family]
            if position >= len(bucket):
                continue
            selected.append(bucket[position])
            positions[family] = position + 1
            advanced = True
            if len(selected) >= int(limit):
                break
        if not advanced:
            break
    return selected
