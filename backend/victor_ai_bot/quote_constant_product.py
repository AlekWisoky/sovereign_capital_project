from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ethabi import enc_address, enc_uint, selector
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure
from .rpc import JsonRpcClient


@dataclass(frozen=True)
class ConstantProductQuote:
    amount_out: int


def _calldata(token_in: str, token_out: str, amount_in: int) -> str:
    data = (
        selector("getAmountsOut(uint256,address[])")
        + enc_uint(int(amount_in))
        + enc_uint(64)
        + enc_uint(2)
        + enc_address(token_in)
        + enc_address(token_out)
    )
    return "0x" + data.hex()


def _parse(result: object) -> Optional[ConstantProductQuote]:
    if not isinstance(result, str):
        return None
    try:
        raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    except (TypeError, ValueError):
        return None
    if len(raw) < 128:
        return None
    offset = int.from_bytes(raw[:32], "big")
    if offset + 96 > len(raw):
        return None
    length = int.from_bytes(raw[offset:offset + 32], "big")
    if length < 2 or offset + 96 > len(raw):
        return None
    amount_out = int.from_bytes(raw[offset + 64:offset + 96], "big")
    return ConstantProductQuote(amount_out=amount_out) if amount_out > 0 else None


async def quote_constant_product(
    rpc: JsonRpcClient,
    router: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    *,
    diagnostics: dict | None = None,
) -> Optional[ConstantProductQuote]:
    try:
        data = _calldata(token_in, token_out, amount_in)
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_constant_product_request")
        return None
    result = await rpc.eth_call(router, data)
    if not result.ok:
        record_quote_failure(diagnostics, classify_quote_error(result.error))
        return None
    quote = _parse(result.result)
    if quote is None:
        record_quote_parse_failure(diagnostics, "invalid_quote_result")
        return None
    return quote


async def quote_constant_product_many(
    rpc: JsonRpcClient,
    router: str,
    reqs: list[tuple[str, str, int]],
    *,
    diagnostics: dict | None = None,
) -> list[Optional[ConstantProductQuote]]:
    if not reqs:
        return []
    calls = [{"to": router, "data": _calldata(a, b, n)} for a, b, n in reqs]
    results = await rpc.eth_call_batch(calls)
    out: list[Optional[ConstantProductQuote]] = []
    for result in results:
        if not result.ok:
            record_quote_failure(diagnostics, classify_quote_error(result.error))
            out.append(None)
            continue
        quote = _parse(result.result)
        if quote is None:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
        out.append(quote)
    return out
