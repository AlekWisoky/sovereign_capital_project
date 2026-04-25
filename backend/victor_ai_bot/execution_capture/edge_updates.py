from __future__ import annotations

from typing import Any, Dict


def edge_learning_metrics(
    *, prediction: Dict[str, Any], actual_success: bool, actual_realized_edge_usd: float
) -> Dict[str, float]:
    projected = float(prediction.get("projected_realized_profit_usd") or 0.0)
    return {
        "actual_realized_edge_usd": float(actual_realized_edge_usd),
        "realization_ratio": (
            float(actual_realized_edge_usd / projected) if abs(projected) > 1e-9 else 1.0
        ),
        "success_error": (1.0 if actual_success else 0.0)
        - float(prediction.get("success_probability") or 0.0),
        "competition_error": (0.0 if actual_success else 1.0)
        - float(prediction.get("competition_probability") or 0.0),
    }
