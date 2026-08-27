from __future__ import annotations

import json
import os
import threading
from typing import Any, Mapping


_SAFE = (OSError, TypeError, ValueError, json.JSONDecodeError)


class DurableLearningIdentity:
    """Small durable identity journal for decision -> settled-outcome learning.

    The journal is intentionally separate from the policy state. It stores only
    enough lineage/action metadata to survive process restarts and prevent a
    canonical settled outcome from updating policy twice.
    """

    def __init__(self, path: str, *, max_rows: int = 4096) -> None:
        self.path = path
        self.max_rows = max(128, int(max_rows))
        self._lock = threading.RLock()
        self._pending: dict[str, dict[str, Any]] = {}
        self._settled: dict[str, dict[str, Any]] = {}
        self._load()

    def remember_decision(self, decision_id: str, row: Mapping[str, Any]) -> None:
        key = str(decision_id or "").strip()
        if not key:
            return
        with self._lock:
            self._pending[key] = dict(row or {})
            self._trim()
            self._save()

    def pending(self, decision_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._pending.get(str(decision_id or "").strip(), {}) or {})

    def is_settled(self, decision_id: str) -> bool:
        with self._lock:
            return str(decision_id or "").strip() in self._settled

    def mark_settled(self, decision_id: str, row: Mapping[str, Any]) -> None:
        key = str(decision_id or "").strip()
        if not key:
            return
        with self._lock:
            self._settled[key] = dict(row or {})
            self._pending.pop(key, None)
            self._trim()
            self._save()

    def _trim(self) -> None:
        if len(self._pending) > self.max_rows:
            keys = list(self._pending.keys())[:-self.max_rows]
            for key in keys:
                self._pending.pop(key, None)
        if len(self._settled) > self.max_rows:
            keys = list(self._settled.keys())[:-self.max_rows]
            for key in keys:
                self._settled.pop(key, None)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump(
                    {"v": 1, "pending": self._pending, "settled": self._settled},
                    handle,
                    sort_keys=True,
                )
            os.replace(tmp, self.path)
        except _SAFE:
            return

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or int(payload.get("v", 0)) != 1:
                return
            pending = payload.get("pending")
            settled = payload.get("settled")
            if isinstance(pending, dict):
                self._pending = {str(k): dict(v) for k, v in pending.items() if isinstance(v, dict)}
            if isinstance(settled, dict):
                self._settled = {str(k): dict(v) for k, v in settled.items() if isinstance(v, dict)}
            self._trim()
        except _SAFE:
            return
