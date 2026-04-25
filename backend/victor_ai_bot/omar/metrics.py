from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any
import numpy as np


@dataclass
class SocialMetrics:
    coordination_index: float
    conflict_resolution_rate: float
    capital_fairness: float


def compute_social_metrics(
    coord_hist: np.ndarray, conflict_hist: np.ndarray, capital_alloc: Dict[str, float]
) -> SocialMetrics:
    coordination_index = float(np.mean(coord_hist)) if len(coord_hist) else 0.0
    # conflict resolution rate proxy: 1 - avg conflict
    conflict_resolution_rate = float(1.0 - np.mean(conflict_hist)) if len(conflict_hist) else 0.0
    # fairness: 1 - Gini
    vals = (
        np.array(list(capital_alloc.values()), dtype=np.float32)
        if capital_alloc
        else np.array([1.0], dtype=np.float32)
    )
    vals = np.maximum(vals, 1e-9)
    vals = vals / vals.sum()
    sorted_vals = np.sort(vals)
    n = len(sorted_vals)
    gini = float(
        (np.sum((2 * np.arange(1, n + 1) - n - 1) * sorted_vals)) / (n * np.sum(sorted_vals) + 1e-9)
    )
    capital_fairness = float(1.0 - abs(gini))
    return SocialMetrics(
        coordination_index=coordination_index,
        conflict_resolution_rate=conflict_resolution_rate,
        capital_fairness=capital_fairness,
    )


def to_dict(m: SocialMetrics) -> Dict[str, Any]:
    return asdict(m)
