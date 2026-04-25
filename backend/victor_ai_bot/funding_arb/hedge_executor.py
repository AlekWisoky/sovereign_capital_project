from __future__ import annotations

from typing import Any, Dict


def hedge_plan(*, symbol: str, notional_usd: float, spot_venue: str, perp_venue: str) -> Dict[str, Any]:
    return {'symbol': symbol, 'notionalUsd': float(notional_usd), 'legs': [{'venue': spot_venue, 'side': 'buy'}, {'venue': perp_venue, 'side': 'sell'}], 'hedged': True}
