from __future__ import annotations

from typing import Any, Dict, Iterable, List


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _mean(values: Iterable[float], default: float = 0.0) -> float:
    vals = [float(v) for v in values]
    return default if not vals else sum(vals) / float(len(vals))


def meta_success_profile(*, candidate: Dict[str, Any], memory_rows: List[Dict[str, Any]], regime: str) -> Dict[str, Any]:
    family = str(candidate.get('strategy_family') or 'generated')
    regime_rows = [r for r in list(memory_rows or []) if str(regime) in set(r.get('regime_tags') or [])]
    family_rows = [r for r in list(memory_rows or []) if str(r.get('strategy_family') or '') == family]
    recent = list(memory_rows or [])[-80:]

    fam_score = _mean([float(r.get('score') or 0.0) for r in family_rows[-40:]], 0.0)
    fam_hit = _mean([1.0 if float(r.get('score') or 0.0) > 0 else 0.0 for r in family_rows[-40:]], 0.55)
    regime_score = _mean([float(r.get('score') or 0.0) for r in regime_rows[-40:]], 0.0)
    regime_hit = _mean([1.0 if float(r.get('score') or 0.0) > 0 else 0.0 for r in regime_rows[-40:]], 0.55)
    recency_hit = _mean([1.0 if float(r.get('score') or 0.0) > 0 else 0.0 for r in recent], 0.55)

    novelty = float(((candidate.get('diversity_metrics') or {}).get('novelty_score') or 0.0))
    corr_pen = float(((candidate.get('diversity_metrics') or {}).get('correlation_penalty') or 0.0)) + float(candidate.get('overlap_penalty') or 0.0)
    robustness = float(((candidate.get('stress_report') or {}).get('robustness_score') or 0.0))
    validation_ok = 1.0 if bool((candidate.get('validation') or {}).get('passed')) else 0.0
    stage = str(candidate.get('lifecycle_stage') or 'sandbox')
    stage_bonus = {'sandbox': -0.05, 'paper': 0.0, 'paper_trading': 0.0, 'shadow_live': 0.03, 'capped_live': 0.05, 'production': 0.08}.get(stage, -0.02)

    predicted_success = 0.22
    predicted_success += fam_hit * 0.26
    predicted_success += regime_hit * 0.18
    predicted_success += recency_hit * 0.10
    predicted_success += _clip(fam_score / 20.0, -0.10, 0.12)
    predicted_success += _clip(regime_score / 20.0, -0.08, 0.10)
    predicted_success += _clip(robustness * 0.18, 0.0, 0.15)
    predicted_success += _clip(novelty * 0.10, 0.0, 0.08)
    predicted_success += stage_bonus
    predicted_success += validation_ok * 0.06
    predicted_success -= _clip(corr_pen * 0.22, 0.0, 0.18)
    predicted_success = _clip(predicted_success, 0.08, 0.95)

    evidence = min(1.0, (len(family_rows) * 0.02) + (len(regime_rows) * 0.015))
    confidence = _clip(0.35 + evidence * 0.45 + robustness * 0.12, 0.20, 0.98)
    return {
        'predicted_success': round(predicted_success, 6),
        'confidence': round(confidence, 6),
        'features': {
            'family_hit_rate': round(fam_hit, 6),
            'regime_hit_rate': round(regime_hit, 6),
            'recency_hit_rate': round(recency_hit, 6),
            'robustness': round(robustness, 6),
            'novelty': round(novelty, 6),
            'overlap_penalty': round(corr_pen, 6),
            'validation_ok': bool(validation_ok),
            'evidence': round(evidence, 6),
        },
    }
