from __future__ import annotations

from typing import Any, Dict


def promotion_allowed(*, score: float, risk_score: float, stage: str) -> Dict[str, Any]:
    if stage == 'sandbox' and score >= 0.55 and risk_score <= 0.60:
        return {'allowed': True, 'nextStage': 'paper', 'reason': 'sandbox_pass'}
    if stage == 'paper' and score >= 0.60 and risk_score <= 0.55:
        return {'allowed': True, 'nextStage': 'shadow_live', 'reason': 'paper_pass'}
    if stage == 'shadow_live' and score >= 0.66 and risk_score <= 0.50:
        return {'allowed': True, 'nextStage': 'capped_live', 'reason': 'shadow_live_pass'}
    if stage == 'capped_live' and score >= 0.72 and risk_score <= 0.45:
        return {'allowed': True, 'nextStage': 'production', 'reason': 'capped_live_pass'}
    return {'allowed': False, 'nextStage': stage, 'reason': 'criteria_not_met'}
