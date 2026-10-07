from __future__ import annotations

from typing import Any
import time

from victor_ai_bot.rpc import JsonRpcClient


class RuntimeLoopEntryFacade:
    """Own the outer runtime loop entry iteration.

    This facade intentionally does not own the broad per-tick containment.
    It only owns the read-RPC selection, client context setup, and delegation
    into the prepared/contained tick pipeline.
    """

    async def _run_loop_entry_iteration(self, *, loop_started_at: float) -> None:
        loop_telemetry = dict(getattr(self, "_runtime_loop_telemetry", {}) or {})
        loop_telemetry["last_loop_entered_ms"] = int(time.time() * 1000)
        loop_telemetry["task_status"] = "running"
        self._runtime_loop_telemetry = loop_telemetry
        # Prefer currently healthy/readable endpoints, but always retain the
        # configured best endpoint as a bootstrap fallback. A single provider
        # outage must not suppress an entire chain's discovery cycle.
        read_candidates = getattr(self.rpc_manager, "read_candidates", None)
        candidates = list(read_candidates() or []) if callable(read_candidates) else []
        bootstrap_url = self.rpc_manager.best_read()

        # The configured read universe is the authoritative bootstrap fallback.
        # RpcManager may temporarily lose its live endpoint map after an
        # operator/provider-state mutation; in that case an empty candidate set
        # must not strand the scanner indefinitely.
        if not bootstrap_url:
            configured = list(
                getattr(getattr(self, "cfg", None), "chain", None)
                and getattr(self.cfg.chain, "rpc_read", None)
                or []
            )
            configured = [str(url) for url in configured if str(url).strip()]
            if configured:
                sync_preferences = getattr(self.rpc_manager, "sync_read_preferences", None)
                if callable(sync_preferences):
                    try:
                        sync_preferences(configured)
                    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                        pass
                candidates = list(dict.fromkeys([*configured, *candidates]))
                bootstrap_url = candidates[0] if candidates else configured[0]

        if bootstrap_url:
            candidates.insert(0, bootstrap_url)
        candidates = list(dict.fromkeys(str(url) for url in candidates if str(url).strip()))
        if not candidates:
            telemetry = dict(getattr(self, "_market_pipeline_telemetry", {}) or {})
            telemetry["scan_status"] = "blocked_before_scan"
            telemetry["scan_error"] = "no_read_rpc_candidates"
            telemetry["rpc"] = {
                "endpoint": "",
                "provider": "",
                "ok": False,
                "configured_read_count": len(
                    list(
                        getattr(getattr(self, "cfg", None), "chain", None)
                        and getattr(self.cfg.chain, "rpc_read", None)
                        or []
                    )
                ),
            }
            self._market_pipeline_telemetry = telemetry
            await self._sleep(1.0)
            return

        for bootstrap_url in candidates:
            self._runtime_loop_telemetry = {
                **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                "phase": "bootstrap_rpc",
                "phase_started_ms": int(time.time() * 1000),
                "bootstrap_endpoint": str(bootstrap_url),
            }
            preselected_scan = None
            selected_url = bootstrap_url
            current_block = None

            async with JsonRpcClient(
                bootstrap_url, timeout_s=10.0, max_concurrency=30, max_batch=80
            ) as bootstrap_rpc:
                bn = await self._prepare_tick_iteration(rpc=bootstrap_rpc)
                if bn is None:
                    # _prepare_tick_iteration records the pre-scan failure in
                    # market telemetry. Try the next readable provider before
                    # declaring the chain unavailable for this block.
                    continue
                current_block = int(bn)

                if hasattr(self, "_resolve_amount_in"):
                    self._runtime_loop_telemetry = {
                        **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                        "phase": "provider_comparison",
                        "phase_started_ms": int(time.time() * 1000),
                    }
                    try:
                        amount_in = int(self._resolve_amount_in())
                        selection = await self._select_rpc_and_scan(
                            bootstrap_rpc=bootstrap_rpc,
                            current_block=current_block,
                            amount_in=amount_in,
                        )
                        selected_url = str(selection.get("selected_endpoint") or bootstrap_url)
                        preselected_scan = selection
                        self._runtime_loop_telemetry = {
                            **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                            "phase": "selected_provider_scan",
                            "phase_started_ms": int(time.time() * 1000),
                        }
                    except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
                        selected_url = bootstrap_url
                        preselected_scan = None

                if preselected_scan is None:
                    await self._run_contained_tick_iteration(
                        rpc=bootstrap_rpc,
                        current_block=current_block,
                        loop_started_at=loop_started_at,
                    )
                    telemetry = getattr(self, "_market_pipeline_telemetry", {}) or {}
                    if isinstance(telemetry, dict):
                        quotes = telemetry.get("quotes") or {}
                        try:
                            self.rpc_manager.observe_quote_telemetry(
                                bootstrap_url,
                                requests=int(quotes.get("requests", 0) or 0),
                                successes=int(quotes.get("successes", 0) or 0),
                                failure_reasons=dict(quotes.get("failure_reasons") or {}),
                            )
                        except (AttributeError, TypeError, ValueError):
                            pass
                    self._runtime_loop_telemetry = {
                        **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                        "phase": "idle",
                        "last_completed_tick_ms": int(time.time() * 1000),
                    }
                    return

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
                        pass
                self._runtime_loop_telemetry = {
                    **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
                    "phase": "idle",
                    "last_completed_tick_ms": int(time.time() * 1000),
                }
                return

        await self._sleep(1.0)

    async def _sleep(self, seconds: float) -> None:
        import asyncio
        await asyncio.sleep(seconds)
