from __future__ import annotations

from typing import Any, Dict


def collateral_risk(*, collateral_efficiency: float, liquidation_buffer_pct: float) -> Dict[str, Any]:
    penalty = max(0.0, 0.6 - float(collateral_efficiency)) + max(0.0, 10.0 - float(liquidation_buffer_pct)) / 20.0
    return {'riskPenalty': round(min(0.8, penalty), 6), 'reason': 'funding_risk_model'}
