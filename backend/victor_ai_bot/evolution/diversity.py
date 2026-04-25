from __future__ import annotations

from typing import Any, Dict, Iterable, List, Set


def diversity_score(
    *, signals: Iterable[str], existing: List[Dict[str, Any]], regime: str
) -> Dict[str, float]:
    sigs = set(str(x) for x in list(signals or []))
    if not existing:
        return {
            "behavioral_novelty": 1.0,
            "regime_complementarity": 1.0,
            "feature_diversity": 1.0,
            "correlation_penalty": 0.0,
        }
    overlap = 0
    regime_overlap = 0
    for row in existing[-50:]:
        rs = set(((row.get("structure_patch") or {}).get("signals") or []))
        if sigs.intersection(rs):
            overlap += 1
        if str(regime) in set(row.get("regime_tags") or []):
            regime_overlap += 1
    total = max(1, len(existing[-50:]))
    behavioral_novelty = max(0.0, 1.0 - (overlap / total))
    regime_complementarity = max(0.0, 1.0 - (regime_overlap / total))
    feature_diversity = max(0.0, min(1.0, len(sigs) / 5.0))
    correlation_penalty = min(1.0, overlap / total)
    return {
        "behavioral_novelty": round(behavioral_novelty, 6),
        "regime_complementarity": round(regime_complementarity, 6),
        "feature_diversity": round(feature_diversity, 6),
        "correlation_penalty": round(correlation_penalty, 6),
    }
