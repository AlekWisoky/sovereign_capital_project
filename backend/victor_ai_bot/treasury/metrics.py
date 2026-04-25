from __future__ import annotations

from typing import Any, Dict


def capital_efficiency_metrics(
    *,
    realized_pnl_wei: int,
    deployed_capital_wei: int,
    at_risk_capital_wei: int,
    gas_cost_wei: int,
    utilization_rate: float,
    failures: int,
    bankroll_wei: int | None = None,
    turnover_count: int = 0,
) -> Dict[str, Any]:
    realized = float(int(realized_pnl_wei))
    deployed = float(max(1, int(deployed_capital_wei)))
    risk = float(max(1, int(at_risk_capital_wei)))
    gas = float(max(1, int(gas_cost_wei)))
    util = max(0.0, min(1.0, float(utilization_rate)))
    bankroll = float(max(int(bankroll_wei or (deployed / max(0.1, util))), 1))
    idle = max(0.0, bankroll - deployed)
    turnover = (
        float(turnover_count) / max(1.0, deployed / max(1.0, bankroll))
        if turnover_count > 0
        else util
    )
    return {
        "return_on_deployed_capital": round(realized / deployed, 6),
        "return_on_at_risk_capital": round(realized / risk, 6),
        "pnl_per_gas_dollar_proxy": round(realized / gas, 6),
        "utilization_rate": round(util, 6),
        "deployed_capital_wei": int(deployed_capital_wei),
        "idle_capital_wei": int(max(0, idle)),
        "idle_capital_ratio": round(max(0.0, 1.0 - util), 6),
        "capital_turnover_rate": round(turnover, 6),
        "failure_adjusted_efficiency": round(
            (realized / deployed) * max(0.1, 1.0 - min(0.95, failures * 0.05)), 6
        ),
    }
