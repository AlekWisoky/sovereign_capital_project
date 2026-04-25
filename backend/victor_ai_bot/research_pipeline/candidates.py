from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, List

from ..outcomes import ResearchPromotionDecision


_ALLOWED = ['sandbox', 'paper', 'shadow_live', 'observe_only', 'capped_live', 'production', 'degraded', 'retired']


class CandidateStore:
    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, 'research', f'candidates_{chain}.json')
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._chain = chain
        self._items = self._load()

    def _load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, 'r', encoding='utf-8') as f:
            data = json.load(f) or {}
        return data if isinstance(data, dict) else {}

    def _save(self) -> None:
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self._items, f, indent=2, sort_keys=True)

    def create(self, *, family: str, origin: str, thesis: str, owner: str = '', generated_by: str = '', metadata: Dict[str, Any] | None = None) -> Dict[str, Any]:
        cid = str(uuid.uuid4())
        generated_live = str(origin or '') == 'generated' and bool((metadata or {}).get('promotion_ready'))
        stage = 'observe_only' if generated_live else 'sandbox'
        item = {
            'candidateId': cid,
            'chain': self._chain,
            'family': str(family),
            'origin': str(origin),
            'owner': str(owner),
            'generatedBy': str(generated_by),
            'thesis': str(thesis),
            'metadata': dict(metadata or {}),
            'stage': stage,
            'createdTs': int(time.time()),
            'updatedTs': int(time.time()),
            'reviews': [],
            'history': [{'ts': int(time.time()), 'stage': stage, 'reason': 'created'}],
        }
        self._items[cid] = item
        self._save()
        return dict(item)

    def get(self, candidate_id: str) -> Dict[str, Any]:
        item = self._items.get(str(candidate_id))
        if item is None:
            raise KeyError('candidate_not_found')
        return dict(item)

    def evaluate_promotion(self, candidate_id: str, *, evidence: Dict[str, Any] | None = None) -> ResearchPromotionDecision:
        item = self.get(candidate_id)
        meta = dict(item.get('metadata') or {})
        ev = dict(evidence or {})
        telemetry = int(ev.get('telemetry_count') or meta.get('telemetry_count') or 0)
        success = float(ev.get('success_rate') or meta.get('success_rate') or 0.0)
        drawdown = float(ev.get('drawdown_pct') or meta.get('drawdown_pct') or 0.0)
        if telemetry < 5:
            return ResearchPromotionDecision(allowed=False, reason_code='insufficient_telemetry', details={'candidateId': candidate_id})
        if success < 0.7:
            return ResearchPromotionDecision(allowed=False, reason_code='success_rate_too_low', details={'candidateId': candidate_id})
        if drawdown > 8.0:
            return ResearchPromotionDecision(allowed=False, reason_code='drawdown_too_high', details={'candidateId': candidate_id})
        next_stage = 'capped_live' if str(item.get('stage') or '') in {'shadow_live', 'observe_only'} else 'shadow_live'
        return ResearchPromotionDecision(allowed=True, reason_code='promotion_ready', next_stage=next_stage, details={'candidateId': candidate_id})

    def transition(self, candidate_id: str, *, stage: str, reason: str, reviewer: str = '') -> Dict[str, Any]:
        if stage not in _ALLOWED:
            raise ValueError('invalid_stage')
        item = self.get(candidate_id)
        item['stage'] = stage
        item['updatedTs'] = int(time.time())
        item.setdefault('history', []).append({'ts': int(time.time()), 'stage': stage, 'reason': str(reason), 'reviewer': str(reviewer)})
        self._items[str(candidate_id)] = item
        self._save()
        return dict(item)

    def add_review(self, candidate_id: str, *, reviewer: str, decision: str, note: str = '') -> Dict[str, Any]:
        item = self.get(candidate_id)
        item.setdefault('reviews', []).append({'ts': int(time.time()), 'reviewer': str(reviewer), 'decision': str(decision), 'note': str(note)})
        item['updatedTs'] = int(time.time())
        self._items[str(candidate_id)] = item
        self._save()
        return dict(item)

    def items(self) -> List[Dict[str, Any]]:
        return [dict(v) for _, v in sorted(self._items.items(), key=lambda kv: (str((kv[1] or {}).get('stage') or ''), int((kv[1] or {}).get('createdTs') or 0)), reverse=True)]

    def pipeline_counts(self) -> Dict[str, int]:
        out = {k: 0 for k in _ALLOWED}
        for v in self._items.values():
            stage = str((v or {}).get('stage') or 'sandbox')
            out[stage] = out.get(stage, 0) + 1
        return out

    def throughput_metrics(self) -> Dict[str, Any]:
        items = list(self._items.values())
        total = len(items)
        promoted = sum(1 for x in items if str((x or {}).get('stage') or '') in {'capped_live', 'production'})
        retired = sum(1 for x in items if str((x or {}).get('stage') or '') == 'retired')
        hit_rate = float(promoted) / max(1, total)
        return {'candidatesGenerated': total, 'candidatesPromoted': promoted, 'candidatesRetired': retired, 'researchHitRate': round(hit_rate, 6)}
