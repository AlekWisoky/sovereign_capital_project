from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List

import aiohttp

from .rpc import JsonRpcClient
from .gas_model import select_consensus_gas_price


@dataclass
class EndpointStats:
    url: str
    ok: bool = True
    latency_ema_ms: float = 250.0
    failures: int = 0
    last_error: str | None = None
    last_seen_block: int | None = None
    updated_at: float = field(default_factory=lambda: time.time())
    quote_failures: int = 0
    quote_successes: int = 0
    quote_last_error: str | None = None
    quote_unhealthy_until: float = 0.0

    def score(self) -> float:
        # Hard-penalize unhealthy endpoints so flakey URLs never win selection
        # simply because they were fast in the past.
        penalty = 1.0 + min(self.failures, 10) * 0.5
        if not self.ok:
            penalty *= 10_000.0
        # If we've never observed a block, treat as unhealthy.
        if self.last_seen_block is None:
            penalty *= 50.0
        if self.quote_unhealthy_until > time.time():
            penalty *= 10_000.0
        else:
            penalty *= 1.0 + min(self.quote_failures, 10) * 0.25
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
        self._configured_read = list(dict.fromkeys(rpc_read))
        self.rpc_read = list(self._configured_read)
        self.rpc_send = list(dict.fromkeys(rpc_send or rpc_read))
        self.rpc_private = list(dict.fromkeys((rpc_private or [])))
        self.timeout_s = timeout_s
        self.probe_interval_s = probe_interval_s
        self._read: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_read}
        self._send: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_send}
        self._private: Dict[str, EndpointStats] = {u: EndpointStats(u) for u in self.rpc_private}
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._gas_consensus_cache: tuple[float, dict] | None = None
        self._gas_consensus_lock = asyncio.Lock()

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

    def sync_read_preferences(self, preferred: List[str] | None = None) -> List[str]:
        """Synchronize operator read preferences into the live quote-provider universe.

        Configured endpoints remain authoritative defaults; preferences add
        operator-selected read endpoints and can be removed without disturbing
        configured endpoints. Existing health/quote telemetry is retained for
        endpoints that remain in the universe.
        """
        preferred_urls = list(
            dict.fromkeys(
                str(url).strip()
                for url in list(preferred or [])
                if str(url).strip()
            )
        )
        merged = list(dict.fromkeys([*self._configured_read, *preferred_urls]))
        existing = self._read
        self._read = {url: existing.get(url) or EndpointStats(url) for url in merged}
        self.rpc_read = list(merged)
        return list(merged)

    def read_candidates(self) -> List[str]:
        """Return read endpoints in operational-score order for quote comparison."""
        return [
            stats.url
            for stats in sorted(self._read.values(), key=lambda item: item.score())
            if stats.ok and float(stats.quote_unhealthy_until or 0.0) <= time.time()
        ]

    def best_read(self) -> str:
        return min(self._read.values(), key=lambda s: s.score()).url if self._read else ""

    def observe_quote_telemetry(
        self,
        url: str,
        *,
        requests: int,
        successes: int,
        failure_reasons: Dict[str, int] | None = None,
    ) -> None:
        """Feed quote-layer health back into read-endpoint selection.

        Basic block probes can succeed while quote traffic is throttled or
        transported poorly. Reverts are deliberately excluded because they
        commonly originate from the quoted pool/contract rather than the RPC.
        """
        stats = self._read.get(str(url))
        if stats is None:
            return
        req = max(0, int(requests))
        ok = max(0, int(successes))
        failures = {
            str(key): max(0, int(value))
            for key, value in dict(failure_reasons or {}).items()
        }
        provider_failures = sum(
            value
            for key, value in failures.items()
            if key in {
                "rpc_rate_limited",
                "rpc_timeout",
                "rpc_transport_or_provider_error",
                "rpc_error",
                "rpc_error_unknown",
                "missing_batch_response",
            }
            or key.startswith("rpc_error_")
        )
        stats.quote_successes += ok
        stats.quote_failures += provider_failures
        if provider_failures:
            stats.quote_last_error = max(
                ((key, value) for key, value in failures.items() if value),
                key=lambda item: item[1],
                default=("quote_provider_error", provider_failures),
            )[0]
            stats.quote_unhealthy_until = max(
                stats.quote_unhealthy_until,
                time.time() + 30.0,
            )
        elif ok > 0:
            stats.quote_unhealthy_until = 0.0
            stats.quote_last_error = None
            stats.quote_failures = max(0, stats.quote_failures - 1)


    async def gas_price_consensus(self, *, max_providers: int = 8, cache_ttl_s: float = 5.0) -> dict:
        """Observe gas price + block from multiple read RPCs and fail closed on disagreement."""
        now = time.time()
        cached = self._gas_consensus_cache
        if cached is not None and now - float(cached[0]) <= max(0.0, float(cache_ttl_s)):
            return dict(cached[1])

        async with self._gas_consensus_lock:
            now = time.time()
            cached = self._gas_consensus_cache
            if cached is not None and now - float(cached[0]) <= max(0.0, float(cache_ttl_s)):
                return dict(cached[1])

            urls = self.read_candidates()[: max(2, int(max_providers))]
            async def observe(url: str) -> dict:
                try:
                    async with JsonRpcClient(
                        url,
                        timeout_s=min(float(self.timeout_s), 8.0),
                        max_concurrency=2,
                        max_batch=4,
                    ) as rpc:
                        block, price = await asyncio.gather(rpc.block_number(), rpc.gas_price())
                    if block is None or price is None or int(price) <= 0:
                        return {
                            "url": url,
                            "provider": url.split("//", 1)[-1].split("/", 1)[0],
                            "block_number": int(block) if block is not None else -1,
                            "gas_price_wei": int(price) if price is not None else 0,
                            "error": "gas_price_or_block_unavailable",
                        }
                    return {
                        "url": url,
                        "provider": url.split("//", 1)[-1].split("/", 1)[0],
                        "block_number": int(block),
                        "gas_price_wei": int(price),
                    }
                except _SAFE_RPC_MANAGER_PROBE_EXCEPTIONS as exc:
                    return {
                        "url": url,
                        "provider": url.split("//", 1)[-1].split("/", 1)[0],
                        "block_number": -1,
                        "gas_price_wei": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }

            observations = await asyncio.gather(*(observe(url) for url in urls))
            consensus = select_consensus_gas_price([dict(item) for item in observations])
            result = {
                **consensus,
                "observations": [dict(item) for item in observations],
                "observed_at": now,
                "provider_count": len(observations),
            }
            self._gas_consensus_cache = (time.time(), result)
            return dict(result)

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
                "quote_failures": s.quote_failures,
                "quote_successes": s.quote_successes,
                "quote_last_error": s.quote_last_error,
                "quote_unhealthy_until": s.quote_unhealthy_until,
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
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.probe_interval_s)
            except asyncio.TimeoutError:
                # Normal probe interval expiry; keep the manager loop alive.
                continue
