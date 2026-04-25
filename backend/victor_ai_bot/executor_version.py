from __future__ import annotations

from typing import Optional, Tuple

from .ethabi import selector
from .rpc import JsonRpcClient, RpcResult


_SAFE_EXECUTOR_VERSION_DECODE_EXCEPTIONS = (TypeError, ValueError)


async def fetch_executor_version(
    rpc: JsonRpcClient,
    *,
    executor_address: str,
    block: str = "latest",
) -> Optional[Tuple[int, int]]:
    """Fetch (abiVersion, implVersion) from VictorArbExecutor.executorVersion().

    Returns None if the call fails (e.g., older executor without the method).
    """

    addr = (executor_address or "").strip()
    if not addr:
        return None

    data = "0x" + selector("executorVersion()").hex()
    res = await rpc.eth_call(addr, data, block=block)

    if isinstance(res, RpcResult):
        if not bool(res.ok) or not isinstance(res.result, str):
            return None
        raw = res.result
    elif isinstance(res, str):
        raw = res
    else:
        return None

    if not raw.startswith("0x"):
        return None
    payload = raw[2:]
    if len(payload) < 64 * 2:
        return None

    try:
        b = bytes.fromhex(payload)
    except _SAFE_EXECUTOR_VERSION_DECODE_EXCEPTIONS:
        return None
    abi_v = int.from_bytes(b[0:32], "big")
    impl_v = int.from_bytes(b[32:64], "big")
    return abi_v, impl_v
