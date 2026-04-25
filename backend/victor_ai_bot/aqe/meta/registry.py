from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

from .types import StrategyCandidate


class MetaRegistry:
    """Disk-backed registry for generated strategy candidates."""

    _ALLOWED_SCALAR_FIELDS = {
        'id',
        'created_iso',
        'description',
        'regime',
        'reason',
        'strategy_family',
        'lifecycle_stage',
    }
    _ALLOWED_NUMERIC_FIELDS = {
        'created_ts',
        'score',
        'genealogy_depth',
        'meta_success_probability',
        'diversity_bonus',
        'correlation_penalty',
        'novelty_score',
    }
    _ALLOWED_DICT_FIELDS = {
        'settings_patch',
        'safety_patch',
        'structure_patch',
        'stress_report',
    }
    _ALLOWED_LIST_FIELDS = {
        'parent_ids',
        'regime_tags',
        'feature_tags',
        'mutation_history',
    }

    def __init__(self, path: str, *, max_items: int = 200):
        self.path = path
        self.max_items = max_items
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _blank(self) -> List[Dict[str, Any]]:
        return []

    def _coerce_item(self, row: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(row, dict):
            return None
        cand_id = row.get('id')
        if cand_id is None:
            return None
        out: Dict[str, Any] = {'id': str(cand_id)}
        for key in self._ALLOWED_SCALAR_FIELDS - {'id'}:
            value = row.get(key)
            if value is not None:
                out[key] = str(value)
        for key in self._ALLOWED_NUMERIC_FIELDS:
            value = row.get(key)
            if value is None:
                continue
            try:
                if key == 'genealogy_depth':
                    out[key] = int(value)
                else:
                    out[key] = float(value)
            except (TypeError, ValueError):
                continue
        for key in self._ALLOWED_DICT_FIELDS:
            value = row.get(key)
            if isinstance(value, dict):
                out[key] = value
        for key in self._ALLOWED_LIST_FIELDS:
            value = row.get(key)
            if isinstance(value, list):
                out[key] = [str(v) for v in value]
        return out

    def _coerce_state(self, data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, list):
            return self._blank()
        rows: List[Dict[str, Any]] = []
        for row in data:
            coerced = self._coerce_item(row)
            if coerced is not None:
                rows.append(coerced)
        return rows[-self.max_items :]

    def load(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(data)

    def save(self, items: List[Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(items[-self.max_items :], f, indent=2, sort_keys=True)

    def append(self, cand: StrategyCandidate) -> None:
        items = self.load()
        items.append(cand.to_dict())
        self.save(items)

    def get(self, cand_id: str) -> Optional[Dict[str, Any]]:
        for x in reversed(self.load()):
            if str(x.get('id')) == cand_id:
                return x
        return None

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.load()[-max(1, int(limit)) :]

    def mark_stage(self, cand_id: str, stage: str) -> None:
        items = self.load()
        changed = False
        for row in items:
            if str(row.get('id')) == cand_id:
                row['lifecycle_stage'] = str(stage)
                changed = True
        if changed:
            self.save(items)
