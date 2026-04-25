from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ...rpc import JsonRpcClient, RpcResult


@dataclass
class BundleResult:
    ok: bool
    result: Any = None
    error: Any = None


class RelayClient:
    """Best-effort relay interface.

    Works with:
    - MEV-protected RPCs that implement `eth_sendPrivateTransaction`
    - relays that implement Flashbots-like `eth_sendBundle` / `eth_callBundle`

    This is provided as optional infrastructure; safe defaults keep it unused.
    """

    def __init__(self, rpc: JsonRpcClient):
        self.rpc = rpc

    async def send_private_transaction(self, raw_tx_hex: str, *, max_block: Optional[int] = None) -> RpcResult:
        return await self.rpc.send_private_tx(raw_tx_hex, max_block_number=max_block)

    async def call_bundle(self, bundle: Dict[str, Any]) -> BundleResult:
        r = await self.rpc.call("eth_callBundle", [bundle])
        if not r.ok:
            return BundleResult(False, error=r.error)
        return BundleResult(True, result=r.result)

    async def send_bundle(self, bundle: Dict[str, Any]) -> BundleResult:
        r = await self.rpc.call("eth_sendBundle", [bundle])
        if not r.ok:
            return BundleResult(False, error=r.error)
        return BundleResult(True, result=r.result)
