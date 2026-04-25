from __future__ import annotations

import asyncio
import json
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
    """Subscribe to `newPendingTransactions` via WebSocket.

    This is best-effort and intentionally conservative:
    - bounded queue
    - reconnect with backoff
    - optional sampling to avoid overload

    NOTE: Some providers do not support pending tx subscriptions.
    """

    def __init__(self, *, ws_url: str, sample_rate: float = 1.0, max_queue: int = 5000, reconnect_backoff_s: float = 2.0):
        self.ws_url = ws_url
        self.sample_rate = max(0.0, min(1.0, float(sample_rate)))
        self.q: asyncio.Queue[str] = asyncio.Queue(maxsize=int(max_queue))
        self.status = MempoolStatus(connected=False, ws_url=ws_url)
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
        backoff = float(self.reconnect_backoff_s)
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = float(self.reconnect_backoff_s)
            except asyncio.CancelledError:
                return
            except _SAFE_WS_LOOP_EXCEPTIONS as e:
                self.status.connected = False
                self.status.last_error = f"ws_error:{type(e).__name__}:{e}"
                await asyncio.sleep(backoff)
                backoff = min(20.0, backoff * 1.5)

    @property
    def reconnect_backoff_s(self) -> float:
        return getattr(self, "_reconnect_backoff_s", 2.0)

    @reconnect_backoff_s.setter
    def reconnect_backoff_s(self, v: float) -> None:
        self._reconnect_backoff_s = float(v)

    async def _connect_once(self) -> None:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(self.ws_url, heartbeat=20) as ws:
                self.status.connected = True
                self.status.last_error = ""

                # Subscribe
                sub = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_subscribe",
                    "params": ["newPendingTransactions"],
                }
                await ws.send_str(json.dumps(sub))

                # Await subscription confirmation
                msg = await ws.receive(timeout=10)
                if msg.type != aiohttp.WSMsgType.TEXT:
                    raise RuntimeError("subscribe_failed")
                self.status.last_msg_ts = time.time()

                while not self._stop.is_set():
                    m = await ws.receive(timeout=30)
                    if m.type == aiohttp.WSMsgType.TEXT:
                        self.status.last_msg_ts = time.time()
                        try:
                            payload = json.loads(m.data)
                            params = payload.get("params") or {}
                            result = params.get("result")
                            if isinstance(result, str) and result.startswith("0x"):
                                if self.sample_rate < 1.0:
                                    # Deterministic sampling: stable under same (ws_url, tx_hash).
                                    u = stable_uniform_0_1(f"mempool:sample:{self.ws_url}:{result}")
                                    if u > self.sample_rate:
                                        continue
                                # Best-effort enqueue (drop oldest if full)
                                if self.q.full():
                                    try:
                                        _ = self.q.get_nowait()
                                    except asyncio.QueueEmpty:
                                        pass
                                try:
                                    self.q.put_nowait(result)
                                except asyncio.QueueFull:
                                    pass
                        except _SAFE_PAYLOAD_EXCEPTIONS:
                            # ignore parse errors and malformed payloads
                            continue
                    elif m.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        raise RuntimeError("ws_closed")
                    else:
                        # ignore pings/binary
                        continue

    async def iter_hashes(self) -> AsyncIterator[str]:
        """Async iterator over pending tx hashes."""
        while not self._stop.is_set():
            try:
                h = await self.q.get()
                yield h
            except asyncio.CancelledError:
                return
