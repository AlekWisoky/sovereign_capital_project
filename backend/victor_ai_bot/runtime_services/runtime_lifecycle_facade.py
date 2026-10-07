from __future__ import annotations

import asyncio
import time


_SAFE_LIFECYCLE_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)


class RuntimeLifecycleFacade:
    """Runtime lifecycle compatibility facade.

    This isolates non-hot-path start/stop orchestration helpers away from
    RuntimeBundle's main monolith while preserving the existing lifecycle
    surface and containment semantics for optional additive runtimes.
    """

    def _start_optional_runtimes(self) -> None:
        try:
            if getattr(self, "_arbitrage", None) is not None:
                self._arbitrage.start()
            if getattr(self, "_mev", None) is not None:
                self._mev.start()
            if getattr(self, "_meta", None) is not None:
                self._meta.start()
            if getattr(self, "_super", None) is not None:
                self._super.start()
            if getattr(self, "_fioa", None) is not None:
                self._fioa.start(self)
            if getattr(self, "_inl", None) is not None:
                self._inl.start(self)
        except _SAFE_LIFECYCLE_EXCEPTIONS:
            pass

    async def _stop_optional_runtimes(self) -> None:
        try:
            if getattr(self, "_arbitrage", None) is not None:
                await self._arbitrage.stop()
            if getattr(self, "_mev", None) is not None:
                await self._mev.stop()
            if getattr(self, "_meta", None) is not None:
                await self._meta.stop()
            if getattr(self, "_super", None) is not None:
                await self._super.stop()
            if getattr(self, "_inl", None) is not None:
                await self._inl.stop()
            if getattr(self, "_fioa", None) is not None:
                await self._fioa.stop()
        except _SAFE_LIFECYCLE_EXCEPTIONS:
            pass

    def _runtime_pool_events_start(self) -> None:
        event_cache = getattr(self, "_pool_event_cache", None)
        if event_cache is None or not callable(getattr(event_cache, "start", None)):
            return
        try:
            event_cache.start()
        except _SAFE_LIFECYCLE_EXCEPTIONS as exc:
            self._runtime_loop_telemetry["pool_event_start_error"] = (
                f"{type(exc).__name__}: {exc}"
            )

    async def _runtime_pool_events_stop(self) -> None:
        event_cache = getattr(self, "_pool_event_cache", None)
        if event_cache is None or not callable(getattr(event_cache, "stop", None)):
            return
        try:
            await event_cache.stop()
        except _SAFE_LIFECYCLE_EXCEPTIONS as exc:
            self._runtime_loop_telemetry["pool_event_stop_error"] = (
                f"{type(exc).__name__}: {exc}"
            )

    def _runtime_loop_done(self, task: asyncio.Task) -> None:
        telemetry = dict(getattr(self, "_runtime_loop_telemetry", {}) or {})
        telemetry["task_done"] = True
        telemetry["task_done_ms"] = int(time.time() * 1000)
        if task.cancelled():
            telemetry["task_status"] = "cancelled"
        else:
            try:
                error = task.exception()
            except _SAFE_LIFECYCLE_EXCEPTIONS as exc:
                error = exc
            if error is None:
                telemetry["task_status"] = "stopped"
            else:
                telemetry["task_status"] = "failed"
                telemetry["task_error"] = f"{type(error).__name__}: {error}"
        self._runtime_loop_telemetry = telemetry
        if not bool(getattr(self, "_stop", None) and self._stop.is_set()):
            try:
                self._task = None
                asyncio.get_running_loop().call_soon(self.start)
            except _SAFE_LIFECYCLE_EXCEPTIONS as exc:
                telemetry["self_heal_error"] = f"{type(exc).__name__}: {exc}"
                self._runtime_loop_telemetry = telemetry

    def start(self) -> None:
        if self._task and not self._task.done():
            telemetry = dict(getattr(self, "_runtime_loop_telemetry", {}) or {})
            telemetry["start_calls_while_running"] = int(
                telemetry.get("start_calls_while_running", 0) or 0
            ) + 1
            self._runtime_loop_telemetry = telemetry
            return
        self._stop.clear()
        self._runtime_loop_telemetry = {
            **dict(getattr(self, "_runtime_loop_telemetry", {}) or {}),
            "task_status": "starting",
            "task_created_ms": int(time.time() * 1000),
            "chain": str(
                getattr(getattr(self, "cfg", None), "chain", None)
                and getattr(self.cfg.chain, "name", "")
                or ""
            ),
        }
        self.rpc_manager.start()
        self._runtime_pool_events_start()
        self._start_optional_runtimes()
        if self._receipt_task is None or self._receipt_task.done():
            self._receipt_task = asyncio.create_task(self._receipt_loop())
        self._task = asyncio.create_task(self._loop())
        self._task.add_done_callback(self._runtime_loop_done)
        self._runtime_loop_telemetry["task_status"] = "scheduled"

    async def stop(self) -> None:
        self._stop.set()
        await self.rpc_manager.stop()
        await self._runtime_pool_events_stop()
        await self._stop_optional_runtimes()
        if self._receipt_task:
            try:
                self._receipt_task.cancel()
            except _SAFE_LIFECYCLE_EXCEPTIONS:
                pass
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except _SAFE_LIFECYCLE_EXCEPTIONS:
                pass
