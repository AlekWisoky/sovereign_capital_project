from __future__ import annotations

import asyncio


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

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self.rpc_manager.start()
        self._start_optional_runtimes()
        if self._receipt_task is None or self._receipt_task.done():
            self._receipt_task = asyncio.create_task(self._receipt_loop())
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        await self.rpc_manager.stop()
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
