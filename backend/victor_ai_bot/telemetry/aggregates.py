from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


def summarize_realization(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_family: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {
            "projected": 0.0,
            "realized": 0.0,
            "count": 0.0,
            "successes": 0.0,
            "drops": 0.0,
            "false_admissions": 0.0,
            "false_drops": 0.0,
        }
    )
    for row in events:
        payload = row.get("payload") or {}
        fam = str(payload.get("route_family") or payload.get("strategy_family") or "unknown")
        b = by_family[fam]
        b["projected"] += float(payload.get("projected_realized_edge_usd") or 0.0)
        b["realized"] += float(payload.get("actual_realized_edge_usd") or 0.0)
        b["count"] += 1.0
        b["successes"] += 1.0 if bool(payload.get("ok")) else 0.0
        b["drops"] += 1.0 if bool(payload.get("dropped")) else 0.0
        b["false_admissions"] += float(payload.get("false_admission") or 0.0)
        b["false_drops"] += float(payload.get("false_drop") or 0.0)
    out = []
    for fam, b in by_family.items():
        projected = float(b["projected"])
        realized = float(b["realized"])
        realization_ratio = (realized / projected) if projected > 0 else 0.0
        out.append(
            {
                "family": fam,
                "count": int(b["count"]),
                "projectedRealizedEdgeUsd": round(projected, 6),
                "actualRealizedEdgeUsd": round(realized, 6),
                "realizationRatio": round(realization_ratio, 6),
                "successRate": round((b["successes"] / max(1.0, b["count"])), 6),
                "dropRate": round((b["drops"] / max(1.0, b["count"])), 6),
                "falseAdmissionRate": round((b["false_admissions"] / max(1.0, b["count"])), 6),
                "falseDropRate": round((b["false_drops"] / max(1.0, b["count"])), 6),
            }
        )
    out.sort(key=lambda x: (-x["actualRealizedEdgeUsd"], x["family"]))
    return {"families": out}


def summarize_agents(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    stats: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"count": 0.0, "followed": 0.0, "realized": 0.0, "precision_hits": 0.0}
    )
    for row in events:
        payload = row.get("payload") or {}
        for contrib in list(payload.get("contributors") or []):
            name = str(contrib.get("agent") or "unknown")
            s = stats[name]
            s["count"] += 1.0
            s["followed"] += 1.0 if bool(contrib.get("followed")) else 0.0
            s["realized"] += float(contrib.get("realized_pnl_impact_usd") or 0.0)
            s["precision_hits"] += 1.0 if bool(contrib.get("precision_hit")) else 0.0
    out = []
    for name, s in stats.items():
        out.append(
            {
                "agent": name,
                "count": int(s["count"]),
                "followRate": round(s["followed"] / max(1.0, s["count"]), 6),
                "precision": round(s["precision_hits"] / max(1.0, s["count"]), 6),
                "realizedImpactUsd": round(s["realized"], 6),
            }
        )
    out.sort(key=lambda x: (-x["realizedImpactUsd"], x["agent"]))
    return {"agents": out}
