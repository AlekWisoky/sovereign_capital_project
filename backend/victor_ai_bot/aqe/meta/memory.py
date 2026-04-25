from __future__ import annotations

import json
import os
from json import JSONDecodeError
from typing import Any, Dict, List, Optional


class StrategyMemory:
    def __init__(self, path: str, *, max_items: int = 500):
        self.path = path
        self.max_items = max_items
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def _blank(self) -> List[Dict[str, Any]]:
        return []

    def _coerce_item(self, item: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(item, dict):
            return None
        coerced: Dict[str, Any] = {}
        if item.get('id') is not None:
            coerced['id'] = str(item.get('id'))
        for key in (
            'description',
            'reason',
            'regime',
            'strategy_family',
            'lifecycle_stage',
        ):
            value = item.get(key)
            if value is not None:
                coerced[key] = str(value)
        for key in ('score', 'created_ts', 'genealogy_depth'):
            value = item.get(key)
            if value is None:
                continue
            try:
                coerced[key] = float(value) if key == 'score' else int(value)
            except (TypeError, ValueError):
                continue
        for key in ('parent_ids', 'regime_tags', 'feature_tags', 'mutation_history'):
            value = item.get(key)
            if not isinstance(value, list):
                continue
            normalized = [str(v) for v in value if v is not None]
            coerced[key] = normalized
        for key in ('settings_patch', 'safety_patch', 'structure_patch', 'stress_report'):
            value = item.get(key)
            if isinstance(value, dict):
                coerced[key] = dict(value)
        if not coerced.get('id'):
            return None
        return coerced

    def _coerce_state(self, data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, list):
            return self._blank()
        items: List[Dict[str, Any]] = []
        for item in data:
            coerced = self._coerce_item(item)
            if coerced is not None:
                items.append(coerced)
        return items

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
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(items[-self.max_items:], f, indent=2, sort_keys=True)

    def append(self, item: Dict[str, Any]) -> None:
        items = self.load()
        items.append(dict(item))
        self.save(items)

    def get(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        for x in reversed(self.load()):
            if str(x.get('id')) == strategy_id:
                return dict(x)
        return None

    def summary(self) -> Dict[str, Any]:
        items = self.load()
        stages: Dict[str, int] = {}
        by_regime: Dict[str, int] = {}
        for x in items:
            stages[str(x.get('lifecycle_stage') or 'experimental')] = stages.get(str(x.get('lifecycle_stage') or 'experimental'), 0) + 1
            for tag in list(x.get('regime_tags') or []):
                by_regime[str(tag)] = by_regime.get(str(tag), 0) + 1
        return {
            'count': len(items),
            'stages': stages,
            'byRegime': by_regime,
        }
