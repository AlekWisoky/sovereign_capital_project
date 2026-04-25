from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .models import OpportunityEnvelope


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _normalize_pending(pending_source: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if isinstance(pending_source, dict):
        source_rows = list(pending_source.get("rows") or [])
    elif isinstance(pending_source, (list, tuple)):
        source_rows = list(pending_source)
    else:
        source_rows = []
    for item in source_rows:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        tokens = set(str(x) for x in list(row.get("tokens") or []) if str(x))
        venues = set(str(x) for x in list(row.get("venues") or []) if str(x))
        pairs = set(str(x) for x in list(row.get("pairs") or []) if str(x))
        pool_keys = set(str(x) for x in list(row.get("pool_keys") or []) if str(x))
        if row.get("token_in"):
            tokens.add(str(row.get("token_in")))
        if row.get("token_out"):
            tokens.add(str(row.get("token_out")))
        if row.get("token"):
            tokens.add(str(row.get("token")))
        if row.get("venue"):
            venues.add(str(row.get("venue")))
        if row.get("pool"):
            pool_keys.add(str(row.get("pool")))
        if row.get("pair"):
            pairs.add(str(row.get("pair")))
        if row.get("token_in") and row.get("token_out"):
            pairs.add(f"{row.get('token_in')}/{row.get('token_out')}")
        row["tokens"] = sorted(tokens)
        row["venues"] = sorted(venues)
        row["pairs"] = sorted(pairs)
        row["pool_keys"] = sorted(pool_keys)
        row["route_family"] = str(row.get("route_family") or "")
        row["searcher_signature"] = str(row.get("searcher_signature") or row.get("from") or "")
        row["priority"] = float(row.get("priority") or row.get("ordering_prob") or 0.0)
        row["competition_relevance"] = float(row.get("competition_relevance") or 0.0)
        rows.append(row)
    rows.sort(
        key=lambda x: (
            -float(x.get("competition_relevance") or 0.0),
            -float(x.get("priority") or 0.0),
            str(x.get("hash") or x.get("searcher_signature") or ""),
        )
    )
    return rows[:10]


def _env_pair(envelope: OpportunityEnvelope) -> str:
    return "/".join(list(envelope.token_path[:2])) if envelope.token_path else ""


def _overlap_score(envelope: OpportunityEnvelope, pending: Dict[str, Any]) -> float:
    pending_tokens = set(str(x) for x in list(pending.get("tokens") or []) if str(x))
    pending_venues = set(str(x) for x in list(pending.get("venues") or []) if str(x))
    pending_pairs = set(str(x) for x in list(pending.get("pairs") or []) if str(x))
    pending_pools = set(str(x) for x in list(pending.get("pool_keys") or []) if str(x))
    env_tokens = set(str(x) for x in list(envelope.token_path or []) if str(x))
    env_venues = set(str(x) for x in list(envelope.venues or []) if str(x))
    env_pair = _env_pair(envelope)
    token_overlap = (
        len(env_tokens & pending_tokens) / float(max(1, len(env_tokens | pending_tokens)))
        if env_tokens or pending_tokens
        else 0.0
    )
    venue_overlap = (
        len(env_venues & pending_venues) / float(max(1, len(env_venues | pending_venues)))
        if env_venues or pending_venues
        else 0.0
    )
    pair_overlap = 1.0 if env_pair and env_pair in pending_pairs else 0.0
    pool_overlap = (
        len(env_venues & pending_pools) / float(max(1, len(env_venues | pending_pools)))
        if env_venues or pending_pools
        else 0.0
    )
    gas_pressure = _clip(float(pending.get("gas_price_pressure") or 0.0), 0.0, 1.0)
    route_overlap = (
        1.0
        if str(pending.get("route_family") or "")
        == str(getattr(envelope, "route_family", "") or "")
        and str(getattr(envelope, "route_family", "") or "")
        else 0.0
    )
    return _clip(
        (0.24 * token_overlap)
        + (0.20 * venue_overlap)
        + (0.18 * pair_overlap)
        + (0.14 * pool_overlap)
        + (0.12 * gas_pressure)
        + (0.12 * route_overlap)
        + 0.15 * float(pending.get("competition_relevance") or 0.0),
        0.0,
        1.0,
    )


def _cluster_key(row: Dict[str, Any]) -> Tuple[str, str, str, str, str]:
    return (
        "|".join(list(row.get("pool_keys") or [])[:2]),
        "|".join(list(row.get("pairs") or [])[:2]),
        "|".join(list(row.get("venues") or [])[:2]),
        str(row.get("route_family") or ""),
        str(row.get("searcher_signature") or ""),
    )


def _build_clusters(
    envelope: OpportunityEnvelope, pending: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    for row in pending:
        overlap = _overlap_score(envelope, row)
        if overlap <= 0:
            continue
        key = _cluster_key(row)
        grp = groups.setdefault(
            key,
            {
                "rows": [],
                "pools": set(),
                "pairs": set(),
                "venues": set(),
                "tokens": set(),
                "searcher_signatures": set(),
                "max_priority": 0.0,
                "impact": 0.0,
            },
        )
        grp["rows"].append(row)
        grp["pools"].update(set(row.get("pool_keys") or []))
        grp["pairs"].update(set(row.get("pairs") or []))
        grp["venues"].update(set(row.get("venues") or []))
        grp["tokens"].update(set(row.get("tokens") or []))
        if row.get("searcher_signature"):
            grp["searcher_signatures"].add(str(row.get("searcher_signature")))
        grp["max_priority"] = max(float(grp["max_priority"]), float(row.get("priority") or 0.0))
        grp["impact"] += overlap
    clusters: List[Dict[str, Any]] = []
    for key, grp in groups.items():
        base_impact = float(grp["impact"]) / float(max(1, len(grp["rows"])))
        ordering = _clip(
            0.40 + float(grp["max_priority"]) * 0.35 + 0.05 * max(0, len(grp["rows"]) - 1), 0.0, 1.0
        )
        impact = _clip(
            base_impact * 0.60
            + ordering * 0.25
            + 0.15 * min(1.0, len(grp["searcher_signatures"]) / 2.0),
            0.0,
            1.0,
        )
        clusters.append(
            {
                "cluster_id": "|".join(key),
                "impact": round(impact, 6),
                "ordering_probability": round(ordering, 6),
                "venues": sorted(grp["venues"]),
                "pairs": sorted(grp["pairs"]),
                "pools": sorted(grp["pools"]),
                "tokens": sorted(grp["tokens"]),
                "searcher_signatures": sorted(grp["searcher_signatures"]),
                "count": len(grp["rows"]),
            }
        )
    clusters.sort(key=lambda x: (-float(x["impact"]), -int(x["count"]), str(x["cluster_id"])))
    return clusters[:5]


def _scenario_edge(
    base_edge: float, impacts: List[float], envelope: OpportunityEnvelope, lane_hint: str
) -> float:
    lane = str(lane_hint or "").lower()
    lane_protection = (
        0.40 if lane == "private" else (0.22 if lane in {"protected_rpc", "protected"} else 0.0)
    )
    combined = 1.0
    for impact in impacts:
        fragility = float(getattr(envelope, "liquidity_fragility", 0.35) or 0.35)
        combined *= max(0.04, 1.0 - float(impact) * (0.28 + fragility * 0.24 - lane_protection))
    reserve_penalty = max(
        0.0, float(getattr(envelope, "liquidity_fragility", 0.35) or 0.35) * 0.10 * len(impacts)
    )
    return float(base_edge) * max(0.02, combined - reserve_penalty)


def _leg_risk(
    clusters: List[Dict[str, Any]], envelope: OpportunityEnvelope
) -> List[Dict[str, Any]]:
    out = []
    for venue in list(envelope.venues or []):
        impact = max(
            [
                float(c.get("impact") or 0.0)
                for c in clusters
                if venue in list(c.get("venues") or [])
            ]
            + [0.0]
        )
        out.append(
            {
                "venue": venue,
                "distortion": round(
                    _clip(
                        impact * 0.75
                        + float(getattr(envelope, "liquidity_fragility", 0.35) or 0.35) * 0.20,
                        0.0,
                        1.0,
                    ),
                    6,
                ),
                "fragile": bool(impact >= 0.55),
            }
        )
    return out


def evaluate_adversarial_state(
    *,
    envelope: OpportunityEnvelope,
    pending_source: Iterable[Dict[str, Any]] | None,
    base_expected_value: float,
    lane_hint: str,
) -> Dict[str, Any]:
    pending = _normalize_pending(pending_source)
    clusters = _build_clusters(envelope, pending)
    base_pending_rate = (
        float(((pending_source or {}).get("summary") or {}).get("pending_rate") or 0.0)
        if isinstance(pending_source, dict)
        else 0.0
    )
    if not clusters:
        relay_necessity = bool(
            envelope.mempool_copy_risk >= 0.7
            or envelope.private_send_preference
            or base_pending_rate >= 0.65
        )
        post_edge = float(base_expected_value) * max(
            0.22, 1.0 - envelope.mempool_copy_risk * 0.22 - base_pending_rate * 0.10
        )
        return {
            "clusters": [],
            "conflict_count": 0,
            "scenarios": [],
            "stale_probability": round(
                _clip(envelope.mempool_copy_risk * 0.35 + base_pending_rate * 0.15, 0.0, 0.99), 6
            ),
            "interference_probability": round(
                _clip(envelope.mempool_copy_risk * 0.45 + base_pending_rate * 0.20, 0.0, 0.99), 6
            ),
            "post_ordering_realized_edge": round(post_edge, 6),
            "copy_risk": round(
                _clip(envelope.mempool_copy_risk + base_pending_rate * 0.10, 0.0, 0.99), 6
            ),
            "relay_necessity": relay_necessity,
            "requires_private_lane": relay_necessity and str(lane_hint or "").lower() == "public",
            "worst_case_edge": round(post_edge, 6),
            "leg_risk": _leg_risk([], envelope),
            "route_invalid_causes": [],
        }
    top = clusters[:4]
    scenario_defs: List[Tuple[int, ...]] = [(0,), (1,), (0, 1)]
    if len(top) >= 3:
        scenario_defs += [(2,), (0, 2), (1, 2)]
    if len(top) >= 4:
        scenario_defs += [(3,), (0, 3)]
    scenarios: List[Dict[str, Any]] = []
    seen = set()
    for idxs in scenario_defs:
        idxs = tuple(i for i in idxs if i < len(top))
        if not idxs or idxs in seen:
            continue
        seen.add(idxs)
        impacts = [float(top[i]["impact"]) for i in idxs]
        edge = _scenario_edge(float(base_expected_value), impacts, envelope, lane_hint)
        scenarios.append(
            {
                "scenario": "-".join(str(i) for i in idxs),
                "clusters": [top[i]["cluster_id"] for i in idxs],
                "edge_after": round(edge, 6),
                "ordering_mass": round(
                    sum(float(top[i]["ordering_probability"]) for i in idxs) / float(len(idxs)), 6
                ),
            }
        )
    scenarios.sort(key=lambda x: (float(x["edge_after"]), str(x["scenario"])))
    impact_sum = sum(float(x["impact"]) for x in top)
    avg_edge = sum(float(x["edge_after"]) for x in scenarios) / float(max(1, len(scenarios)))
    worst_edge = min([float(x["edge_after"]) for x in scenarios] + [float(base_expected_value)])
    base_copy_risk = float(envelope.mempool_copy_risk)
    private_factor = (
        0.40
        if str(lane_hint or "").lower() == "private"
        else (0.70 if str(lane_hint or "").lower() in {"protected_rpc", "protected"} else 1.0)
    )
    searcher_overlap = 1.0 if any(list(x.get("searcher_signatures") or []) for x in top) else 0.0
    copy_risk = _clip(
        base_copy_risk * private_factor
        + impact_sum * 0.15
        + searcher_overlap * 0.10
        + base_pending_rate * 0.10,
        0.0,
        0.99,
    )
    stale_probability = _clip(
        impact_sum * 0.20
        + copy_risk * 0.35
        + (350.0 / float(max(350, getattr(envelope, "latency_half_life_ms", 800)))) * 0.10,
        0.0,
        0.99,
    )
    interference_probability = _clip(
        impact_sum * 0.34 + copy_risk * 0.30 + base_pending_rate * 0.15, 0.0, 0.99
    )
    relay_necessity = bool(
        copy_risk >= 0.55
        or stale_probability >= 0.45
        or envelope.private_send_preference
        or worst_edge <= 0.0
    )
    leg_risk = _leg_risk(top, envelope)
    route_invalid_causes = [
        f"leg:{row['venue']}:adversarial_fragile" for row in leg_risk if bool(row.get("fragile"))
    ]
    if worst_edge <= 0.0:
        route_invalid_causes.append("post_ordering_negative_ev")
    return {
        "clusters": top,
        "conflict_count": len(top),
        "scenarios": scenarios,
        "stale_probability": round(stale_probability, 6),
        "interference_probability": round(interference_probability, 6),
        "post_ordering_realized_edge": round(avg_edge, 6),
        "copy_risk": round(copy_risk, 6),
        "relay_necessity": relay_necessity,
        "requires_private_lane": relay_necessity and str(lane_hint or "").lower() == "public",
        "worst_case_edge": round(worst_edge, 6),
        "leg_risk": leg_risk,
        "route_invalid_causes": route_invalid_causes,
    }
