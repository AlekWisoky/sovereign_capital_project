from __future__ import annotations

import json
import os
from typing import Any, Dict, List


class GenealogyStore:
    def __init__(self, path: str, *, max_items: int = 1000):
        self.path = path
        self.max_items = int(max_items)
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _blank(self) -> List[Dict[str, Any]]:
        return []

    def _coerce_item(self, raw: Any) -> Dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        item: Dict[str, Any] = {}
        candidate_id = raw.get("id")
        if candidate_id is None:
            return None
        candidate_id = str(candidate_id).strip()
        if not candidate_id:
            return None
        item["id"] = candidate_id

        parent_ids = raw.get("parent_ids")
        if isinstance(parent_ids, list):
            item["parent_ids"] = [
                str(x).strip()
                for x in parent_ids
                if x is not None and str(x).strip()
            ]
        else:
            item["parent_ids"] = []

        mutation_history = raw.get("mutation_history")
        if isinstance(mutation_history, list):
            item["mutation_history"] = [
                str(x).strip()
                for x in mutation_history
                if x is not None and str(x).strip()
            ]
        else:
            item["mutation_history"] = []

        for key in ("generation_number",):
            value = raw.get(key)
            if value is None:
                continue
            try:
                item[key] = int(value)
            except (TypeError, ValueError):
                continue

        for key in ("lifecycle_stage", "retirement_reason", "strategy_family"):
            value = raw.get(key)
            if value is None:
                continue
            value = str(value).strip()
            if value:
                item[key] = value
        return item

    def _coerce_state(self, raw: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw, list):
            return self._blank()
        items: List[Dict[str, Any]] = []
        for entry in raw:
            coerced = self._coerce_item(entry)
            if coerced is not None:
                items.append(coerced)
        return items[-self.max_items :]

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f) or []
        except (OSError, json.JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(data)

    def append(self, row: Dict[str, Any]) -> None:
        items = self.load()
        items.append(dict(row))
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(items[-self.max_items :], f, indent=2, sort_keys=True)

    def lineage(self, candidate_id: str) -> List[Dict[str, Any]]:
        cid = str(candidate_id)
        return [
            x
            for x in self.load()
            if cid in set([str(x.get("id"))] + list(x.get("parent_ids") or []))
        ]
