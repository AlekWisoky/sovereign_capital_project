from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Any, List, Optional, Dict
import aiohttp


_SAFE_RPC_CALL_EXCEPTIONS = (AssertionError, aiohttp.ClientError, asyncio.TimeoutError, OSError)
_SAFE_RPC_BATCH_ID_EXCEPTIONS = (TypeError, ValueError)


@dataclass
class RpcResult:
    ok: bool
    result: Any = None
    error: Any = None
    latency_ms: float | None = None


class JsonRpcClient:
    def __init__(
        self, url: str, *, timeout_s: float = 10.0, max_concurrency: int = 20, max_batch: int = 50
    ):
        self.url = url
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self.max_batch = max_batch
        self._session: aiohttp.ClientSession | None = None
        self._id = 0
        # Provider capability cache: some endpoints do not support JSON-RPC batching.
        # None=unknown, True=supported, False=not supported (fallback to individual calls).
        self._batch_supported: bool | None = None

    async def __aenter__(self):
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout_s))
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._session:
            await self._session.close()
            self._session = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: list | None = None) -> RpcResult:
        params = params or []
        async with self._sem:
            t0 = time.perf_counter()
            payload = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}
            try:
                assert self._session is not None, "Use as async context manager"
                async with self._session.post(self.url, json=payload) as r:
                    j = await r.json()
                dt = (time.perf_counter() - t0) * 1000.0
                if "error" in j:
                    return RpcResult(False, error=j["error"], latency_ms=dt)
                return RpcResult(True, result=j.get("result"), latency_ms=dt)
            except _SAFE_RPC_CALL_EXCEPTIONS as e:
                dt = (time.perf_counter() - t0) * 1000.0
                return RpcResult(False, error=str(e), latency_ms=dt)

    async def batch(self, calls: List[tuple[str, list]]) -> List[RpcResult]:
        """Execute JSON-RPC calls using a single batched HTTP request when supported.

        Many RPC providers support JSON-RPC batching (sending a list of request objects).
        This can drastically reduce latency for quote-heavy workloads (e.g., arbitrage scanning).

        Behavior:
        - Preserves input ordering.
        - Splits into chunks of size `self.max_batch`.
        - If the provider does not support batching, transparently falls back to per-call requests
          and caches that capability for this client instance.
        """
        if not calls:
            return []

        # Fast path: provider known to not support batching.
        if self._batch_supported is False:
            out: List[RpcResult] = []
            for method, params in calls:
                out.append(await self.call(method, params or []))
            return out

        out: List[RpcResult] = []
        for i in range(0, len(calls), max(1, int(self.max_batch))):
            chunk = calls[i : i + max(1, int(self.max_batch))]
            async with self._sem:
                t0 = time.perf_counter()
                reqs = []
                ids: List[int] = []
                for method, params in chunk:
                    rid = self._next_id()
                    ids.append(rid)
                    reqs.append(
                        {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or []}
                    )
                try:
                    assert self._session is not None, "Use as async context manager"
                    async with self._session.post(self.url, json=reqs) as r:
                        j = await r.json()
                    dt = (time.perf_counter() - t0) * 1000.0

                    # Some providers do not support batching and will return a dict/error.
                    if not isinstance(j, list):
                        # Cache capability and fallback for this chunk.
                        self._batch_supported = False
                        for method, params in chunk:
                            out.append(await self.call(method, params or []))
                        continue

                    # Cache as supported once we see a list response.
                    if self._batch_supported is None:
                        self._batch_supported = True

                    by_id: Dict[int, Any] = {}
                    for resp in j:
                        try:
                            if isinstance(resp, dict) and "id" in resp:
                                by_id[int(resp["id"])] = resp
                        except _SAFE_RPC_BATCH_ID_EXCEPTIONS:
                            continue
                    for rid in ids:
                        resp = by_id.get(rid)
                        if not isinstance(resp, dict):
                            out.append(
                                RpcResult(False, error="missing_batch_response", latency_ms=dt)
                            )
                        elif "error" in resp:
                            out.append(RpcResult(False, error=resp["error"], latency_ms=dt))
                        else:
                            out.append(RpcResult(True, result=resp.get("result"), latency_ms=dt))
                except _SAFE_RPC_CALL_EXCEPTIONS as e:
                    dt = (time.perf_counter() - t0) * 1000.0
                    for _ in chunk:
                        out.append(RpcResult(False, error=str(e), latency_ms=dt))
        return out

    async def eth_call_batch(
        self,
        calls: List[Dict[str, Any]],
        *,
        block: str = "latest",
    ) -> List[RpcResult]:
        """Batch multiple `eth_call`s.

        Each entry in `calls` must be an object like:
          { "to": <address>, "data": <0x...>, "from": <optional> }

        Returns a list of RpcResult aligned to the input ordering.
        """
        reqs: List[tuple[str, list]] = []
        for obj in calls:
            reqs.append(("eth_call", [obj, block]))
        return await self.batch(reqs)

    async def eth_call(
        self, to: str, data_hex: str, *, block: str = "latest", from_addr: str | None = None
    ) -> RpcResult:
        obj: Dict[str, Any] = {"to": to, "data": data_hex}
        if from_addr:
            obj["from"] = from_addr
        return await self.call("eth_call", [obj, block])

    async def block_number(self) -> Optional[int]:
        r = await self.call("eth_blockNumber")
        if not r.ok or not isinstance(r.result, str):
            return None
        return int(r.result, 16)

    async def chain_id(self) -> Optional[int]:
        r = await self.call("eth_chainId")
        if not r.ok or not isinstance(r.result, str):
            return None
        return int(r.result, 16)

    async def gas_price(self) -> Optional[int]:
        r = await self.call("eth_gasPrice")
        if not r.ok or not isinstance(r.result, str):
            return None
        return int(r.result, 16)

    async def fee_history_tip(self) -> Optional[int]:
        # Try EIP-1559 feeHistory reward median tip (priority fee)
        r = await self.call("eth_feeHistory", ["0x5", "latest", [50]])
        if not r.ok or not isinstance(r.result, dict):
            return None
        rewards = r.result.get("reward")
        if not rewards or not isinstance(rewards, list):
            return None
        # take last block's median
        last = rewards[-1]
        if not last or not isinstance(last, list):
            return None
        tip_hex = last[0]
        return int(tip_hex, 16) if isinstance(tip_hex, str) else None

    async def estimate_gas(self, tx: dict) -> Optional[int]:
        r = await self.call("eth_estimateGas", [tx])
        if not r.ok or not isinstance(r.result, str):
            return None
        return int(r.result, 16)

    async def get_nonce(self, addr: str) -> Optional[int]:
        r = await self.call("eth_getTransactionCount", [addr, "pending"])
        if not r.ok or not isinstance(r.result, str):
            return None
        return int(r.result, 16)

    async def send_raw_tx(self, raw_tx_hex: str) -> RpcResult:
        return await self.call("eth_sendRawTransaction", [raw_tx_hex])

    async def send_private_tx(
        self, raw_tx_hex: str, *, max_block_number: int | None = None
    ) -> RpcResult:
        # Best-effort "eth_sendPrivateTransaction" (common on MEV-protected RPCs).
        # Different relays differ; we keep params minimal.
        params = {"tx": raw_tx_hex}
        if max_block_number is not None:
            params["maxBlockNumber"] = hex(max_block_number)
        return await self.call("eth_sendPrivateTransaction", [params])

    async def get_tx_by_hash(self, tx_hash: str) -> Optional[dict]:
        r = await self.call("eth_getTransactionByHash", [tx_hash])
        if not r.ok or not isinstance(r.result, dict):
            return None
        return r.result

    async def wait_for_receipt(
        self, tx_hash: str, *, timeout_s: float = 120.0, poll_interval_s: float = 2.0
    ) -> Optional[dict]:
        start = time.time()
        while time.time() - start < timeout_s:
            r = await self.call("eth_getTransactionReceipt", [tx_hash])
            if r.ok and r.result:
                return r.result
            await asyncio.sleep(poll_interval_s)
        return None
