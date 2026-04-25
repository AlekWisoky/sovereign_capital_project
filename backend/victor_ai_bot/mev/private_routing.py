from __future__ import annotations

from typing import Any, Dict


def private_route_policy(*, copy_risk: float, expected_edge_usd: float) -> Dict[str, Any]:
    lane = 'PRIVATE' if float(copy_risk) >= 0.65 or float(expected_edge_usd) > 50.0 else 'PROTECTED'
    return {'lane': lane, 'allowed': True, 'reason': 'defensive_private_routing'}
