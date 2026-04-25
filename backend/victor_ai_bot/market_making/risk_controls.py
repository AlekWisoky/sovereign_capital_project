from __future__ import annotations

from typing import Any, Dict


def mm_risk_posture(*, inventory_usage: float, vol_edge_pct: float) -> Dict[str, Any]:
    severe = float(inventory_usage) > 0.95 or float(vol_edge_pct) < -10.0
    return {'allowed': not severe, 'reason': 'inventory_or_vol_risk' if severe else 'ok'}
