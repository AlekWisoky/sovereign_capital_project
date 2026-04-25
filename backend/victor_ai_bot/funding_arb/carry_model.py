from __future__ import annotations

from typing import Any, Dict


def carry_horizon_value(*, annualized_funding_pct: float, notional_usd: float, hours: float, fee_drag_pct: float, basis_drag_pct: float) -> Dict[str, Any]:
    gross = float(notional_usd) * (float(annualized_funding_pct) / 100.0) * max(0.0, float(hours)) / 8760.0
    drag = float(notional_usd) * (float(fee_drag_pct) + float(basis_drag_pct)) / 100.0
    return {'grossCarryUsd': round(gross, 8), 'netCarryUsd': round(gross - drag, 8)}
