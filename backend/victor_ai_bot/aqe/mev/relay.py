from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...rpc import JsonRpcClient, RpcResult
from ...execution_capture.endpoint_quality import EndpointQualityStore


@dataclass
class BundleResult:
    ok: bool
    result: Any = None
    error: Any = None
    latency_ms: float | None = None


class RelayClient:
    """Best-effort relay interface with optional endpoint quality telemetry.

    Works with:
    - MEV-protected RPCs that implement `eth_sendPrivateTransaction`
    - relays that implement Flashbots-like `eth_sendBundle` / `eth_callBundle`

    Telemetry is observational only; safe defaults keep the relay unused.
    """

    def __init__(self, rpc: JsonRpcClient, *, quality_store: EndpointQualityStore | None = None):
        self.rpc = rpc
        self.quality_store = quality_store

    def _observe(self, result: RpcResult) -> None:
        if self.quality_store is None:
            return
        latency_ms = float(result.latency_ms or 0.0)
        error_text = str(result.error or "").lower()
        self.quality_store.observe(
            lane="PRIVATE",
            endpoint=str(self.rpc.url),
            latency_ms=latency_ms,
            ok=bool(result.ok),
            timeout="timeout" in error_text,
            error=not bool(result.ok) and "timeout" not in error_text,
            relay=True,
        )

    async def send_private_transaction(self, raw_tx_hex: str, *, max_block: Optional[int] = None) -> RpcResult:
        result = await self.rpc.send_private_tx(raw_tx_hex, max_block_number=max_block)
        self._observe(result)
        return result

    async def call_bundle(self, bundle: Dict[str, Any]) -> BundleResult:
        r = await self.rpc.call("eth_callBundle", [bundle])
        self._observe(r)
        if not r.ok:
            return BundleResult(False, error=r.error, latency_ms=r.latency_ms)
        return BundleResult(True, result=r.result, latency_ms=r.latency_ms)

    async def send_bundle(self, bundle: Dict[str, Any]) -> BundleResult:
        r = await self.rpc.call("eth_sendBundle", [bundle])
        self._observe(r)
        if not r.ok:
            return BundleResult(False, error=r.error, latency_ms=r.latency_ms)
        return BundleResult(True, result=r.result, latency_ms=r.latency_ms)
