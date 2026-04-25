from __future__ import annotations

from typing import Any, Dict


def estimate_borrow_cost(
    *,
    notional_usd: float,
    source: str,
    horizon_minutes: float,
    flashloan_bps: float = 9.0,
    internal_prime_bps_per_day: float = 12.0,
) -> Dict[str, Any]:
    src = str(source or "flashloan")
    if src == "flashloan":
        cost = float(notional_usd) * (float(flashloan_bps) / 10_000.0)
    else:
        daily = float(notional_usd) * (float(internal_prime_bps_per_day) / 10_000.0)
        cost = daily * max(0.0, float(horizon_minutes)) / 1440.0
    return {"source": src, "borrowCostUsd": round(cost, 8)}
