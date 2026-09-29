from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .rpc import JsonRpcClient
from .ethabi import selector, enc_int, enc_uint
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure


@dataclass
class CurveQuote:
    amount_out: int
    used_underlying: bool


async def _call(
    rpc: JsonRpcClient, pool: str, i: int, j: int, dx: int, underlying: bool,
    diagnostics: dict | None = None,
) -> Optional[int]:
    sig = (
        "get_dy_underlying(int128,int128,uint256)"
        if underlying
        else "get_dy(int128,int128,uint256)"
    )
    data = b"".join([selector(sig), enc_int(i), enc_int(j), enc_uint(dx)])
    r = await rpc.eth_call(pool, "0x" + data.hex())
    if not r.ok:
        record_quote_failure(diagnostics, classify_quote_error(r.error))
        return None
    if not isinstance(r.result, str):
        record_quote_parse_failure(diagnostics, "invalid_rpc_result")
        return None
    try:
        raw = bytes.fromhex(r.result[2:]) if r.result.startswith("0x") else bytes.fromhex(r.result)
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_hex_result")
        return None
    if len(raw) < 32:
        record_quote_parse_failure(diagnostics, "short_quote_result")
        return None
    return int.from_bytes(raw[0:32], "big")


async def quote_curve(
    rpc: JsonRpcClient, pool: str, i: int, j: int, amount_in: int, prefer_underlying: bool = False,
    diagnostics: dict | None = None,
) -> Optional[CurveQuote]:
    out = await _call(rpc, pool, i, j, amount_in, prefer_underlying, diagnostics)
    if out is not None:
        return CurveQuote(amount_out=out, used_underlying=prefer_underlying)
    out2 = await _call(rpc, pool, i, j, amount_in, not prefer_underlying, diagnostics)
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
    *,
    diagnostics: dict | None = None,
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
            try:
                amt = parse_curve_quote_result(rr.result)
            except (TypeError, ValueError):
                amt = None
            if amt is not None:
                out[idx] = CurveQuote(amount_out=amt, used_underlying=bool(reqs[idx][4]))
                continue
        if not rr.ok:
            record_quote_failure(diagnostics, classify_quote_error(rr.error))
        elif not isinstance(rr.result, str):
            record_quote_parse_failure(diagnostics, "invalid_rpc_result")
        else:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
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
            try:
                amt = parse_curve_quote_result(rr.result)
            except (TypeError, ValueError):
                amt = None
            if amt is not None:
                out[idx] = CurveQuote(amount_out=amt, used_underlying=(not bool(reqs[idx][4])))
                continue
        if not rr.ok:
            record_quote_failure(diagnostics, classify_quote_error(rr.error))
        elif not isinstance(rr.result, str):
            record_quote_parse_failure(diagnostics, "invalid_rpc_result")
        else:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
    return out
