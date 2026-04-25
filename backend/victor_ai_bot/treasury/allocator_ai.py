from __future__ import annotations

from typing import Any, Dict

from .family_allocator import compute_dynamic_family_weights


def recommend_family_weights(
    *,
    base_targets: Dict[str, float],
    scorecards: Dict[str, Any],
    regime: str,
    capital_metrics: Dict[str, Any],
    covariance_penalties: Dict[str, float],
) -> Dict[str, Any]:
    weights = compute_dynamic_family_weights(
        base_targets=base_targets,
        scorecards=scorecards,
        regime=regime,
        capital_metrics=capital_metrics,
        covariance_penalties=covariance_penalties,
    )
    sharpe_like = {
        k: round(float(v) * (1.0 - float((covariance_penalties or {}).get(k, 0.0))), 6)
        for k, v in weights.items()
    }
    return {"weights": weights, "sharpeLikeAdjusted": sharpe_like}
