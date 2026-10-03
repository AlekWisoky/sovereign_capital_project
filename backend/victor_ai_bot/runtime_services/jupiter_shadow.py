from __future__ import annotations

import os
from typing import Any

from .solana_jupiter import JupiterSwapV2Client

class JupiterShadowService:
    """Bounded, read-only Jupiter synchronization state; never execution authority."""
    def __init__(self) -> None:
        self.enabled = bool(int(os.getenv("VICTOR_SOLANA_JUPITER_ENABLED", "0") or 0))
        self.max_pairs = max(1, int(os.getenv("VICTOR_SOLANA_JUPITER_MAX_PAIRS", "24") or 24))
        self.max_sizes = max(1, int(os.getenv("VICTOR_SOLANA_JUPITER_MAX_SIZES", "7") or 7))
        self.client = JupiterSwapV2Client()
        self._last = {
            "enabled": self.enabled, "configured": self.client.configured,
            "status": "disabled" if not self.enabled else ("configured" if self.client.configured else "unconfigured"),
            "quotes": {"requests": 0, "successes": 0, "failures": 0},
            "opportunities": {"authoritative": 0, "diagnostic": 0},
            "economic_frontier": None, "execution_authority": False,
        }
    def snapshot(self) -> dict[str, Any]:
        return dict(self._last)
    async def quote_pairs(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            return self.snapshot()
        bounded = list(requests[: self.max_pairs * self.max_sizes])
        results = await self.client.quote_matrix(bounded, concurrency=4)
        successes = sum(item is not None for item in results)
        self._last = {**self._last, "quotes": {"requests": len(bounded), "successes": successes, "failures": len(bounded) - successes}, "status": "healthy" if successes else "quote_unavailable", "execution_authority": False}
        return self.snapshot()
