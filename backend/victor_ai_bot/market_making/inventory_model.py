from __future__ import annotations

from typing import Any, Dict


def inventory_limits(*, inventory_usd: float, max_inventory_usd: float) -> Dict[str, Any]:
    usage = max(0.0, float(inventory_usd)) / max(1.0, float(max_inventory_usd))
    return {'usage': round(usage, 6), 'canQuote': usage < 1.0, 'rebalanceNeeded': usage > 0.8}
