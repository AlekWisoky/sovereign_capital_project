from __future__ import annotations

from typing import Any, Dict, List


def cointegration_score(series_a: List[float], series_b: List[float]) -> Dict[str, Any]:
    if not series_a or not series_b or len(series_a) != len(series_b):
        return {'score': 0.0}
    mean_a = sum(series_a)/len(series_a); mean_b = sum(series_b)/len(series_b)
    cov = sum((a-mean_a)*(b-mean_b) for a,b in zip(series_a, series_b))/max(1,len(series_a))
    var_a = sum((a-mean_a)**2 for a in series_a)/max(1,len(series_a))
    var_b = sum((b-mean_b)**2 for b in series_b)/max(1,len(series_b))
    denom = (var_a * var_b) ** 0.5
    return {'score': round(cov/denom, 6) if denom > 0 else 0.0}
