from __future__ import annotations

import time
from typing import Any, Dict

from ..caq_kds.bus import BUS

_SAFE_POST_TICK_EXCEPTIONS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
)


class RuntimePostTickFacade:
    """Same-iteration research/observability tail compatibility facade.

    This isolates RuntimeBundle's post-scan meta/quicksight coordination away
    from the main tick loop while preserving the existing degraded-state
    semantics: skip all same-iteration tails after a contained per-tick bug,
    swallow only local shape/state failures, and let unexpected bugs escape to
    the runtime task boundary rather than silently hiding them.
    """

    async def _post_tick_meta_tail(self) -> bool:
        try:
            if getattr(self, "_meta", None) is None:
                return False
            await self._meta.tick(self)
            return True
        except _SAFE_POST_TICK_EXCEPTIONS:
            return False

    def _quicksight_tick_state(self) -> Dict[str, Any]:
        return {
            "ts": int(time.time()),
            "market": BUS.get("market") or {},
            "treasury": BUS.get("treasury") or {},
            "behaveagent": BUS.get("behaveagent") or {},
            "governance": (
                self._gov.snapshot() if getattr(self, "_gov", None) is not None else {}
            ),
            "pnl": {},
            "circuit_breaker": (
                self._cb.snapshot() if getattr(self, "_cb", None) is not None else {}
            ),
            "agent_perf": (
                self._agent_perf.snapshot() if getattr(self, "_agent_perf", None) is not None else {}
            ),
        }

    async def _post_tick_quicksight_tail(self) -> bool:
        try:
            if getattr(self, "_quicksight", None) is None:
                return False
            await self._quicksight.tick(state=self._quicksight_tick_state())
            return True
        except _SAFE_POST_TICK_EXCEPTIONS:
            return False

    async def _run_post_tick_tails(self, *, tick_failed: bool) -> bool:
        if bool(tick_failed):
            return False
        await self._post_tick_meta_tail()
        await self._post_tick_quicksight_tail()
        return True
