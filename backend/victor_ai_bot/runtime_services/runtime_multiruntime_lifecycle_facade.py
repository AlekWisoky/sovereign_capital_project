from __future__ import annotations

import asyncio

_SAFE_MULTIRUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeMultiruntimeLifecycleFacade:
    """Non-hot-path multichain lifecycle/websocket compatibility helpers.

    These methods own active-chain switching, additive lifecycle start/stop,
    and websocket fan-in for MultiRuntimeBundle. They are shell/control logic
    and do not belong in the legacy runtime monolith.
    """

    def select_chain(self, chain_name: str) -> bool:
        if chain_name in self._runtimes:
            self._active_chain = chain_name
            if not self.ALLOW_AUTO_ALL:
                for name, rt in self._runtimes.items():
                    desired = bool(getattr(rt.cfg.execution, "auto_trading", False))
                    rt.set_settings(auto_trading=(desired if name == self._active_chain else False))
            return True
        return False

    def start(self) -> None:
        if not self.ALLOW_AUTO_ALL:
            for name, rt in self._runtimes.items():
                desired = bool(getattr(rt.cfg.execution, "auto_trading", False))
                rt.set_settings(auto_trading=(desired if name == self._active_chain else False))
        for rt in self._runtimes.values():
            rt.start()
        self._start_fan_in()

    async def stop(self) -> None:
        self._fan_stop.set()
        for t in list(self._fan_tasks):
            try:
                t.cancel()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        self._fan_tasks.clear()
        await asyncio.gather(*[rt.stop() for rt in self._runtimes.values()], return_exceptions=True)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._ws_clients.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        try:
            self._ws_clients.remove(q)
        except ValueError:
            pass

    def _start_fan_in(self) -> None:
        if self._fan_tasks:
            return
        self._fan_stop.clear()
        for chain_name, rt in self._runtimes.items():
            self._fan_tasks.append(asyncio.create_task(self._fan_one(chain_name, rt)))

    async def _fan_one(self, chain_name: str, rt) -> None:
        q = rt.subscribe()
        try:
            while not self._fan_stop.is_set():
                msg = await q.get()
                wrapped = {"chain": chain_name, **(msg or {})}
                for out_q in list(self._ws_clients):
                    try:
                        out_q.put_nowait(wrapped)
                    except (AttributeError, asyncio.QueueFull, RuntimeError, TypeError, ValueError):
                        pass
        except _SAFE_MULTIRUNTIME_EXCEPTIONS:
            return
        finally:
            try:
                rt.unsubscribe(q)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
