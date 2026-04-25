from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_INT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_TELEMETRY_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except _SAFE_FLOAT_EXCEPTIONS:
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except _SAFE_INT_EXCEPTIONS:
        return default


class ExecutionTelemetryStore:
    """Deterministic file-backed execution capture telemetry.

    Keeps rolling metrics by route family / venue / lane / chain and surfaces
    feedback signals for capture scoring. Updates are append + aggregate, never
    influence core execution semantics outside the capture layer.
    """

    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain)
        self._path = os.path.join(data_dir, "execution_capture", f"telemetry_{self.chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {
            "updated_ts": int(time.time()),
            "route_family": {},
            "venue": {},
            "lane": {},
            "relay": {},
            "rpc": {},
        }

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._blank()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except _SAFE_TELEMETRY_LOAD_EXCEPTIONS:
            return self._blank()
        if not isinstance(data, dict):
            return self._blank()
        blank = self._blank()
        blank.update(data)
        return blank

    def _persist(self) -> None:
        self._state["updated_ts"] = int(time.time())
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _bucket(self, section: str, key: str) -> Dict[str, Any]:
        sec = self._state.setdefault(section, {})
        item = sec.get(key)
        if not isinstance(item, dict):
            item = {
                "attempts": 0,
                "successes": 0,
                "drops": 0,
                "reverts": 0,
                "stales": 0,
                "timeouts": 0,
                "slippage_delta_bps_sum": 0.0,
                "realized_pnl_usd_sum": 0.0,
                "expected_pnl_usd_sum": 0.0,
                "quote_drift_bps_sum": 0.0,
                "latency_ms_sum": 0.0,
                "sample_count": 0,
            }
            sec[key] = item
        return item

    def _update_bucket(self, bucket: Dict[str, Any], row: Dict[str, Any]) -> None:
        bucket["attempts"] = _safe_int(bucket.get("attempts")) + 1
        bucket["sample_count"] = _safe_int(bucket.get("sample_count")) + 1
        if bool(row.get("success")):
            bucket["successes"] = _safe_int(bucket.get("successes")) + 1
        if bool(row.get("drop")):
            bucket["drops"] = _safe_int(bucket.get("drops")) + 1
        if bool(row.get("revert")):
            bucket["reverts"] = _safe_int(bucket.get("reverts")) + 1
        if bool(row.get("stale")):
            bucket["stales"] = _safe_int(bucket.get("stales")) + 1
        if bool(row.get("timeout")):
            bucket["timeouts"] = _safe_int(bucket.get("timeouts")) + 1
        bucket["slippage_delta_bps_sum"] = _safe_float(
            bucket.get("slippage_delta_bps_sum")
        ) + _safe_float(row.get("slippage_delta_bps"))
        bucket["realized_pnl_usd_sum"] = _safe_float(
            bucket.get("realized_pnl_usd_sum")
        ) + _safe_float(row.get("realized_pnl_usd"))
        bucket["expected_pnl_usd_sum"] = _safe_float(
            bucket.get("expected_pnl_usd_sum")
        ) + _safe_float(row.get("expected_pnl_usd"))
        bucket["quote_drift_bps_sum"] = _safe_float(
            bucket.get("quote_drift_bps_sum")
        ) + _safe_float(row.get("quote_drift_bps"))
        bucket["latency_ms_sum"] = _safe_float(bucket.get("latency_ms_sum")) + _safe_float(
            row.get("latency_ms")
        )

    def record(
        self,
        *,
        route_family: str,
        venues: Iterable[str],
        lane: str,
        relay: str,
        rpc: str,
        success: bool,
        drop: bool,
        revert: bool,
        stale: bool,
        timeout: bool,
        slippage_delta_bps: float,
        realized_pnl_usd: float,
        expected_pnl_usd: float,
        quote_drift_bps: float,
        latency_ms: float,
    ) -> None:
        row = {
            "success": bool(success),
            "drop": bool(drop),
            "revert": bool(revert),
            "stale": bool(stale),
            "timeout": bool(timeout),
            "slippage_delta_bps": float(slippage_delta_bps),
            "realized_pnl_usd": float(realized_pnl_usd),
            "expected_pnl_usd": float(expected_pnl_usd),
            "quote_drift_bps": float(quote_drift_bps),
            "latency_ms": float(latency_ms),
        }
        self._update_bucket(self._bucket("route_family", str(route_family or "unknown")), row)
        self._update_bucket(self._bucket("lane", str(lane or "UNKNOWN")), row)
        self._update_bucket(self._bucket("relay", str(relay or "default")), row)
        self._update_bucket(self._bucket("rpc", str(rpc or "default")), row)
        for venue in list(venues or []):
            self._update_bucket(self._bucket("venue", str(venue or "unknown")), row)
        self._persist()

    def summary(self, section: str, key: str) -> Dict[str, float]:
        item = ((self._state.get(section) or {}) if isinstance(self._state, dict) else {}).get(
            key
        ) or {}
        if not isinstance(item, dict):
            item = {}
        attempts = max(0, _safe_int(item.get("attempts")))
        samples = max(1, _safe_int(item.get("sample_count")))
        success_rate = (_safe_int(item.get("successes")) / attempts) if attempts > 0 else 0.65
        stale_rate = (_safe_int(item.get("stales")) / attempts) if attempts > 0 else 0.05
        timeout_rate = (_safe_int(item.get("timeouts")) / attempts) if attempts > 0 else 0.02
        revert_rate = (_safe_int(item.get("reverts")) / attempts) if attempts > 0 else 0.05
        drop_rate = (_safe_int(item.get("drops")) / attempts) if attempts > 0 else 0.0
        avg_slippage_delta_bps = _safe_float(item.get("slippage_delta_bps_sum")) / float(samples)
        avg_quote_drift_bps = _safe_float(item.get("quote_drift_bps_sum")) / float(samples)
        avg_latency_ms = _safe_float(item.get("latency_ms_sum")) / float(samples)
        avg_realized_pnl_usd = _safe_float(item.get("realized_pnl_usd_sum")) / float(samples)
        avg_expected_pnl_usd = _safe_float(item.get("expected_pnl_usd_sum")) / float(samples)
        venue_quality = max(
            0.2,
            min(
                1.2,
                (0.60 * success_rate) + (0.25 * (1.0 - stale_rate)) + (0.15 * (1.0 - revert_rate)),
            ),
        )
        return {
            "attempts": float(attempts),
            "success_rate": float(success_rate),
            "stale_rate": float(stale_rate),
            "timeout_rate": float(timeout_rate),
            "revert_rate": float(revert_rate),
            "drop_rate": float(drop_rate),
            "avg_slippage_delta_bps": float(avg_slippage_delta_bps),
            "avg_quote_drift_bps": float(avg_quote_drift_bps),
            "avg_latency_ms": float(avg_latency_ms),
            "avg_realized_pnl_usd": float(avg_realized_pnl_usd),
            "avg_expected_pnl_usd": float(avg_expected_pnl_usd),
            "venue_quality": float(venue_quality),
        }

    def combined_feedback(
        self, *, route_family: str, venues: Iterable[str], lane: str
    ) -> Dict[str, float]:
        route = self.summary("route_family", str(route_family or "unknown"))
        lane_s = self.summary("lane", str(lane or "UNKNOWN"))
        venue_summaries = [self.summary("venue", str(v or "unknown")) for v in list(venues or [])]
        if venue_summaries:
            venue_quality = sum(v["venue_quality"] for v in venue_summaries) / float(
                len(venue_summaries)
            )
            venue_success = sum(v["success_rate"] for v in venue_summaries) / float(
                len(venue_summaries)
            )
            venue_stale = sum(v["stale_rate"] for v in venue_summaries) / float(
                len(venue_summaries)
            )
        else:
            venue_quality = 0.80
            venue_success = 0.65
            venue_stale = 0.05
        return {
            "route_success_rate": float(route["success_rate"]),
            "route_stale_rate": float(route["stale_rate"]),
            "route_quote_drift_bps": float(route["avg_quote_drift_bps"]),
            "lane_success_rate": float(lane_s["success_rate"]),
            "lane_timeout_rate": float(lane_s["timeout_rate"]),
            "lane_stale_rate": float(lane_s["stale_rate"]),
            "lane_revert_rate": float(lane_s["revert_rate"]),
            "venue_quality": float(venue_quality),
            "venue_success_rate": float(venue_success),
            "venue_stale_rate": float(venue_stale),
        }

    def analytics_series(self) -> Dict[str, Any]:
        lanes = (self._state.get("lane") or {}) if isinstance(self._state, dict) else {}
        lane_success = []
        for key in sorted(lanes.keys()):
            s = self.summary("lane", str(key))
            lane_success.append(
                {
                    "lane": str(key),
                    "successPct": round(s["success_rate"] * 100.0, 2),
                    "stalePct": round(s["stale_rate"] * 100.0, 2),
                }
            )
        venues = (self._state.get("venue") or {}) if isinstance(self._state, dict) else {}
        venue_quality = []
        for key in sorted(venues.keys())[:12]:
            s = self.summary("venue", str(key))
            venue_quality.append(
                {
                    "venue": str(key),
                    "quality": round(s["venue_quality"], 4),
                    "successPct": round(s["success_rate"] * 100.0, 2),
                }
            )
        return {
            "laneSuccess": lane_success,
            "venueQuality": venue_quality,
        }
