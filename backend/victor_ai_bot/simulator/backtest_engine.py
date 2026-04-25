from __future__ import annotations

from typing import Any, Dict, Iterable


def run_backtest(samples: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    pnl = 0.0; count = 0
    for row in samples:
        pnl += float((row or {}).get('realizedPnlUsd') or 0.0); count += 1
    return {'count': count, 'realizedPnlUsd': round(pnl, 8), 'avgPnlUsd': round(pnl / max(1, count), 8)}
