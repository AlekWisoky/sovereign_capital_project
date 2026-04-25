from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from .events import TelemetryEvent
from ..persistence.db import PersistenceDB
from ..persistence.repositories.telemetry_repo import TelemetryRepository


_SAFE_TELEMETRY_REPO_PERSIST_EXCEPTIONS = (
    OSError,
    TypeError,
    ValueError,
    sqlite3.Error,
)

_SAFE_TELEMETRY_TRIM_EXCEPTIONS = (OSError,)


class TelemetryStore:
    """Append-only telemetry store with JSONL + SQLite-backed query helpers."""

    def __init__(self, *, data_dir: str, chain: str, max_items: int = 5000):
        self.chain = str(chain)
        self.max_items = int(max_items)
        self.path = os.path.join(data_dir, "telemetry", f"events_{self.chain}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._db = PersistenceDB(os.path.join(data_dir, "state", "xdv_runtime_state.sqlite3"))
        self._repo = TelemetryRepository(self._db, chain=self.chain)

    def append(self, event: TelemetryEvent) -> None:
        row = event.to_dict()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True) + "\n")
        try:
            self._repo.insert(
                event_type=str(event.event_type),
                ts_ms=int(event.ts_ms),
                payload=dict(event.payload or {}),
            )
        except _SAFE_TELEMETRY_REPO_PERSIST_EXCEPTIONS:
            pass
        self._trim_if_needed()

    def _trim_if_needed(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) <= self.max_items:
                return
            with open(self.path, "w", encoding="utf-8") as f:
                f.writelines(lines[-self.max_items :])
        except _SAFE_TELEMETRY_TRIM_EXCEPTIONS:
            return

    def tail(self, limit: int = 200, *, event_type: str = "") -> List[Dict[str, Any]]:
        rows = self._repo.query(event_type=event_type, limit=limit)
        if rows:
            return rows
        if not os.path.exists(self.path):
            return []
        out: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for ln in reversed(lines):
                try:
                    row = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if event_type and str(row.get("event_type") or "") != str(event_type):
                    continue
                out.append(row)
                if len(out) >= int(limit):
                    break
        except OSError:
            return []
        return list(reversed(out))

    def filter(
        self,
        *,
        event_type: str = "",
        route_family: str = "",
        strategy_family: str = "",
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        rows = self._repo.query(
            event_type=event_type,
            route_family=route_family,
            strategy_family=strategy_family,
            limit=max(limit, 2000),
        ) or self.tail(limit=max(limit, 2000), event_type=event_type)
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = row.get("payload") or {}
            if event_type and str(row.get("event_type") or "") != str(event_type):
                continue
            if route_family and str(payload.get("route_family") or "") != str(route_family):
                continue
            if strategy_family and str(payload.get("strategy_family") or "") != str(
                strategy_family
            ):
                continue
            out.append(row)
        return out[-limit:]
