from __future__ import annotations

import asyncio
from typing import Any

_SAFE_AUTO_QUEUE_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeAutoQueueFacade:
    """Portfolio-recommendation auto-queue compatibility facade.

    This isolates the additive, non-submission auto-queue refresh path away
    from RuntimeBundle's legacy tick loop while preserving the existing
    portfolio-driven queue semantics used by decision-selected auto trading.
    """

    def _refresh_auto_queue_from_decision(self, decision: Any, *, current_block: int) -> bool:
        try:
            portfolio = getattr(decision, "portfolio", None)
            if not portfolio:
                return False
            self._auto_queue = list(portfolio or [])
            self._auto_queue_block = int(current_block)
            return True
        except _SAFE_AUTO_QUEUE_EXCEPTIONS:
            return False
