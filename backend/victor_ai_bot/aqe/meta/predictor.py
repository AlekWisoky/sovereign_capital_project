from __future__ import annotations

from typing import Any, Dict, List

from .success_model import meta_success_profile


def predict_candidate_success(*, candidate: Dict[str, Any], memory_rows: List[Dict[str, Any]], regime: str) -> Dict[str, float]:
    prof = meta_success_profile(candidate=candidate, memory_rows=memory_rows, regime=regime)
    out = {
        'predicted_success': float(prof.get('predicted_success') or 0.0),
        'prediction_confidence': float(prof.get('confidence') or 0.0),
    }
    out.update({f'feature_{k}': v for k, v in dict(prof.get('features') or {}).items()})
    return out
