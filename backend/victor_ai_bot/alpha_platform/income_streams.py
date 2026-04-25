from __future__ import annotations

from typing import Any, Dict


def rotation_plan(*, metrics: Dict[str, Any]) -> Dict[str, Any]:
    families = dict(metrics or {})
    scores: Dict[str, float] = {}
    for family, row in families.items():
        rec = dict(row or {})
        realized = float(rec.get('realizedPnlUsd', 0.0) or 0.0)
        efficiency = float(rec.get('capitalEfficiency', 0.0) or 0.0)
        stability = float(rec.get('stability', 0.5) or 0.0)
        drawdown = float(rec.get('drawdownPenalty', 0.0) or 0.0)
        score = realized * 0.4 + efficiency * 0.3 + stability * 0.3 - drawdown * 0.4
        scores[str(family)] = round(score, 6)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    total = sum(max(0.0, v) for _, v in ordered) or 1.0
    weights = {k: round(max(0.0, v) / total, 6) for k, v in ordered}
    return {'scores': scores, 'weights': weights, 'rotationOrder': [k for k, _ in ordered]}
