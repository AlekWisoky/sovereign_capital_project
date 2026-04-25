from __future__ import annotations

from typing import Any, Dict


def quote_policy(*, mid: float, vol_pct: float, inventory_skew: float) -> Dict[str, Any]:
    spread_bps = max(4.0, float(vol_pct) * 0.8 + abs(float(inventory_skew)) * 10.0)
    return {'bid': round(float(mid) * (1.0 - spread_bps / 20_000.0), 8), 'ask': round(float(mid) * (1.0 + spread_bps / 20_000.0), 8), 'spreadBps': round(spread_bps, 6)}
