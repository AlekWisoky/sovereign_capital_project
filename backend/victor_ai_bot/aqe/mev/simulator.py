from __future__ import annotations

from typing import Dict


def simulate_bundle(*, expected_profit_usd: float, gas_cost_usd: float, contention_risk: float) -> Dict[str, float | bool]:
    gas = float(gas_cost_usd)
    risk = max(0.0, min(1.0, float(contention_risk)))
    realized = max(0.0, float(expected_profit_usd) - gas - float(expected_profit_usd) * risk * 0.35)
    return {
        'ok': bool(realized > 0.0),
        'expected_realized_profit_usd': round(realized, 6),
        'contention_penalty_usd': round(float(expected_profit_usd) * risk * 0.35, 6),
    }
