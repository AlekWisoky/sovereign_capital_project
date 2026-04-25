from __future__ import annotations

from typing import Optional, Tuple

from .ethabi import selector
from .rpc import JsonRpcClient, RpcResult


_SAFE_EXECUTOR_OWNER_DECODE_EXCEPTIONS = (TypeError, ValueError)
_ZERO_ADDRESS = "0x" + ("0" * 40)


async def fetch_executor_owner(
    rpc: JsonRpcClient,
    *,
    executor_address: str,
    block: str = "latest",
) -> Optional[str]:
    """Fetch VictorArbExecutor.owner().

    Returns None when the call fails or the response is malformed.
    """

    addr = (executor_address or "").strip()
    if not addr:
        return None

    data = "0x" + selector("owner()").hex()
    res = await rpc.eth_call(addr, data, block=block)

    if isinstance(res, RpcResult):
        if not bool(res.ok) or not isinstance(res.result, str):
            return None
        raw = res.result
    elif isinstance(res, str):
        raw = res
    elif bool(getattr(res, "ok", False)) and isinstance(getattr(res, "result", None), str):
        raw = str(getattr(res, "result"))
    else:
        return None

    if not raw.startswith("0x"):
        return None
    payload = raw[2:]
    if len(payload) < 64:
        return None

    try:
        word = bytes.fromhex(payload[:64])
    except _SAFE_EXECUTOR_OWNER_DECODE_EXCEPTIONS:
        return None

    owner = "0x" + word[-20:].hex()
    if owner == _ZERO_ADDRESS:
        return None
    return owner


async def validate_executor_owner_proof(
    rpc: JsonRpcClient,
    *,
    executor_address: str,
    signer_address: str,
    block: str = "latest",
) -> Tuple[str | None, str | None]:
    """Validate that the configured backend signer owns the executor contract.

    Returns (reason_code, owner_address). reason_code is None when the proof is valid.
    """

    owner = await fetch_executor_owner(rpc, executor_address=executor_address, block=block)
    if not owner:
        return "executor_owner_lookup_failed", None
    if str(owner).lower() != str(signer_address or "").strip().lower():
        return "executor_owner_mismatch", owner
    return None, owner
