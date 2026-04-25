from __future__ import annotations

from typing import Any, Dict


def thin_spread_realized_edge(
    *, spread_bps: float, gas_cost_usd: float, loan_fee_usd: float, notional_usd: float
) -> Dict[str, Any]:
    gross = float(notional_usd) * (float(spread_bps) / 10_000.0)
    realized = gross - float(gas_cost_usd) - float(loan_fee_usd)
    return {
        "projectedGrossEdgeUsd": round(gross, 8),
        "projectedRealizedEdgeUsd": round(realized, 8),
        "thinMargin": bool(float(spread_bps) <= 20.0),
    }
