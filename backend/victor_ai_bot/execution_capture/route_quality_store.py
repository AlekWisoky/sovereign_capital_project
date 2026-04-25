from __future__ import annotations

import json
import os
from typing import Any, Dict, List

_SAFE_ROUTE_QUALITY_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class RouteQualityStore:
    def __init__(self, *, data_dir: str, chain: str):
        self._path = os.path.join(data_dir, "execution_capture", f"route_quality_{chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return {"items": {}}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {"items": {}}
        except _SAFE_ROUTE_QUALITY_LOAD_EXCEPTIONS:
            return {"items": {}}

    def _persist(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _key(
        self,
        *,
        route_family: str,
        venue_subset: List[str],
        split_signature: str,
        pair: str,
        size_bucket: str,
        latency_class: str,
    ) -> str:
        return "|".join(
            [
                str(route_family),
                ",".join(sorted(str(v) for v in venue_subset)),
                str(split_signature),
                str(pair),
                str(size_bucket),
                str(latency_class),
            ]
        )

    def observe(
        self,
        *,
        route_family: str,
        venue_subset: list[str],
        split_signature: str,
        ok: bool,
        realized_edge_usd: float,
        pair: str = "",
        size_bucket: str = "medium",
        latency_class: str = "moderate",
    ) -> None:
        key = self._key(
            route_family=str(route_family),
            venue_subset=list(venue_subset),
            split_signature=str(split_signature),
            pair=str(pair),
            size_bucket=str(size_bucket),
            latency_class=str(latency_class),
        )
        item = dict((self._state.get("items") or {}).get(key) or {})
        item["route_family"] = str(route_family)
        item["venue_subset"] = sorted(str(v) for v in venue_subset)
        item["split_signature"] = str(split_signature)
        item["pair"] = str(pair)
        item["size_bucket"] = str(size_bucket)
        item["latency_class"] = str(latency_class)
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["successes"] = int(item.get("successes") or 0) + (1 if ok else 0)
        item["realized_edge_usd_sum"] = float(item.get("realized_edge_usd_sum") or 0.0) + float(
            realized_edge_usd
        )
        self._state.setdefault("items", {})[key] = item
        self._persist()

    def summary(
        self,
        *,
        route_family: str,
        venue_subset: list[str],
        split_signature: str,
        pair: str = "",
        size_bucket: str = "medium",
        latency_class: str = "moderate",
    ) -> Dict[str, Any]:
        key = self._key(
            route_family=str(route_family),
            venue_subset=list(venue_subset),
            split_signature=str(split_signature),
            pair=str(pair),
            size_bucket=str(size_bucket),
            latency_class=str(latency_class),
        )
        item = dict((self._state.get("items") or {}).get(key) or {})
        attempts = int(item.get("attempts") or 0)
        success_rate = (
            float(item.get("successes") or 0) / float(max(1, attempts)) if attempts else 0.65
        )
        mean_edge = (
            float(item.get("realized_edge_usd_sum") or 0.0) / float(max(1, attempts))
            if attempts
            else 0.0
        )
        quality = _clip(
            0.68 * success_rate
            + 0.22 * _clip(0.5 + mean_edge / 10.0, 0.0, 1.0)
            + 0.10 * (1.0 if attempts >= 3 else 0.75),
            0.05,
            1.25,
        )
        return {
            "attempts": attempts,
            "success_rate": round(success_rate, 6),
            "mean_realized_edge_usd": round(mean_edge, 6),
            "quality": round(quality, 6),
        }

    def snapshot(self) -> Dict[str, Any]:
        items = []
        for key, value in sorted((self._state.get("items") or {}).items()):
            if not isinstance(value, dict):
                continue
            items.append(
                {
                    "key": key,
                    **value,
                    **self.summary(
                        route_family=str(value.get("route_family") or ""),
                        venue_subset=list(value.get("venue_subset") or []),
                        split_signature=str(value.get("split_signature") or "default"),
                        pair=str(value.get("pair") or ""),
                        size_bucket=str(value.get("size_bucket") or "medium"),
                        latency_class=str(value.get("latency_class") or "moderate"),
                    ),
                }
            )
        return {"items": items}
