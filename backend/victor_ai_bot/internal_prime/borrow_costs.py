from __future__ import annotations

from typing import Dict


def internal_borrow_cost(
    *, notional_usd: float, horizon_minutes: float, utilization: float
) -> Dict[str, float]:
    bps_per_day = 8.0 + max(0.0, float(utilization)) * 12.0
    cost = (
        float(notional_usd) * (bps_per_day / 10_000.0) * max(0.0, float(horizon_minutes)) / 1440.0
    )
    return {"bpsPerDay": round(bps_per_day, 6), "borrowCostUsd": round(cost, 8)}
