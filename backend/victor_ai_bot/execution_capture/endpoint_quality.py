from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Iterable, List


_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_INT_EXCEPTIONS = (TypeError, ValueError)
_SAFE_ENDPOINT_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


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


class EndpointQualityStore:
    """Rolling deterministic endpoint/relay quality model.

    Tracks quality by lane + endpoint and surfaces best endpoint selection and
    latency pressure as execution inputs.
    """

    def __init__(self, *, data_dir: str, chain: str):
        self.chain = str(chain)
        self._path = os.path.join(
            data_dir, "execution_capture", f"endpoint_quality_{self.chain}.json"
        )
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Any]:
        return {"updated_ts": int(time.time()), "lanes": {}, "relays": {}}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._blank()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            blank = self._blank()
            if isinstance(data, dict):
                blank.update(data)
            return blank
        except _SAFE_ENDPOINT_LOAD_EXCEPTIONS:
            return self._blank()

    def _persist(self) -> None:
        self._state["updated_ts"] = int(time.time())
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _bucket(self, lane: str, endpoint: str, *, relay: bool = False) -> Dict[str, Any]:
        root = self._state.setdefault("relays" if relay else "lanes", {})
        lane_root = root.setdefault(str(lane or "UNKNOWN").upper(), {})
        item = lane_root.get(endpoint)
        if not isinstance(item, dict):
            item = {
                "attempts": 0,
                "successes": 0,
                "timeouts": 0,
                "errors": 0,
                "latency_ms_ema": 0.0,
                "recent_success": 0.0,
                "quality": 0.55,
                "updated_ts": int(time.time()),
            }
            lane_root[endpoint] = item
        return item

    def observe(
        self,
        *,
        lane: str,
        endpoint: str,
        latency_ms: float,
        ok: bool,
        timeout: bool = False,
        error: bool = False,
        relay: bool = False,
    ) -> None:
        if not endpoint:
            return
        bucket = self._bucket(str(lane or "UNKNOWN"), str(endpoint), relay=relay)
        attempts = _safe_int(bucket.get("attempts")) + 1
        bucket["attempts"] = attempts
        if ok:
            bucket["successes"] = _safe_int(bucket.get("successes")) + 1
        if timeout:
            bucket["timeouts"] = _safe_int(bucket.get("timeouts")) + 1
        if error:
            bucket["errors"] = _safe_int(bucket.get("errors")) + 1
        prev_ema = _safe_float(bucket.get("latency_ms_ema"))
        lat = max(1.0, float(latency_ms or 0.0))
        alpha = 0.35
        bucket["latency_ms_ema"] = (
            lat if prev_ema <= 0 else (alpha * lat + (1.0 - alpha) * prev_ema)
        )
        prev_recent = _safe_float(bucket.get("recent_success"), 0.5)
        bucket["recent_success"] = (0.25 * (1.0 if ok else 0.0)) + (0.75 * prev_recent)
        success_rate = _safe_int(bucket.get("successes")) / float(max(1, attempts))
        timeout_rate = _safe_int(bucket.get("timeouts")) / float(max(1, attempts))
        error_rate = _safe_int(bucket.get("errors")) / float(max(1, attempts))
        latency_score = max(0.0, min(1.0, 1.0 - (float(bucket["latency_ms_ema"]) / 2500.0)))
        bucket["quality"] = round(
            max(
                0.05,
                min(
                    1.0,
                    (0.40 * success_rate)
                    + (0.25 * latency_score)
                    + (0.20 * bucket["recent_success"])
                    + (0.10 * (1.0 - timeout_rate))
                    + (0.05 * (1.0 - error_rate)),
                ),
            ),
            6,
        )
        bucket["updated_ts"] = int(time.time())
        self._persist()

    def summary(self, *, lane: str, endpoint: str, relay: bool = False) -> Dict[str, Any]:
        root = self._state.get("relays" if relay else "lanes") or {}
        bucket = (
            (root.get(str(lane or "UNKNOWN").upper()) or {}) if isinstance(root, dict) else {}
        ).get(str(endpoint)) or {}
        if not isinstance(bucket, dict):
            bucket = {}
        attempts = max(0, _safe_int(bucket.get("attempts")))
        success_rate = (
            _safe_int(bucket.get("successes")) / float(max(1, attempts)) if attempts else 0.65
        )
        timeout_rate = (
            _safe_int(bucket.get("timeouts")) / float(max(1, attempts)) if attempts else 0.05
        )
        error_rate = _safe_int(bucket.get("errors")) / float(max(1, attempts)) if attempts else 0.05
        return {
            "attempts": attempts,
            "success_rate": round(success_rate, 6),
            "timeout_rate": round(timeout_rate, 6),
            "error_rate": round(error_rate, 6),
            "latency_ms_ema": round(_safe_float(bucket.get("latency_ms_ema"), 850.0) or 850.0, 6),
            "recent_success": round(_safe_float(bucket.get("recent_success"), 0.65) or 0.65, 6),
            "quality": round(_safe_float(bucket.get("quality"), 0.55) or 0.55, 6),
        }

    def ranked(
        self, *, lane: str, endpoints: Iterable[str], relay: bool = False
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ordered = []
        seen = set()
        for raw in list(endpoints or []):
            endpoint = str(raw or "")
            if not endpoint or endpoint in seen:
                continue
            seen.add(endpoint)
            ordered.append(endpoint)
        for idx, endpoint in enumerate(ordered):
            s = self.summary(lane=lane, endpoint=endpoint, relay=relay)
            out.append({"endpoint": endpoint, "input_rank": idx, **s})
        out.sort(
            key=lambda x: (
                -float(x["quality"]),
                float(x["latency_ms_ema"]),
                -float(x["success_rate"]),
                int(x.get("input_rank", 999)),
                str(x["endpoint"]),
            )
        )
        return out

    def latency_pressure(self, *, lane: str, endpoints: Iterable[str]) -> Dict[str, Any]:
        ranked = self.ranked(lane=lane, endpoints=endpoints)
        if not ranked:
            return {"pressure": 0.15, "class": "unknown", "best_latency_ms": 900.0}
        best = ranked[0]
        pressure = max(
            0.0,
            min(
                1.0,
                (float(best["latency_ms_ema"]) - 350.0) / 1800.0
                + float(best["timeout_rate"]) * 0.65
                + max(0.0, 0.55 - float(best["quality"])),
            ),
        )
        pclass = "normal"
        if pressure >= 0.70:
            pclass = "severe"
        elif pressure >= 0.40:
            pclass = "elevated"
        return {
            "pressure": round(pressure, 6),
            "class": pclass,
            "best_latency_ms": round(float(best["latency_ms_ema"]), 6),
        }

    def choose(
        self, *, lane: str, endpoints: Iterable[str], relays: Iterable[str] | None = None
    ) -> Dict[str, Any]:
        ranked = self.ranked(lane=lane, endpoints=endpoints)
        relay_ranked = (
            self.ranked(lane=lane, endpoints=list(relays or []), relay=True) if relays else []
        )
        pressure = self.latency_pressure(lane=lane, endpoints=endpoints)
        best = (
            ranked[0]
            if ranked
            else {
                "endpoint": "",
                "quality": 0.0,
                "latency_ms_ema": 0.0,
                "success_rate": 0.0,
                "timeout_rate": 0.0,
            }
        )
        best_relay = relay_ranked[0] if relay_ranked else {"endpoint": "", "quality": 0.0}
        return {
            "lane": str(lane or "UNKNOWN").upper(),
            "endpoint": str(best.get("endpoint") or ""),
            "relay": str(best_relay.get("endpoint") or ""),
            "endpoint_quality": round(float(best.get("quality") or 0.0), 6),
            "relay_quality": round(float(best_relay.get("quality") or 0.0), 6),
            "measured_latency_ms": round(float(best.get("latency_ms_ema") or 0.0), 6),
            "pressure": float(pressure["pressure"]),
            "pressure_class": str(pressure["class"]),
            "candidates": ranked[:5],
            "relay_candidates": relay_ranked[:5],
        }

    def snapshot(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._state))
