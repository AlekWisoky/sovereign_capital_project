from __future__ import annotations
import asyncio
import os
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
        self,
        url: str,
        *,
        timeout_s: float = 10.0,
        max_concurrency: int = 20,
        max_batch: int = 50,
        max_batch_concurrency: int | None = None,
    ):
        self.url = url
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self.max_batch = max_batch
        configured_batch_concurrency = (
            max_batch_concurrency
            if max_batch_concurrency is not None
            else int(os.environ.get("VICTOR_RPC_BATCH_CONCURRENCY", "2") or 2)
        )
        self.max_batch_concurrency = max(
            1, min(int(configured_batch_concurrency), int(max_concurrency))
        )
        self._batch_sem = asyncio.Semaphore(self.max_batch_concurrency)
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
        """Execute JSON-RPC calls in bounded-concurrent HTTP batches.

        Independent chunks may overlap, but concurrency is capped separately
        from the per-call semaphore. Input ordering is preserved.
        """
        if not calls:
            return []

        chunk_size = max(1, int(self.max_batch))
        chunks = [
            calls[i : i + chunk_size]
            for i in range(0, len(calls), chunk_size)
        ]

        async def _send_chunk(chunk: List[tuple[str, list]]) -> List[RpcResult]:
            async with self._batch_sem:
                async with self._sem:
                    t0 = time.perf_counter()
                    reqs = []
                    ids: List[int] = []
                    for method, params in chunk:
                        rid = self._next_id()
                        ids.append(rid)
                        reqs.append({
                            "jsonrpc": "2.0",
                            "id": rid,
                            "method": method,
                            "params": params or [],
                        })
                    try:
                        assert self._session is not None, "Use as async context manager"
                        async with self._session.post(self.url, json=reqs) as r:
                            j = await r.json()
                        dt = (time.perf_counter() - t0) * 1000.0

                        if not isinstance(j, list):
                            self._batch_supported = False
                            return [
                                await self.call(method, params or [])
                                for method, params in chunk
                            ]

                        if self._batch_supported is None:
                            self._batch_supported = True

                        by_id: Dict[int, Any] = {}
                        for resp in j:
                            try:
                                if isinstance(resp, dict) and "id" in resp:
                                    by_id[int(resp["id"])] = resp
                            except _SAFE_RPC_BATCH_ID_EXCEPTIONS:
                                continue
                        results: List[RpcResult] = []
                        for rid in ids:
                            resp = by_id.get(rid)
                            if not isinstance(resp, dict):
                                results.append(RpcResult(
                                    False, error="missing_batch_response", latency_ms=dt
                                ))
                            elif "error" in resp:
                                results.append(RpcResult(
                                    False, error=resp["error"], latency_ms=dt
                                ))
                            else:
                                results.append(RpcResult(
                                    True, result=resp.get("result"), latency_ms=dt
                                ))
                        return results
                    except _SAFE_RPC_CALL_EXCEPTIONS as exc:
                        dt = (time.perf_counter() - t0) * 1000.0
                        return [
                            RpcResult(False, error=str(exc), latency_ms=dt)
                            for _ in chunk
                        ]

        if self._batch_supported is False:
            out: List[RpcResult] = []
            for chunk in chunks:
                for method, params in chunk:
                    out.append(await self.call(method, params or []))
            return out

        if self._batch_supported is None:
            first = await _send_chunk(chunks[0])
            if self._batch_supported is False:
                out = list(first)
                for chunk in chunks[1:]:
                    for method, params in chunk:
                        out.append(await self.call(method, params or []))
                return out
            remaining = chunks[1:]
            if not remaining:
                return first
            rest = await asyncio.gather(*(_send_chunk(chunk) for chunk in remaining))
            return first + [item for chunk_results in rest for item in chunk_results]

        results = await asyncio.gather(*(_send_chunk(chunk) for chunk in chunks))
        return [item for chunk_results in results for item in chunk_results]

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

    async def eth_get_logs(
        self,
        *,
        address: str,
        from_block: int,
        to_block: int,
        topics: List[str] | None = None,
    ) -> List[dict]:
        """Read bounded event logs without introducing a write-capable path."""
        params: Dict[str, Any] = {
            "address": address,
            "fromBlock": hex(max(0, int(from_block))),
            "toBlock": hex(max(0, int(to_block))),
        }
        if topics:
            params["topics"] = list(topics)
        r = await self.call("eth_getLogs", [params])
        return list(r.result or []) if r.ok and isinstance(r.result, list) else []

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
