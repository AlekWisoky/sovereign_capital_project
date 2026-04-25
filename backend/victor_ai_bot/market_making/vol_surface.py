from __future__ import annotations

from typing import Any, Dict


def vol_surface_point(*, realized_vol_pct: float, implied_vol_pct: float) -> Dict[str, Any]:
    edge = float(implied_vol_pct) - float(realized_vol_pct)
    return {'volEdgePct': round(edge, 6), 'quoteWidening': round(max(0.0, float(realized_vol_pct) / 100.0), 6)}
