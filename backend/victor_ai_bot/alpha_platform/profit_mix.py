from __future__ import annotations

from typing import Any, Dict


def build_profit_mix(scorecards: Dict[str, Any]) -> Dict[str, Any]:
    families = list((scorecards or {}).get('families') or [])
    total = sum(max(0.0, float(x.get('realizedPnlUsd') or 0.0)) for x in families)
    items = []
    for row in families:
        pnl = max(0.0, float(row.get('realizedPnlUsd') or 0.0))
        items.append({
            'family': str(row.get('family') or ''),
            'contributionPct': round((pnl / total) * 100.0, 6) if total > 0 else 0.0,
            'returnOnDeployedCapital': round(float(row.get('gasEfficiency') or 0.0), 6),
            'failureAdjustedProfitability': round(float(row.get('stability') or 0.0) * pnl, 6),
            'costAdjustedProfitability': round(max(0.0, pnl - float(row.get('drawdownPenaltyUsd') or 0.0)), 6),
            'readinessToScale': round(min(1.0, float(row.get('stability') or 0.0) * max(0.0, float(row.get('gasEfficiency') or 0.0))), 6),
        })
    items.sort(key=lambda x: x['contributionPct'], reverse=True)
    return {'families': items, 'totalRealizedPnlUsd': round(total, 6)}
