from __future__ import annotations

import asyncio
import time
from typing import List

from ..models import Opportunity

_SAFE_POSTDECISION_EXCEPTIONS = (
    AttributeError,
    asyncio.QueueFull,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimePostdecisionStateFacade:
    """Post-decision analytics/publication compatibility facade.

    This isolates analytics-only and publication-only work that happens after
    decision shaping but before the tick exits, while preserving current
    semantics:
    - unit economics remains analytics-only and best-effort
    - execution-capture ordering remains best-effort local annotation
    - runtime opportunity state and scan metrics still commit on success
    - CAQ-KDS DEX summary publication remains add-only
    - unexpected bugs still escape to the process boundary
    """

    async def _run_postdecision_analytics_state(
        self,
        *,
        opps: List[Opportunity],
        rpc,
        regime_label: str,
        current_block: int,
        loop_started_at: float,
    ) -> bool:
        await self._annotate_unit_economics(
            opps=opps,
            rpc=rpc,
            current_block=int(current_block),
        )

        try:
            self._annotate_execution_capture(opps, str(regime_label or "balanced"))
        except _SAFE_POSTDECISION_EXCEPTIONS:
            pass

        async with self._state_lock:
            self._opps = opps
        self.metrics.scan_ms = int((time.perf_counter() - float(loop_started_at)) * 1000.0)
        self.metrics.last_error = ""
        self._publish_dex_scan_summary(opps=opps)
        return True
