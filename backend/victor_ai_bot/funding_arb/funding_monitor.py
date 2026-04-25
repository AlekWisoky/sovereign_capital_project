from __future__ import annotations

from typing import Any, Dict, List


def monitor_funding(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        annualized = float((r or {}).get('annualizedFundingPct') or 0.0)
        if abs(annualized) < 5.0:
            continue
        out.append({'symbol': str((r or {}).get('symbol') or ''), 'annualizedFundingPct': annualized, 'venue': str((r or {}).get('venue') or '')})
    return out
