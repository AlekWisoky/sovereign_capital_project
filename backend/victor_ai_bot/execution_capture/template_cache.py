from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from typing import Any, Dict


class RouteTemplateCache:
    def __init__(self, *, data_dir: str, chain: str):
        self._path = os.path.join(data_dir, "execution_capture", f"templates_{chain}.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._cache = self._load()

    def _blank(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return {"by_family": {}, "by_route_id": {}}

    def _coerce_payload(self, value: Any) -> Dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        route_id = str(value.get("route_id") or "")
        metadata = value.get("metadata")
        updated_ts_ms = value.get("updated_ts_ms")
        try:
            normalized_ts = int(updated_ts_ms) if updated_ts_ms is not None else 0
        except (TypeError, ValueError):
            normalized_ts = 0
        return {
            "route_id": route_id,
            "metadata": dict(metadata) if isinstance(metadata, dict) else {},
            "updated_ts_ms": normalized_ts,
        }

    def _coerce_bucket(self, value: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for key, payload in value.items():
            coerced = self._coerce_payload(payload)
            if coerced:
                out[str(key)] = coerced
        return out

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self._path):
            return self._blank()
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        if not isinstance(data, dict):
            return self._blank()
        return {
            "by_family": self._coerce_bucket(data.get("by_family")),
            "by_route_id": self._coerce_bucket(data.get("by_route_id")),
        }

    def _persist(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2, sort_keys=True)

    def remember(self, *, route_family: str, route_id: str, metadata: Dict[str, Any]) -> None:
        if not route_family and not route_id:
            return
        payload = {
            "route_id": str(route_id),
            "metadata": dict(metadata or {}),
            "updated_ts_ms": int(time.time() * 1000),
        }
        if route_family:
            self._cache.setdefault("by_family", {})[str(route_family)] = payload
        if route_id:
            self._cache.setdefault("by_route_id", {})[str(route_id)] = payload
        self._persist()

    def invalidate(self, *, route_family: str = "", route_id: str = "") -> None:
        changed = False
        if route_family and str(route_family) in self._cache.get("by_family", {}):
            self._cache["by_family"].pop(str(route_family), None)
            changed = True
        if route_id and str(route_id) in self._cache.get("by_route_id", {}):
            self._cache["by_route_id"].pop(str(route_id), None)
            changed = True
        if changed:
            self._persist()

    def get(self, key: str) -> Dict[str, Any]:
        if str(key) in self._cache.get("by_route_id", {}):
            item = self._cache["by_route_id"][str(key)]
            return dict(item) if isinstance(item, dict) else {}
        item = self._cache.get("by_family", {}).get(str(key))
        return dict(item) if isinstance(item, dict) else {}

    def snapshot(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._cache))
