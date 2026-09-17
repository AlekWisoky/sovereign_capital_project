from __future__ import annotations

import json
import os
import time
import uuid
from json import JSONDecodeError
from typing import Any, Dict


class AlphaMarketplaceStore:
    _STAGES = ('sandbox', 'paper', 'shadow', 'capped_live', 'live')

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
        stage = str(item.get('stage', 'sandbox') or 'sandbox')
        if stage not in self._STAGES:
            stage = 'sandbox'
        return {
            'submissionId': submission_id,
            'title': str(item.get('title', '') or ''),
            'contributor': str(item.get('contributor', '') or ''),
            'family': str(item.get('family', '') or ''),
            'thesis': str(item.get('thesis', '') or ''),
            'origin': str(item.get('origin', 'human') or 'human'),
            'strategyId': str(item.get('strategyId', submission_id) or submission_id),
            'parentStrategyIds': [str(v) for v in item.get('parentStrategyIds', []) if v is not None],
            'generatingEngine': str(item.get('generatingEngine', '') or ''),
            'agentId': str(item.get('agentId', '') or ''),
            'expectedEconomics': dict(item.get('expectedEconomics', {}) or {}) if isinstance(item.get('expectedEconomics', {}), dict) else {},
            'evidence': dict(item.get('evidence', {}) or {}) if isinstance(item.get('evidence', {}), dict) else {},
            'settingsPatch': dict(item.get('settingsPatch', {}) or {}) if isinstance(item.get('settingsPatch', {}), dict) else {},
            'safetyPatch': dict(item.get('safetyPatch', {}) or {}) if isinstance(item.get('safetyPatch', {}), dict) else {},
            'structurePatch': dict(item.get('structurePatch', {}) or {}) if isinstance(item.get('structurePatch', {}), dict) else {},
            'mutationHistory': [str(v) for v in item.get('mutationHistory', []) if v is not None],
            'reviewState': str(item.get('reviewState', 'pending') or 'pending'),
            'stage': stage,
            'governanceStatus': str(item.get('governanceStatus', 'pending') or 'pending'),
            'capitalSleeveStatus': str(item.get('capitalSleeveStatus', 'unfunded') or 'unfunded'),
            'promotionReason': str(item.get('promotionReason', '') or ''),
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

    def _save(self) -> None:
        with open(self.path, 'w', encoding='utf-8') as handle:
            json.dump(self._items, handle, indent=2, sort_keys=True)

    def submit(self, *, title: str, contributor: str, family: str, thesis: str) -> Dict[str, Any]:
        if not self.enabled:
            return {'ok': False, 'reason': 'marketplace_disabled'}
        sid = str(uuid.uuid4())
        item = {
            'submissionId': sid,
            'title': str(title),
            'contributor': str(contributor),
            'family': str(family),
            'thesis': str(thesis),
            'origin': 'human',
            'strategyId': sid,
            'parentStrategyIds': [],
            'generatingEngine': '',
            'agentId': '',
            'expectedEconomics': {},
            'evidence': {},
            'settingsPatch': {},
            'safetyPatch': {},
            'structurePatch': {},
            'mutationHistory': [],
            'reviewState': 'pending',
            'stage': 'sandbox',
            'governanceStatus': 'pending',
            'capitalSleeveStatus': 'unfunded',
            'promotionReason': '',
            'createdTs': int(time.time()),
            'profitSharingPlaceholder': True,
        }
        self._items[sid] = item
        self._save()
        return {'ok': True, 'item': dict(item)}

    def submit_candidate(self, *, candidate: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            return {'ok': False, 'reason': 'marketplace_disabled'}
        sid = str(candidate.get('submissionId') or candidate.get('strategyId') or '').strip()
        if not sid:
            return {'ok': False, 'reason': 'missing_strategy_identity'}
        item = self._coerce_item(sid, candidate)
        if item is None:
            return {'ok': False, 'reason': 'invalid_strategy_candidate'}
        item['origin'] = 'ai' if item['origin'] not in {'human', 'hybrid'} else item['origin']
        item['reviewState'] = 'pending'
        item['stage'] = 'sandbox'
        item['governanceStatus'] = 'pending'
        item['capitalSleeveStatus'] = 'unfunded'
        item['promotionReason'] = ''
        item['createdTs'] = int(item.get('createdTs') or time.time())
        self._items[sid] = item
        self._save()
        return {'ok': True, 'item': dict(item)}

    def snapshot(self) -> Dict[str, Any]:
        return {'enabled': self.enabled, 'items': [dict(v) for v in self._items.values()]}
