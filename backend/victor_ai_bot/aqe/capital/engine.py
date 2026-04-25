from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CapitalBucket:
    name: str
    usd: float
    meta: Dict[str, Any] = field(default_factory=dict)


class CapitalAllocator:
    """Capital allocation overlay.

    Allocation uses expected_return / margin_required as a simple deterministic
    proxy. This is *not* a trading engine; it only emits constraints.
    """

    def __init__(self):
        self.last_allocation: Dict[str, Any] = {}

    def allocate(
        self,
        *,
        buckets: List[CapitalBucket],
        opportunities: List[Dict[str, Any]],
        max_fraction_per_trade: float = 0.15,
    ) -> Dict[str, Any]:
        total = sum(float(b.usd) for b in buckets)
        total = max(1e-9, total)
        # Rank by efficiency = expected_return / max(margin_required, 1)
        scored = []
        for o in opportunities:
            er = float(o.get("expected_return", 0.0) or 0.0)
            mr = float(o.get("margin_required", 1.0) or 1.0)
            scored.append((er / max(1e-9, mr), o))
        scored.sort(key=lambda x: float(x[0]), reverse=True)

        # Suggested cap for each trade (USD) based on total + max_fraction
        cap_usd = float(total) * float(max(0.01, min(0.50, max_fraction_per_trade)))
        out = {
            "ts": int(time.time()),
            "total_usd": float(total),
            "per_trade_cap_usd": float(cap_usd),
            "top": [dict(x[1]) for x in scored[:10]],
        }
        self.last_allocation = out
        return out


class InventoryManager:
    def __init__(self):
        self.last: Dict[str, Any] = {}

    def snapshot(self) -> Dict[str, Any]:
        return dict(self.last)


class MarginOptimizer:
    def __init__(self):
        self.last: Dict[str, Any] = {}

    def optimize(self, *, venues: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Placeholder for a real optimizer.
        out = {"ts": int(time.time()), "venues": list(venues), "note": "margin_optimizer_placeholder"}
        self.last = out
        return out
