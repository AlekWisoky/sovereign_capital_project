from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List

import aiohttp

from .rpc import JsonRpcClient


@dataclass
class EndpointStats:
    url: str
    ok: bool = True
    latency_ema_ms: float = 250.0
    failures: int = 0
    last_error: str | None = None
    last_seen_block: int | None = None
    updated_at: float = field(default_factory=lambda: time.time())

    def score(self) -> float:
        # Hard-penalize unhealthy endpoints so flakey URLs never win selection
        # simply because they were fast in the past.
        penalty = 1.0 + min(self.failures, 10) * 0.5
        if not self.ok:
            penalty *= 10_000.0
        # If we've never observed a block, treat as unhealthy.
        if self.last_seen_block is None:
            penalty *= 50.0
        return self.latency_ema_ms * penalty


_SAFE_RPC_MANAGER_PROBE_EXCEPTIONS = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_RPC_MANAGER_STOP_EXCEPTIONS = (asyncio.TimeoutError, RuntimeError)


class RpcManager:
    def __init__(
        self,
        *,
        rpc_read: List[str],
        rpc_send: List[str],
        rpc_private: List[str] | None = None,
        timeout_s: float = 8.0,
        probe_interval_s: float = 15.0,
    ):
        self.rpc_read = list(dict.fromkeys(rpc_read))
        self.rpc_send = list(dict.fromkeys(rpc_send or rpc_read))
        self.rpc_private = list(dict.fromkeys((rpc_private or [])))
        self.timeout_s = timeout_s
        self.probe_interval_s = probe_interval_s
        self._read: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_read}
        self._send: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_send}
        self._private: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_private}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except _SAFE_RPC_MANAGER_STOP_EXCEPTIONS:
                pass

    def best_read(self) -> str:
        return min(self._read.values(), key=lambda s: s.score()).url if self._read else ""

    def best_send(self) -> str:
        return (
            min(self._send.values(), key=lambda s: s.score()).url
            if self._send
            else self.best_read()
        )

    def best_private(self) -> str:
        return min(self._private.values(), key=lambda s: s.score()).url if self._private else ""

    def snapshot(self) -> dict:
        def row(s: EndpointStats) -> dict:
            return {
                "url": s.url,
                "ok": s.ok,
                "latency_ms": round(s.latency_ema_ms, 1),
                "failures": s.failures,
                "last_error": s.last_error,
                "last_seen_block": s.last_seen_block,
                "score": round(s.score(), 1),
            }

        return {
            "read": [row(s) for s in sorted(self._read.values(), key=lambda x: x.score())],
            "send": [row(s) for s in sorted(self._send.values(), key=lambda x: x.score())],
            "private": [row(s) for s in sorted(self._private.values(), key=lambda x: x.score())],
        }

    async def _probe_one(self, url: str, stats: EndpointStats) -> None:
        try:
            async with JsonRpcClient(
                url, timeout_s=self.timeout_s, max_concurrency=3, max_batch=10
            ) as rpc:
                t0 = time.perf_counter()
                bn = await rpc.block_number()
                dt = (time.perf_counter() - t0) * 1000.0
                if bn is None:
                    raise RuntimeError("block_number failed")
                stats.ok = True
                stats.last_seen_block = bn
                stats.last_error = None
                stats.latency_ema_ms = stats.latency_ema_ms * 0.8 + dt * 0.2
                stats.failures = max(0, stats.failures - 1)
                stats.updated_at = time.time()
        except _SAFE_RPC_MANAGER_PROBE_EXCEPTIONS as e:
            stats.ok = False
            stats.failures += 1
            stats.last_error = str(e)
            stats.updated_at = time.time()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            tasks = []
            for u, s in list(self._read.items()):
                tasks.append(self._probe_one(u, s))
            for u, s in list(self._send.items()):
                tasks.append(self._probe_one(u, s))
            for u, s in list(self._private.items()):
                tasks.append(self._probe_one(u, s))
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.wait([self._stop.wait()], timeout=self.probe_interval_s)
