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
        bootstrap_url = self.rpc_manager.best_read()
        if not bootstrap_url:
            await self._sleep(1.0)
            return

        preselected_scan = None
        selected_url = bootstrap_url
        current_block = None

        async with JsonRpcClient(
            bootstrap_url, timeout_s=10.0, max_concurrency=30, max_batch=80
        ) as bootstrap_rpc:
            bn = await self._prepare_tick_iteration(rpc=bootstrap_rpc)
            if bn is None:
                return
            current_block = int(bn)
            try:
                amount_in = int(self._resolve_amount_in())
                selection = await self._select_rpc_and_scan(
                    bootstrap_rpc=bootstrap_rpc,
                    current_block=current_block,
                    amount_in=amount_in,
                )
                selected_url = str(selection.get("selected_endpoint") or bootstrap_url)
                preselected_scan = selection
            except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                selected_url = bootstrap_url
                preselected_scan = None

        async with JsonRpcClient(
            selected_url, timeout_s=10.0, max_concurrency=30, max_batch=80
        ) as rpc:
            await self._run_contained_tick_iteration(
                rpc=rpc,
                current_block=int(current_block),
                loop_started_at=loop_started_at,
                preselected_scan=preselected_scan,
            )
            telemetry = getattr(self, "_market_pipeline_telemetry", {}) or {}
            if isinstance(telemetry, dict):
                quotes = telemetry.get("quotes") or {}
                try:
                    self.rpc_manager.observe_quote_telemetry(
                        selected_url,
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
