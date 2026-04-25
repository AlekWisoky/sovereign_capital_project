from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from typing import Any, Dict, List


def _push(store: Dict[str, List[int]], key: str, ts_ms: int, horizon_ms: int) -> None:
    cutoff = int(ts_ms) - int(horizon_ms)
    vals = [int(x) for x in list(store.get(key, [])) if int(x) >= cutoff]
    vals.append(int(ts_ms))
    store[key] = vals


class ExecutionRiskMemory:
    def __init__(self, path: str, *, horizon_ms: int = 20 * 60 * 1000):
        self.path = path
        self.horizon_ms = int(horizon_ms)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()

    def _blank(self) -> Dict[str, Dict[str, List[int]]]:
        return {"failures": {}}

    def _coerce_failures(self, value: Any) -> Dict[str, List[int]]:
        if not isinstance(value, dict):
            return {}
        out: Dict[str, List[int]] = {}
        for key, timestamps in value.items():
            key_str = str(key or "")
            if not key_str or ":" not in key_str or not isinstance(timestamps, list):
                continue
            vals: List[int] = []
            for ts in timestamps:
                try:
                    vals.append(int(ts))
                except (TypeError, ValueError):
                    continue
            if vals:
                out[key_str] = vals
        return out

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        if not isinstance(data, dict):
            return self._blank()
        return {"failures": self._coerce_failures(data.get("failures"))}

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def observe_failure(
        self,
        *,
        route_family: str = "",
        venue: str = "",
        token_pair: str = "",
        strategy_family: str = "",
        chain: str = "",
        pool_path: str = "",
        ts_ms: int | None = None,
    ) -> None:
        now_ms = int(ts_ms or time.time() * 1000)
        failures = dict(self._state.get("failures") or {})
        for key in [
            f"route:{route_family}",
            f"venue:{venue}",
            f"pair:{token_pair}",
            f"family:{strategy_family}",
            f"chain:{chain}",
            f"pool:{pool_path}",
        ]:
            if key.endswith(":"):
                continue
            _push(failures, key, now_ms, self.horizon_ms)
        self._state["failures"] = failures
        self._save()

    def penalty(
        self,
        *,
        route_family: str = "",
        venue: str = "",
        token_pair: str = "",
        strategy_family: str = "",
        chain: str = "",
        pool_path: str = "",
        ts_ms: int | None = None,
    ) -> Dict[str, Any]:
        now_ms = int(ts_ms or time.time() * 1000)
        cutoff = now_ms - self.horizon_ms
        failures = dict(self._state.get("failures") or {})
        total = 0
        reason_codes: List[str] = []
        for label, value in [
            ("route", route_family),
            ("venue", venue),
            ("pair", token_pair),
            ("family", strategy_family),
            ("chain", chain),
            ("pool", pool_path),
        ]:
            if not value:
                continue
            key = f"{label}:{value}"
            vals = [int(x) for x in list(failures.get(key, [])) if int(x) >= cutoff]
            failures[key] = vals
            if vals:
                total += len(vals)
                reason_codes.append(f"recent_{label}_failures")
        self._state["failures"] = failures
        self._save()
        penalty = min(0.45, 0.07 * float(total))
        return {
            "penalty": penalty,
            "reason_codes": sorted(set(reason_codes)),
            "recent_failures": total,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {"failures": dict(self._state.get("failures") or {})}
