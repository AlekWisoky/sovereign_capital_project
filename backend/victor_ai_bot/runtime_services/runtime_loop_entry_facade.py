from __future__ import annotations

from typing import Any

from victor_ai_bot.rpc import JsonRpcClient


class RuntimeLoopEntryFacade:
    """Own the outer runtime loop entry iteration.

    This facade intentionally does not own the broad per-tick containment.
    It only owns the read-RPC selection, client context setup, and delegation
    into the prepared/contained tick pipeline.
    """

    async def _run_loop_entry_iteration(self, *, loop_started_at: float) -> None:
        read_url = self.rpc_manager.best_read()
        if not read_url:
            await self._sleep(1.0)
            return

        async with JsonRpcClient(
            read_url, timeout_s=10.0, max_concurrency=30, max_batch=80
        ) as rpc:
            bn = await self._prepare_tick_iteration(rpc=rpc)
            if bn is None:
                return
            await self._run_contained_tick_iteration(
                rpc=rpc,
                current_block=int(bn),
                loop_started_at=loop_started_at,
            )
            telemetry = getattr(self, "_market_pipeline_telemetry", {}) or {}
            if isinstance(telemetry, dict):
                quotes = telemetry.get("quotes") or {}
                try:
                    self.rpc_manager.observe_quote_telemetry(
                        read_url,
                        requests=int(quotes.get("requests", 0) or 0),
                        successes=int(quotes.get("successes", 0) or 0),
                        failure_reasons=dict(quotes.get("failure_reasons") or {}),
                    )
                except (AttributeError, TypeError, ValueError):
                    # Quote telemetry is observational; never let health feedback
                    # interrupt the existing scan/execution containment path.
                    pass

    async def _sleep(self, seconds: float) -> None:
        import asyncio
        await asyncio.sleep(seconds)
