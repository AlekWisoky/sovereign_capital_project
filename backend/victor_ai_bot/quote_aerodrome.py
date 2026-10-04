from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from .ethabi import enc_address, enc_bool, enc_uint, selector
from .rpc import JsonRpcClient
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure


@dataclass
class AerodromeQuote:
    amount_out: int
    stable: bool
    factory: str


def _route_calldata(token_in: str, token_out: str, stable: bool, factory: str, amount_in: int) -> str:
    # IRouter.Route = (address from, address to, bool stable, address factory).
    # getAmountsOut(uint256,Route[]) has a static head (amount, offset=64)
    # followed by a one-element dynamic tuple array.
    route = b"".join([
        enc_address(token_in),
        enc_address(token_out),
        enc_bool(stable),
        enc_address(factory),
    ])
    data = (
        selector("getAmountsOut(uint256,(address,address,bool,address)[])")
        + enc_uint(int(amount_in))
        + enc_uint(64)
        + enc_uint(1)
        + route
    )
    return "0x" + data.hex()


def _parse_amount_out(result: object) -> Optional[int]:
    if not isinstance(result, str):
        return None
    try:
        raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    except (TypeError, ValueError):
        return None
    if len(raw) < 96:
        return None
    # uint256[] return: offset, length, amountIn, amountOut.
    offset = int.from_bytes(raw[:32], "big")
    if offset + 96 > len(raw):
        return None
    length = int.from_bytes(raw[offset:offset + 32], "big")
    if length < 2 or offset + 96 > len(raw):
        return None
    return int.from_bytes(raw[offset + 64:offset + 96], "big")


async def quote_aerodrome(
    rpc: JsonRpcClient,
    router: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    *,
    stable: bool,
    factory: str,
    diagnostics: dict | None = None,
) -> Optional[AerodromeQuote]:
    data = _route_calldata(token_in, token_out, stable, factory, amount_in)
    result = await rpc.eth_call(router, data)
    if not result.ok:
        record_quote_failure(diagnostics, classify_quote_error(result.error))
        return None
    out = _parse_amount_out(result.result)
    if out is None:
        record_quote_parse_failure(diagnostics, "invalid_quote_result")
        return None
    if out <= 0:
        record_quote_failure(diagnostics, "zero_output")
        return None
    return AerodromeQuote(amount_out=out, stable=bool(stable), factory=str(factory))


async def quote_aerodrome_many(
    rpc: JsonRpcClient,
    router: str,
    reqs: list[tuple[str, str, int, bool, str]],
    *,
    diagnostics: dict | None = None,
) -> list[Optional[AerodromeQuote]]:
    if not reqs:
        return []
    calls = [
        {"to": router, "data": _route_calldata(token_in, token_out, stable, factory, amount_in)}
        for token_in, token_out, amount_in, stable, factory in reqs
    ]
    results = await rpc.eth_call_batch(calls)
    out: list[Optional[AerodromeQuote]] = []
    for req, result in zip(reqs, results):
        if not result.ok:
            record_quote_failure(diagnostics, classify_quote_error(result.error))
            out.append(None)
            continue
        amount_out = _parse_amount_out(result.result)
        if amount_out is None:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
            out.append(None)
            continue
        if amount_out <= 0:
            record_quote_failure(diagnostics, "zero_output")
            out.append(None)
            continue
        out.append(AerodromeQuote(amount_out=amount_out, stable=bool(req[3]), factory=str(req[4])))
    return out
