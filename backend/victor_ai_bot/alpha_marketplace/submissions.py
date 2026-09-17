from __future__ import annotations

import json
import os
import time
import uuid
from json import JSONDecodeError
from typing import Any, Dict

from ..research_pipeline.promotion import promotion_allowed, retirement_allowed


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

    def set_governance(self, submission_id: str, *, review_state: str, governance_status: str, reviewer: str = "", reason: str = "") -> Dict[str, Any]:
        item = self._items.get(str(submission_id))
        if item is None:
            return {"ok": False, "reason": "submission_not_found"}
        review = str(review_state or "pending").strip().lower()
        governance = str(governance_status or "pending").strip().lower()
        if review not in {"pending", "approved", "rejected"} or governance not in {"pending", "approved", "rejected"}:
            return {"ok": False, "reason": "invalid_governance_state"}
        item["reviewState"] = review
        item["governanceStatus"] = governance
        item.setdefault("evidence", {})["lastReview"] = {
            "reviewer": str(reviewer or ""),
            "reason": str(reason or ""),
            "reviewState": review,
            "governanceStatus": governance,
            "ts": int(time.time()),
        }
        item["promotionReason"] = str(reason or item.get("promotionReason") or "")
        self._items[str(submission_id)] = item
        self._save()
        return {"ok": True, "item": dict(item)}

    def promote(self, submission_id: str, *, score: float | None = None, risk_score: float | None = None, reviewer: str = "") -> Dict[str, Any]:
        item = self._items.get(str(submission_id))
        if item is None:
            return {"ok": False, "reason": "submission_not_found"}
        if str(item.get("reviewState")) != "approved" or str(item.get("governanceStatus")) != "approved":
            return {"ok": False, "reason": "governance_approval_required"}
        evidence = dict(item.get("evidence") or {})
        economics = dict(item.get("expectedEconomics") or {})
        score_value = float(score if score is not None else evidence.get("score", economics.get("score", 0.0)))
        risk_value = float(risk_score if risk_score is not None else evidence.get("riskScore", 1.0))
        decision = promotion_allowed(score=score_value, risk_score=risk_value, stage=str(item.get("stage") or "sandbox"), evidence=evidence)
        if not bool(decision.get("allowed")):
            return {"ok": False, "reason": str(decision.get("reason") or "promotion_denied"), "decision": decision}
        next_stage = str(decision.get("nextStage") or item.get("stage") or "sandbox")
        projection = {"shadow_live": "shadow", "production": "live"}
        next_stage = projection.get(next_stage, next_stage)
        item["stage"] = next_stage
        item["promotionReason"] = str(decision.get("reason") or "promotion_allowed")
        item.setdefault("evidence", {})["lastPromotion"] = {"score": score_value, "riskScore": risk_value, "reviewer": str(reviewer or ""), "decision": dict(decision), "ts": int(time.time())}
        self._items[str(submission_id)] = item
        self._save()
        return {"ok": True, "item": dict(item), "decision": decision}

    def retire(self, submission_id: str, *, evidence: Dict[str, Any] | None = None, reviewer: str = "") -> Dict[str, Any]:
        item = self._items.get(str(submission_id))
        if item is None:
            return {"ok": False, "reason": "submission_not_found"}
        merged = dict(item.get("evidence") or {})
        merged.update(dict(evidence or {}))
        decision = retirement_allowed(stage=str(item.get("stage") or "sandbox"), evidence=merged)
        if not bool(decision.get("allowed")):
            return {"ok": False, "reason": str(decision.get("reason") or "retirement_denied"), "decision": decision}
        item["stage"] = "retired"
        item["promotionReason"] = str(decision.get("reason") or "retired")
        item.setdefault("evidence", {})["lastRetirement"] = {"reviewer": str(reviewer or ""), "decision": dict(decision), "ts": int(time.time())}
        self._items[str(submission_id)] = item
        self._save()
        return {"ok": True, "item": dict(item), "decision": decision}

    def snapshot(self) -> Dict[str, Any]:
        return {'enabled': self.enabled, 'items': [dict(v) for v in self._items.values()]}
