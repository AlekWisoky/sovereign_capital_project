from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List


class EngineMetrics:
    def summarize(self, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        grouped = defaultdict(lambda: {"count": 0, "projected": 0.0, "realized": 0.0})
        for row in rows:
            payload = row.get("payload") or {}
            engine = str(payload.get("engine_type") or "")
            if not engine:
                continue
            g = grouped[engine]
            g["count"] += 1
            g["projected"] += float(payload.get("projected_realized_edge_usd") or 0.0)
            g["realized"] += float(payload.get("actual_realized_edge_usd") or 0.0)
        items: List[Dict[str, Any]] = []
        for engine, data in grouped.items():
            proj = float(data["projected"])
            real = float(data["realized"])
            items.append(
                {
                    "engine_type": engine,
                    "count": int(data["count"]),
                    "projected_realized_edge_usd": round(proj, 6),
                    "actual_realized_edge_usd": round(real, 6),
                    "realization_ratio": round(real / proj, 6) if proj > 0 else 0.0,
                }
            )
        items.sort(key=lambda x: (-float(x["actual_realized_edge_usd"]), x["engine_type"]))
        return {"engines": items}
