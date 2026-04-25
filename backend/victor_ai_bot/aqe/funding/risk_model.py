from __future__ import annotations

from typing import Dict


def funding_risk_adjustment(*, leverage: float, collateral_efficiency: float, liquidation_buffer_pct: float, divergence_score: float) -> Dict[str, float]:
    liq_pen = max(0.0, (10.0 - float(liquidation_buffer_pct)) / 100.0)
    lev_pen = max(0.0, float(leverage) - 1.0) * 0.015
    collat_pen = max(0.0, 0.9 - float(collateral_efficiency)) * 0.20
    div_pen = max(0.0, float(divergence_score)) * 0.25
    total = liq_pen + lev_pen + collat_pen + div_pen
    return {
        'risk_penalty_ratio': round(total, 8),
        'liquidation_penalty': round(liq_pen, 8),
        'collateral_penalty': round(collat_pen, 8),
        'divergence_penalty': round(div_pen, 8),
    }
