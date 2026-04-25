from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable


_SAFE_RPC_PREFERENCE_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)
_RPC_PREFERENCE_LANES = ("read", "send", "private")


class RpcPreferencesStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "governance", f"rpc_preferences_{chain}.json")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._state = self._load()

    def _normalize_lane(self, values: Iterable[Any] | None) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in list(values or []):
            item = str(value or "").strip()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    def _normalized_state(self, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        source = dict(data or {})
        return {lane: self._normalize_lane(source.get(lane)) for lane in _RPC_PREFERENCE_LANES}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._normalized_state()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except _SAFE_RPC_PREFERENCE_LOAD_EXCEPTIONS:
            return self._normalized_state()
        if not isinstance(data, dict):
            return self._normalized_state()
        return self._normalized_state(data)

    def save(
        self,
        *,
        read: list[str] | None = None,
        send: list[str] | None = None,
        private: list[str] | None = None,
    ) -> Dict[str, Any]:
        next_state = dict(self._state)
        updates = {"read": read, "send": send, "private": private}
        for lane, values in updates.items():
            if values is not None:
                next_state[lane] = self._normalize_lane(values)
        tmp_path = f"{self.path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(next_state, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self.path)
        self._state = next_state
        return self.snapshot()

    def patch(
        self,
        *,
        read: list[str] | None = None,
        send: list[str] | None = None,
        private: list[str] | None = None,
    ) -> Dict[str, Any]:
        return self.save(read=read, send=send, private=private)

    def snapshot(self) -> Dict[str, Any]:
        state = self._normalized_state(self._state)
        return {
            "read": list(state.get("read") or []),
            "send": list(state.get("send") or []),
            "private": list(state.get("private") or []),
            "configured": bool(
                (state.get("read") or [])
                or (state.get("send") or [])
                or (state.get("private") or [])
            ),
        }
