from __future__ import annotations

import json
import os
import time
from json import JSONDecodeError
from typing import Any, Dict, List

from ..persistence.db import PersistenceDB
from ..persistence.repositories.lifecycle_repository import LifecycleHistoryRepository


class StrategyLifecycleMemory:
    def __init__(self, path: str, *, chain: str):
        self.path = path
        self.chain = str(chain)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()
        self._db = PersistenceDB(
            os.path.join(
                os.path.dirname(os.path.dirname(path)), "state", "xdv_runtime_state.sqlite3"
            )
        )
        self._repo = LifecycleHistoryRepository(self._db, chain=self.chain)

    def _blank(self) -> Dict[str, Any]:
        return {"items": []}

    def _coerce_item(self, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        family = str(item.get("family") or "")
        strategy_id = str(item.get("strategy_id") or "")
        stage = str(item.get("stage") or "")
        reason_code = str(item.get("reason_code") or "")
        if not (family and strategy_id and stage and reason_code):
            return None
        payload = item.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        try:
            ts_ms = int(item.get("ts_ms") or 0)
        except (TypeError, ValueError):
            ts_ms = 0
        return {
            "ts_ms": ts_ms,
            "family": family,
            "strategy_id": strategy_id,
            "stage": stage,
            "reason_code": reason_code,
            "payload": dict(payload),
        }

    def _coerce_state(self, data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return self._blank()
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            return self._blank()
        items: List[Dict[str, Any]] = []
        for raw in raw_items:
            coerced = self._coerce_item(raw)
            if coerced is not None:
                items.append(coerced)
        return {"items": items[-1000:]}

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(data)

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2, sort_keys=True)

    def append(
        self,
        *,
        family: str,
        strategy_id: str,
        stage: str,
        reason_code: str,
        payload: Dict[str, Any] | None = None,
        ts_ms: int | None = None,
    ) -> None:
        item = {
            "ts_ms": int(ts_ms or time.time() * 1000),
            "family": str(family),
            "strategy_id": str(strategy_id),
            "stage": str(stage),
            "reason_code": str(reason_code),
            "payload": dict(payload or {}),
        }
        items = list(self._state.get("items") or [])
        items.append(item)
        self._state["items"] = items[-1000:]
        self._save()
        self._repo.append(
            ts_ms=int(item["ts_ms"]),
            family=str(family),
            strategy_id=str(strategy_id),
            stage=str(stage),
            reason_code=str(reason_code),
            payload=dict(payload or {}),
        )

    def snapshot(self, *, family: str = "") -> Dict[str, Any]:
        rows = self._repo.query(family=str(family), limit=200)
        if rows:
            return {"items": rows}
        items = list(self._state.get("items") or [])
        if family:
            items = [x for x in items if str(x.get("family") or "") == str(family)]
        return {"items": items[-200:]}
