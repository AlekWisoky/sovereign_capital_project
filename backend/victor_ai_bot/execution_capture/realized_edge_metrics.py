from __future__ import annotations

from typing import Any, Dict


def realized_edge_metrics(
    *,
    projected_gross_edge_usd: float,
    projected_realized_edge_usd: float,
    actual_realized_edge_usd: float,
) -> Dict[str, Any]:
    realization_ratio = (
        actual_realized_edge_usd / projected_realized_edge_usd
        if projected_realized_edge_usd > 0
        else 0.0
    )
    return {
        "projected_gross_edge_usd": round(float(projected_gross_edge_usd), 6),
        "projected_realized_edge_usd": round(float(projected_realized_edge_usd), 6),
        "actual_realized_edge_usd": round(float(actual_realized_edge_usd), 6),
        "realization_ratio": round(float(realization_ratio), 6),
    }
