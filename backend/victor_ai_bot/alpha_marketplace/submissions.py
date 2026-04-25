from __future__ import annotations

import json
import os
import time
import uuid
from json import JSONDecodeError
from typing import Any, Dict, List


class AlphaMarketplaceStore:
    def __init__(self, *, data_dir: str, chain: str, enabled: bool = False):
        self.enabled = bool(enabled)
        self.path = os.path.join(data_dir, 'marketplace', f'submissions_{chain}.json')
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._items = self._load()

    def _blank(self) -> Dict[str, Dict[str, Any]]:
        return {}

    def _coerce_item(self, key: str, item: Any) -> Dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        submission_id = item.get('submissionId', key)
        if submission_id is None:
            return None
        submission_id = str(submission_id).strip()
        if not submission_id:
            return None
        return {
            'submissionId': submission_id,
            'title': str(item.get('title', '') or ''),
            'contributor': str(item.get('contributor', '') or ''),
            'family': str(item.get('family', '') or ''),
            'thesis': str(item.get('thesis', '') or ''),
            'reviewState': str(item.get('reviewState', 'pending') or 'pending'),
            'stage': str(item.get('stage', 'sandbox') or 'sandbox'),
            'createdTs': int(item.get('createdTs', 0) or 0),
            'profitSharingPlaceholder': bool(item.get('profitSharingPlaceholder', True)),
        }

    def _coerce_state(self, payload: Any) -> Dict[str, Dict[str, Any]]:
        if not isinstance(payload, dict):
            return self._blank()
        state: Dict[str, Dict[str, Any]] = {}
        for key, item in payload.items():
            coerced = self._coerce_item(str(key), item)
            if coerced is not None:
                state[coerced['submissionId']] = coerced
        return state

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.path):
            return self._blank()
        try:
            with open(self.path, 'r', encoding='utf-8') as handle:
                payload = json.load(handle) or {}
        except (OSError, JSONDecodeError, ValueError):
            return self._blank()
        return self._coerce_state(payload)

    def _save(self):
        json.dump(self._items, open(self.path,'w',encoding='utf-8'), indent=2, sort_keys=True)

    def submit(self, *, title: str, contributor: str, family: str, thesis: str) -> Dict[str, Any]:
        if not self.enabled:
            return {'ok': False, 'reason': 'marketplace_disabled'}
        sid = str(uuid.uuid4())
        item = {'submissionId': sid, 'title': str(title), 'contributor': str(contributor), 'family': str(family), 'thesis': str(thesis), 'reviewState': 'pending', 'stage': 'sandbox', 'createdTs': int(time.time()), 'profitSharingPlaceholder': True}
        self._items[sid]=item; self._save(); return {'ok': True, 'item': item}

    def snapshot(self) -> Dict[str, Any]:
        return {'enabled': self.enabled, 'items': [dict(v) for v in self._items.values()]}
