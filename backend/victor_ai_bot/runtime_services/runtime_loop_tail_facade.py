from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

_SAFE_LOOP_TAIL_EXCEPTIONS = (
    AttributeError,
    KeyError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeLoopTailFacade:
    """End-of-iteration reporting/health compatibility facade.

    This isolates RuntimeBundle's non-hot-path loop tail away from the main
    orchestration body while preserving existing semantics:
    - websocket/operator broadcast still happens first and is not swallowed
    - loop latency recording remains best-effort
    - PnL-store health/cache metrics remain best-effort
    - each iteration still yields with the existing bounded sleep
    """

    def _record_loop_latency_tail(self, *, loop_started_at: float) -> None:
        try:
            loop_ms = float((time.perf_counter() - float(loop_started_at)) * 1000.0)
            control = getattr(self, "_runtime_control_service", None)
            if control is not None and hasattr(control, "record_loop_latency"):
                control.record_loop_latency(self, loop_ms)
            else:
                self.metrics.last_tick_ms = int(loop_ms)
        except _SAFE_LOOP_TAIL_EXCEPTIONS:
            pass

    def _record_pnl_store_tail_metrics(self) -> Dict[str, Any]:
        try:
            st = self._pnl.stats() if getattr(self, "_pnl", None) is not None else {}
            if isinstance(st, dict):
                self.metrics.db_latency_ms = float(st.get("last_db_ms", 0.0) or 0.0)
                self.metrics.db_latency_ema_ms = float(st.get("ema_db_ms", 0.0) or 0.0)
                self.metrics.db_errors = int(st.get("db_errors", 0) or 0)
                self.metrics.pnl_summary_cache_hits = int(st.get("summary_cache_hits", 0) or 0)
                self.metrics.pnl_summary_cache_misses = int(
                    st.get("summary_cache_misses", 0) or 0
                )
                self.metrics.pnl_income_cache_hits = int(st.get("income_cache_hits", 0) or 0)
                self.metrics.pnl_income_cache_misses = int(
                    st.get("income_cache_misses", 0) or 0
                )
                return dict(st)
        except _SAFE_LOOP_TAIL_EXCEPTIONS:
            pass
        return {}

    async def _run_loop_iteration_tail(self, *, loop_started_at: float) -> None:
        await self._broadcast()
        self._record_loop_latency_tail(loop_started_at=float(loop_started_at))
        self._record_pnl_store_tail_metrics()
        await asyncio.sleep(0.1)
