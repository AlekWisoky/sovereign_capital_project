from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .ethabi import enc_address, enc_uint, selector
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure
from .rpc import JsonRpcClient


@dataclass(frozen=True)
class SlipstreamQuote:
    amount_out: int
    gas_estimate: int
    tick_spacing: int


_SIG = "quoteExactInputSingle((address,address,uint256,int24,uint160))"


def _enc_tick_spacing(value: int) -> bytes:
    value = int(value)
    if value < -(1 << 23) or value >= (1 << 23):
        raise ValueError("tick_spacing_out_of_int24_range")
    # ABI int24 occupies a full 32-byte two's-complement word.
    return enc_uint(value if value >= 0 else (1 << 256) + value)


def _calldata(token_in: str, token_out: str, tick_spacing: int, amount_in: int, sqrt_price_limit_x96: int = 0) -> str:
    data = b"".join(
        [
            selector(_SIG),
            enc_address(token_in),
            enc_address(token_out),
            enc_uint(int(amount_in)),
            _enc_tick_spacing(int(tick_spacing)),
            enc_uint(int(sqrt_price_limit_x96)),
        ]
    )
    return "0x" + data.hex()


def _parse(result: object, tick_spacing: int) -> Optional[SlipstreamQuote]:
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
    if amount_out <= 0:
        return None
    return SlipstreamQuote(amount_out=amount_out, gas_estimate=gas_estimate, tick_spacing=int(tick_spacing))


async def quote_slipstream(
    rpc: JsonRpcClient,
    quoter_v2: str,
    token_in: str,
    token_out: str,
    tick_spacing: int,
    amount_in: int,
    *,
    block: str = "latest",
    diagnostics: dict | None = None,
) -> Optional[SlipstreamQuote]:
    try:
        data = _calldata(token_in, token_out, int(tick_spacing), int(amount_in))
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_tick_spacing")
        return None
    result = await rpc.eth_call(quoter_v2, data, block=block)
    if not result.ok:
        record_quote_failure(diagnostics, classify_quote_error(result.error))
        return None
    quote = _parse(result.result, int(tick_spacing))
    if quote is None:
        record_quote_parse_failure(diagnostics, "invalid_quote_result")
    return quote


async def quote_slipstream_many(
    rpc: JsonRpcClient,
    quoter_v2: str,
    reqs: list[tuple[str, str, int, int]],
    *,
    block: str = "latest",
    diagnostics: dict | None = None,
) -> list[Optional[SlipstreamQuote]]:
    if not reqs:
        return []
    calls = []
    for token_in, token_out, tick_spacing, amount_in in reqs:
        try:
            calls.append({"to": quoter_v2, "data": _calldata(token_in, token_out, int(tick_spacing), int(amount_in))})
        except (TypeError, ValueError):
            calls.append(None)

    valid_calls = [call for call in calls if call is not None]
    results = await rpc.eth_call_batch(valid_calls, block=block) if valid_calls else []
    out: list[Optional[SlipstreamQuote]] = []
    result_index = 0
    for req, call in zip(reqs, calls):
        if call is None:
            record_quote_parse_failure(diagnostics, "invalid_tick_spacing")
            out.append(None)
            continue
        result = results[result_index]
        result_index += 1
        if not result.ok:
            record_quote_failure(diagnostics, classify_quote_error(result.error))
            out.append(None)
            continue
        quote = _parse(result.result, int(req[2]))
        if quote is None:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
        out.append(quote)
    return out
