from __future__ import annotations

import asyncio
import json
from collections import deque
from victor_ai_bot.determinism import stable_uniform_0_1
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import aiohttp


_SAFE_WS_LOOP_EXCEPTIONS = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
    OSError,
    RuntimeError,
    ValueError,
)
_SAFE_PAYLOAD_EXCEPTIONS = (AttributeError, TypeError, ValueError, json.JSONDecodeError)


@dataclass
class MempoolStatus:
    connected: bool = False
    ws_url: str = ""
    last_error: str = ""
    last_msg_ts: float = 0.0


class MempoolMonitor:
    """Subscribe to pending transactions from one or more WebSocket sources.

    This is best-effort and intentionally conservative:
    - bounded queue
    - duplicate suppression across sources
    - reconnect with backoff per source
    - optional deterministic sampling to avoid overload

    NOTE: Some providers do not support pending tx subscriptions.
    """

    def __init__(
        self,
        *,
        ws_url: str = "",
        ws_urls: Optional[list[str]] = None,
        sample_rate: float = 1.0,
        max_queue: int = 5000,
        reconnect_backoff_s: float = 2.0,
    ):
        configured = list(ws_urls or [])
        if ws_url and ws_url not in configured:
            configured.insert(0, ws_url)
        self.ws_urls = [url for url in configured if isinstance(url, str) and url]
        self.ws_url = self.ws_urls[0] if self.ws_urls else ""
        self.sample_rate = max(0.0, min(1.0, float(sample_rate)))
        self.q: asyncio.Queue[str] = asyncio.Queue(maxsize=max(1, int(max_queue)))
        self._seen_hashes: deque[str] = deque(maxlen=max(1, int(max_queue) * 4))
        self._seen_hash_set: set[str] = set()
        self.status = MempoolStatus(connected=False, ws_url=self.ws_url)
        self.source_status: dict[str, MempoolStatus] = {
            url: MempoolStatus(connected=False, ws_url=url) for url in self.ws_urls
        }
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.reconnect_backoff_s = reconnect_backoff_s

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        if not self.ws_urls:
            self.status.connected = False
            self.status.last_error = "no_ws_url"
            return
        tasks = [asyncio.create_task(self._run_source(url)) for url in self.ws_urls]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            return
        finally:
            self._refresh_status()

    async def _run_source(self, ws_url: str) -> None:
        backoff = float(self.reconnect_backoff_s)
        while not self._stop.is_set():
            try:
                await self._connect_once(ws_url)
                backoff = float(self.reconnect_backoff_s)
            except asyncio.CancelledError:
                return
            except _SAFE_WS_LOOP_EXCEPTIONS as e:
                source = self.source_status[ws_url]
                source.connected = False
                source.last_error = f"ws_error:{type(e).__name__}:{e}"
                self._refresh_status()
                await asyncio.sleep(backoff)
                backoff = min(20.0, backoff * 1.5)

    @property
    def reconnect_backoff_s(self) -> float:
        return getattr(self, "_reconnect_backoff_s", 2.0)

    @reconnect_backoff_s.setter
    def reconnect_backoff_s(self, v: float) -> None:
        self._reconnect_backoff_s = float(v)

    def _refresh_status(self) -> None:
        sources = list(self.source_status.values())
        connected = any(item.connected for item in sources)
        latest = max(sources, key=lambda item: float(item.last_msg_ts or 0.0), default=None)
        self.status.connected = connected
        self.status.ws_url = self.ws_url
        self.status.last_msg_ts = float(latest.last_msg_ts) if latest is not None else 0.0
        self.status.last_error = ""
        for item in sources:
            if item.last_error:
                self.status.last_error = item.last_error

    def _enqueue_hash(self, tx_hash: str, *, source_url: str) -> None:
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            return
        if tx_hash in self._seen_hash_set:
            return
        if self.sample_rate < 1.0:
            u = stable_uniform_0_1(f"mempool:sample:{source_url}:{tx_hash}")
            if u > self.sample_rate:
                return
        if len(self._seen_hashes) == self._seen_hashes.maxlen:
            oldest = self._seen_hashes.popleft()
            self._seen_hash_set.discard(oldest)
        self._seen_hashes.append(tx_hash)
        self._seen_hash_set.add(tx_hash)
        if self.q.full():
            try:
                dropped = self.q.get_nowait()
                self._seen_hash_set.discard(dropped)
                try:
                    self._seen_hashes.remove(dropped)
                except ValueError:
                    pass
            except asyncio.QueueEmpty:
                pass
        try:
            self.q.put_nowait(tx_hash)
        except asyncio.QueueFull:
            self._seen_hash_set.discard(tx_hash)
            try:
                self._seen_hashes.remove(tx_hash)
            except ValueError:
                pass

    async def _connect_once(self, ws_url: Optional[str] = None) -> None:
        source_url = str(ws_url or self.ws_url)
        source = self.source_status.setdefault(
            source_url, MempoolStatus(connected=False, ws_url=source_url)
        )
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(source_url, heartbeat=20) as ws:
                source.connected = True
                source.last_error = ""
                self._refresh_status()

                sub = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"],
                }
                await ws.send_str(json.dumps(sub))

                msg = await ws.receive(timeout=10)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    raise RuntimeError("subscribe_failed")
                source.last_msg_ts = time.time()
                self._refresh_status()

                while not self._stop.is_set():
                    m = await ws.receive(timeout=30)
                    if m.type == aiohttp.WSMsgType.TEXT:
                        source.last_msg_ts = time.time()
                        self._refresh_status()
                        try:
                            payload = json.loads(m.data)
                            params = payload.get("params") or {}
                            result = params.get("result")
                            self._enqueue_hash(result, source_url=source_url)
                        except _SAFE_PAYLOAD_EXCEPTIONS:
                            continue
                    elif m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        raise RuntimeError("ws_closed")
                    else:
                        continue

    async def iter_hashes(self) -> AsyncIterator[str]:
        """Async iterator over deduplicated pending tx hashes."""
        while not self._stop.is_set():
            try:
                h = await self.q.get()
                yield h
            except asyncio.CancelledError:
                return
