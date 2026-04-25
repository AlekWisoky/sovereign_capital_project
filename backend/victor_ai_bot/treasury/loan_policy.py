from __future__ import annotations

from typing import Any, Dict

from .borrow_costs import estimate_borrow_cost


def loan_admission(
    *,
    family: str,
    stage: str,
    notional_usd: float,
    projected_realized_edge_usd: float,
    source: str,
    confidence: float,
) -> Dict[str, Any]:
    borrow = estimate_borrow_cost(
        notional_usd=notional_usd,
        source=source,
        horizon_minutes=15.0 if source == "flashloan" else 180.0,
    )
    require = 0.70 if str(source) == "flashloan" else 0.80
    thin = float(projected_realized_edge_usd) <= float(borrow["borrowCostUsd"]) * 1.5
    restricted = (
        str(stage) in {"internal_capital", "pilot_capital"}
        and float(notional_usd) > 5_000_000
        and str(source) != "flashloan"
    )
    allowed = float(confidence) >= require and not thin and not restricted
    return {
        "allowed": bool(allowed),
        "reason": (
            "ok"
            if allowed
            else (
                "confidence_too_low"
                if float(confidence) < require
                else "thin_after_borrow_cost" if thin else "stage_restriction"
            )
        ),
        "borrowCostUsd": float(borrow["borrowCostUsd"]),
        "requiredConfidence": require,
    }
