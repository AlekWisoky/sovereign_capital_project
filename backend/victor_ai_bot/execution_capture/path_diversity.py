from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List

_SAFE_PATH_DIVERSITY_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


class PathDiversityMemory:
    def __init__(self, path: str, *, horizon_ms: int = 10 * 60 * 1000):
        self.path = path
        self.horizon_ms = int(horizon_ms)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()

    def _load(self) -> Dict[str, List[int]]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            return {str(k): [int(x) for x in list(v or [])] for k, v in dict(data).items()}
        except _SAFE_PATH_DIVERSITY_LOAD_EXCEPTIONS:
            return {}

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def _prune(self, now_ms: int) -> None:
        cutoff = int(now_ms) - int(self.horizon_ms)
        self._state = {
            k: [ts for ts in vals if int(ts) >= cutoff]
            for k, vals in self._state.items()
            if [ts for ts in vals if int(ts) >= cutoff]
        }

    def observe(self, path_id: str, *, ts_ms: int | None = None) -> None:
        now_ms = int(ts_ms or time.time() * 1000)
        self._prune(now_ms)
        key = str(path_id or "")
        self._state.setdefault(key, []).append(now_ms)
        self._save()

    def penalty(self, path_id: str, *, ts_ms: int | None = None) -> float:
        now_ms = int(ts_ms or time.time() * 1000)
        self._prune(now_ms)
        uses = len(self._state.get(str(path_id or ""), []))
        if uses <= 0:
            return 0.0
        return min(0.35, 0.06 * float(uses))

    def snapshot(self) -> Dict[str, Any]:
        now_ms = int(time.time() * 1000)
        self._prune(now_ms)
        return {
            "paths": [{"path_id": k, "recent_uses": len(v)} for k, v in sorted(self._state.items())]
        }
