from __future__ import annotations

from typing import Any, Dict, Iterable


def netting_summary(positions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    net: Dict[str, float] = {}
    for p in positions:
        asset = str((p or {}).get("asset") or "")
        net[asset] = float(net.get(asset, 0.0)) + float((p or {}).get("amount") or 0.0)
    return {
        "netPositions": {k: round(v, 8) for k, v in net.items()},
        "nettableAssets": sum(1 for v in net.values() if abs(v) > 1e-9),
    }
