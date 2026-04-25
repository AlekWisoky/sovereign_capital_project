from __future__ import annotations

from typing import Any, Dict, List

from .mempool_listener import parse_pending
from .private_routing import private_route_policy
from ..execution_capture.universal_actions import UniversalAction


def search_candidates(*, pending: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for row in parse_pending(pending):
        copy_risk = min(0.95, float((row or {}).get('copyRisk') or 0.4))
        edge = float((row or {}).get('protectedEdgeUsd') or 0.0)
        if edge <= 0.0:
            continue
        route = private_route_policy(copy_risk=copy_risk, expected_edge_usd=edge)
        act = UniversalAction(action_id=f"mev-{row.get('hash','')}" , family='mev_search', action_type='protected_backrun', route_family='mev_search', engine_type='mev_search', chain=str((row or {}).get('chain') or 'ethereum'), venues=['private_relay'], token_path=list((row or {}).get('tokenPath') or []), expected_profit_usd=edge, expected_realized_profit_usd=edge * 0.68, capital_required_usd=float((row or {}).get('capitalRequiredUsd') or 0.0), confidence=max(0.55, min(0.95, 0.60 + edge / 200.0)), lifecycle_stage='shadow_live', metadata={'preferredLane': route['lane'], 'victimTxHash': row.get('hash')})
        out.append(act.to_dict())
    return out
