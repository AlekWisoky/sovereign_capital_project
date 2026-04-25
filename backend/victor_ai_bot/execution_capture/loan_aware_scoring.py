from __future__ import annotations

from typing import Any, Dict


def loan_adjusted_value(
    *, projected_realized_edge_usd: float, borrow_cost_usd: float, confidence: float
) -> Dict[str, Any]:
    adjusted = float(projected_realized_edge_usd) - float(borrow_cost_usd)
    confidence_mult = max(0.25, min(1.1, float(confidence)))
    return {
        "loanAdjustedEdgeUsd": round(adjusted * confidence_mult, 8),
        "borrowCostUsd": float(borrow_cost_usd),
        "reason": "loan_cost_applied",
    }
