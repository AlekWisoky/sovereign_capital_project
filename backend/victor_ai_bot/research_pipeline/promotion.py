from __future__ import annotations

from typing import Any, Dict


def promotion_allowed(*, score: float, risk_score: float, stage: str, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    evidence = dict(evidence or {})
    try:
        telemetry_count = int(evidence.get('telemetry_count') or 0)
    except (TypeError, ValueError):
        telemetry_count = 0
    if telemetry_count < 5:
        return {'allowed': False, 'nextStage': stage, 'reason': 'insufficient_telemetry'}
    if stage == 'sandbox' and score >= 0.55 and risk_score <= 0.60:
        return {'allowed': True, 'nextStage': 'paper', 'reason': 'sandbox_pass'}
    if stage == 'paper' and score >= 0.60 and risk_score <= 0.55:
        return {'allowed': True, 'nextStage': 'shadow_live', 'reason': 'paper_pass'}
    if stage == 'shadow_live' and score >= 0.66 and risk_score <= 0.50:
        return {'allowed': True, 'nextStage': 'capped_live', 'reason': 'shadow_live_pass'}
    if stage == 'capped_live' and score >= 0.72 and risk_score <= 0.45:
        return {'allowed': True, 'nextStage': 'production', 'reason': 'capped_live_pass'}
    return {'allowed': False, 'nextStage': stage, 'reason': 'criteria_not_met'}



def retirement_allowed(*, stage: str, evidence: Dict[str, Any] | None = None) -> Dict[str, Any]:
    evidence = dict(evidence or {})
    if stage in {'sandbox', 'paper', 'shadow'}:
        return {'allowed': False, 'reason': 'retirement_requires_active_stage'}
    try:
        drawdown = float(evidence.get('drawdown_pct') or 0.0)
        success_rate = float(evidence.get('success_rate') or 1.0)
        overlap = float(evidence.get('overlap_score') or 0.0)
        execution_decay = float(evidence.get('execution_decay_pct') or 0.0)
    except (TypeError, ValueError):
        return {'allowed': False, 'reason': 'invalid_retirement_evidence'}
    reasons = []
    if drawdown > 8.0:
        reasons.append('drawdown_limit_breached')
    if success_rate < 0.70:
        reasons.append('success_rate_degraded')
    if overlap > 0.80:
        reasons.append('overlap_excessive')
    if execution_decay > 0.25:
        reasons.append('execution_decay_excessive')
    if not reasons:
        return {'allowed': False, 'reason': 'retirement_criteria_not_met'}
    return {'allowed': True, 'nextStage': 'retired', 'reason': reasons[0], 'reasonCodes': reasons}
