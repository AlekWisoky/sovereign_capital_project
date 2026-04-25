from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .rpc import JsonRpcClient
from .ethabi import selector, enc_int, enc_uint


@dataclass
class CurveQuote:
    amount_out: int
    used_underlying: bool


async def _call(
    rpc: JsonRpcClient, pool: str, i: int, j: int, dx: int, underlying: bool
) -> Optional[int]:
    sig = (
        "get_dy_underlying(int128,int128,uint256)"
        if underlying
        else "get_dy(int128,int128,uint256)"
    )
    data = b"".join([selector(sig), enc_int(i), enc_int(j), enc_uint(dx)])
    r = await rpc.eth_call(pool, "0x" + data.hex())
    if not r.ok or not isinstance(r.result, str):
        return None
    raw = bytes.fromhex(r.result[2:]) if r.result.startswith("0x") else bytes.fromhex(r.result)
    if len(raw) < 32:
        return None
    return int.from_bytes(raw[0:32], "big")


async def quote_curve(
    rpc: JsonRpcClient, pool: str, i: int, j: int, amount_in: int, prefer_underlying: bool = False
) -> Optional[CurveQuote]:
    out = await _call(rpc, pool, i, j, amount_in, prefer_underlying)
    if out is not None:
        return CurveQuote(amount_out=out, used_underlying=prefer_underlying)
    out2 = await _call(rpc, pool, i, j, amount_in, not prefer_underlying)
    if out2 is None:
        return None
    return CurveQuote(amount_out=out2, used_underlying=not prefer_underlying)


def build_curve_quote_calldata(i: int, j: int, dx: int, underlying: bool) -> str:
    sig = (
        "get_dy_underlying(int128,int128,uint256)"
        if underlying
        else "get_dy(int128,int128,uint256)"
    )
    data = b"".join([selector(sig), enc_int(int(i)), enc_int(int(j)), enc_uint(int(dx))])
    return "0x" + data.hex()


def parse_curve_quote_result(hex_result: str) -> Optional[int]:
    if not isinstance(hex_result, str):
        return None
    raw = (
        bytes.fromhex(hex_result[2:]) if hex_result.startswith("0x") else bytes.fromhex(hex_result)
    )
    if len(raw) < 32:
        return None
    return int.from_bytes(raw[0:32], "big")


async def quote_curve_many(
    rpc: JsonRpcClient,
    reqs: list[tuple[str, int, int, int, bool]],
) -> list[Optional[CurveQuote]]:
    """Batch Curve get_dy/get_dy_underlying quotes.

    Each req: (pool, i, j, amount_in, prefer_underlying)

    Implementation:
    - First batch quotes with prefer_underlying.
    - For failures, fallback to the opposite underlying flag with a second batch.
    """
    if not reqs:
        return []
    # Stage 1: preferred
    calls = []
    for pool, i, j, dx, prefer_underlying in reqs:
        calls.append(
            {"to": pool, "data": build_curve_quote_calldata(i, j, dx, bool(prefer_underlying))}
        )
    r1 = await rpc.eth_call_batch(calls)
    out: list[Optional[CurveQuote]] = [None] * len(reqs)
    need_fallback: list[int] = []
    for idx, rr in enumerate(r1):
        if rr.ok and isinstance(rr.result, str):
            amt = parse_curve_quote_result(rr.result)
            if amt is not None:
                out[idx] = CurveQuote(amount_out=amt, used_underlying=bool(reqs[idx][4]))
                continue
        need_fallback.append(idx)

    if not need_fallback:
        return out

    # Stage 2: fallback to opposite
    calls2 = []
    for idx in need_fallback:
        pool, i, j, dx, prefer = reqs[idx]
        calls2.append(
            {"to": pool, "data": build_curve_quote_calldata(i, j, dx, (not bool(prefer)))}
        )
    r2 = await rpc.eth_call_batch(calls2)
    for local_i, idx in enumerate(need_fallback):
        rr = r2[local_i]
        if rr.ok and isinstance(rr.result, str):
            amt = parse_curve_quote_result(rr.result)
            if amt is not None:
                out[idx] = CurveQuote(amount_out=amt, used_underlying=(not bool(reqs[idx][4])))
    return out
