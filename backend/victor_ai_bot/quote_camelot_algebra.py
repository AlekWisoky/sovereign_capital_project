from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ethabi import enc_address, enc_uint, selector
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure
from .rpc import JsonRpcClient


@dataclass(frozen=True)
class CamelotAlgebraQuote:
    amount_out: int
    fee: int
    gas_estimate: int


_SIG = "quoteExactInputSingle((address,address,uint256,uint160))"


def _calldata(token_in: str, token_out: str, amount_in: int, limit_sqrt_price_x96: int = 0) -> str:
    return "0x" + (
        selector(_SIG)
        + enc_address(token_in)
        + enc_address(token_out)
        + enc_uint(int(amount_in))
        + enc_uint(int(limit_sqrt_price_x96))
    ).hex()


def _parse(result: object) -> Optional[CamelotAlgebraQuote]:
    if not isinstance(result, str):
        return None
    try:
        raw = bytes.fromhex(result[2:] if result.startswith("0x") else result)
    except (TypeError, ValueError):
        return None
    if len(raw) < 128:
        return None
    amount_out = int.from_bytes(raw[0:32], "big")
    gas_estimate = int.from_bytes(raw[96:128], "big")
    # Algebra returns the current dynamic fee in the second return slot.
    fee = int.from_bytes(raw[32:64], "big")
    if amount_out <= 0 or fee < 0:
        return None
    return CamelotAlgebraQuote(amount_out=amount_out, fee=fee, gas_estimate=gas_estimate)


async def quote_camelot_algebra(
    rpc: JsonRpcClient,
    quoter_v2: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    *,
    block: str = "latest",
    diagnostics: dict | None = None,
) -> Optional[CamelotAlgebraQuote]:
    try:
        data = _calldata(token_in, token_out, int(amount_in))
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_camelot_algebra_request")
        return None
    result = await rpc.eth_call(quoter_v2, data, block=block)
    if not result.ok:
        record_quote_failure(diagnostics, classify_quote_error(result.error))
        return None
    quote = _parse(result.result)
    if quote is None:
        record_quote_parse_failure(diagnostics, "invalid_camelot_algebra_quote")
    return quote


async def quote_camelot_algebra_many(
    rpc: JsonRpcClient,
    quoter_v2: str,
    reqs: list[tuple[str, str, int]],
    *,
    block: str = "latest",
    diagnostics: dict | None = None,
) -> list[Optional[CamelotAlgebraQuote]]:
    if not reqs:
        return []
    calls = [_calldata(a, b, int(amount)) for a, b, amount in reqs]
    results = await rpc.eth_call_batch(calls, block=block)
    out: list[Optional[CamelotAlgebraQuote]] = []
    for result in results:
        if not result.ok:
            record_quote_failure(diagnostics, classify_quote_error(result.error))
            out.append(None)
            continue
        quote = _parse(result.result)
        if quote is None:
            record_quote_parse_failure(diagnostics, "invalid_camelot_algebra_quote")
        out.append(quote)
    return out
