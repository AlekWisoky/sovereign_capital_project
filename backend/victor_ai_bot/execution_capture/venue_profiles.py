from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable

_SAFE_VENUE_PROFILE_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)

from ..persistence.db import PersistenceDB
from ..persistence.repositories.venue_repository import VenueRepository


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return default if b <= 0 else float(a) / float(b)


class VenueReliabilityStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "execution_capture", f"venue_profiles_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._state = self._load()
        self._db = PersistenceDB(os.path.join(data_dir, "state", "xdv_runtime_state.sqlite3"))
        self._repo = VenueRepository(self._db, chain=chain)

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return data if isinstance(data, dict) else {}
        except _SAFE_VENUE_PROFILE_LOAD_EXCEPTIONS:
            return {}

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe(
        self,
        *,
        venue: str,
        success: bool,
        stale_quote: bool,
        slippage_bias_bps: float,
        latency_ms: float,
        route_success_contribution: float,
    ) -> None:
        v = str(venue or "")
        if not v:
            return
        s = dict(self._state.get(v) or {})
        s["count"] = int(s.get("count") or 0) + 1
        s["successes"] = int(s.get("successes") or 0) + (1 if success else 0)
        s["failures"] = int(s.get("failures") or 0) + (0 if success else 1)
        s["stale_quotes"] = int(s.get("stale_quotes") or 0) + (1 if stale_quote else 0)
        s["total_slippage_bias"] = float(s.get("total_slippage_bias") or 0.0) + float(
            slippage_bias_bps
        )
        s["total_latency_ms"] = float(s.get("total_latency_ms") or 0.0) + float(latency_ms)
        s["route_success_contribution"] = float(s.get("route_success_contribution") or 0.0) + float(
            route_success_contribution
        )
        self._state[v] = s
        self._save()
        self._repo.upsert(v, s)

    def profile(self, *, venue: str) -> Dict[str, float]:
        rows = {str(r.get("venue") or ""): r for r in self._repo.rows()}
        s = dict(rows.get(str(venue or "")) or self._state.get(str(venue or "")) or {})
        count = max(1, int(s.get("count") or 0))
        fill_reliability = _safe_div(float(s.get("successes") or 0), count, 0.65)
        failure_rate = _safe_div(float(s.get("failures") or 0), count, 0.0)
        stale_rate = _safe_div(float(s.get("stale_quotes") or 0), count, 0.0)
        slippage_bias = _safe_div(float(s.get("total_slippage_bias") or 0.0), count, 0.0)
        latency_sensitivity = min(
            1.0, _safe_div(float(s.get("total_latency_ms") or 0.0), count, 1500.0)
        )
        route_success_contribution = _safe_div(
            float(s.get("route_success_contribution") or 0.0), count, 0.7
        )
        venue_reliability_score = max(
            0.2,
            min(
                1.2,
                0.55 * fill_reliability
                + 0.20 * (1.0 - failure_rate)
                + 0.15 * (1.0 - stale_rate)
                + 0.10 * route_success_contribution,
            ),
        )
        return {
            "venue_reliability_score": float(venue_reliability_score),
            "venue_slippage_bias": float(slippage_bias),
            "venue_failure_penalty": float(min(0.5, failure_rate + 0.5 * stale_rate)),
            "fill_reliability": float(fill_reliability),
            "latency_sensitivity": float(latency_sensitivity),
        }

    def combined_profile(self, venues: Iterable[str]) -> Dict[str, float]:
        vals = [self.profile(venue=str(v)) for v in list(venues or []) if str(v)]
        if not vals:
            return {
                "venue_reliability_score": 0.75,
                "venue_slippage_bias": 0.0,
                "venue_failure_penalty": 0.0,
                "fill_reliability": 0.65,
                "latency_sensitivity": 0.25,
            }
        n = float(len(vals))
        return {
            "venue_reliability_score": sum(v["venue_reliability_score"] for v in vals) / n,
            "venue_slippage_bias": sum(v["venue_slippage_bias"] for v in vals) / n,
            "venue_failure_penalty": sum(v["venue_failure_penalty"] for v in vals) / n,
            "fill_reliability": sum(v["fill_reliability"] for v in vals) / n,
            "latency_sensitivity": sum(v["latency_sensitivity"] for v in vals) / n,
        }

    def snapshot(self) -> Dict[str, Any]:
        out = []
        seen = set()
        for row in self._repo.rows():
            venue = str(row.get("venue") or "")
            out.append({"venue": venue, **self.profile(venue=venue)})
            seen.add(venue)
        for venue in sorted(self._state.keys()):
            if venue in seen:
                continue
            out.append({"venue": venue, **self.profile(venue=venue)})
        return {"venues": out}
