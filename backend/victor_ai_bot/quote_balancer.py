from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .rpc import JsonRpcClient
from .quote_diagnostics import classify_quote_error, record_quote_failure, record_quote_parse_failure
from .ethabi import (
    selector,
    enc_uint,
    enc_address,
    enc_bool,
    enc_bytes32,
    enc_bytes_dyn,
)

_SIG = "queryBatchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],address[],(address,bool,address,bool))"


@dataclass
class BalancerQuote:
    amount_out: int


def _decode_balancer_swap_deltas(hex_result: str) -> list[int]:
    """Decode a strict ABI int256[] return without accepting truncated words."""
    if not isinstance(hex_result, str):
        raise TypeError("Balancer result must be a hex string")
    payload = hex_result[2:] if hex_result.startswith("0x") else hex_result
    try:
        raw = bytes.fromhex(payload)
    except ValueError as exc:
        raise ValueError("Balancer result is not valid hex") from exc
    if len(raw) < 64 or len(raw) % 32:
        raise ValueError("Balancer result has an invalid ABI word length")

    offset = int.from_bytes(raw[:32], "big")
    if offset != 32:
        raise ValueError("Balancer int256[] return has a non-canonical offset")

    count = int.from_bytes(raw[32:64], "big")
    expected_length = 64 + count * 32
    if len(raw) != expected_length:
        raise ValueError("Balancer int256[] return length does not match its element count")

    deltas: list[int] = []
    for start in range(64, expected_length, 32):
        value = int.from_bytes(raw[start:start + 32], "big")
        if value >= 2**255:
            value -= 2**256
        deltas.append(value)
    return deltas


async def quote_balancer_given_in(
    rpc: JsonRpcClient,
    vault: str,
    pool_id_hex32: str,
    token_in: str,
    token_out: str,
    amount_in: int,
    diagnostics: dict | None = None,
) -> Optional[BalancerQuote]:
    data = build_balancer_query_batchswap_calldata(
        pool_id_hex32,
        token_in,
        token_out,
        int(amount_in),
    )
    r = await rpc.eth_call(vault, data)
    if not r.ok:
        record_quote_failure(diagnostics, classify_quote_error(r.error))
        return None
    if not isinstance(r.result, str):
        record_quote_parse_failure(diagnostics, "invalid_rpc_result")
        return None
    try:
        deltas = _decode_balancer_swap_deltas(r.result)
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_quote_result")
        return None
    if len(deltas) < 2:
        record_quote_parse_failure(diagnostics, "insufficient_swap_deltas")
        return None
    amt_out = -deltas[1]
    if amt_out <= 0:
        return None
    return BalancerQuote(amount_out=amt_out)


def build_balancer_query_batchswap_calldata(
    pool_id_hex32: str, token_in: str, token_out: str, amount_in: int
) -> str:
    """ABI-encode a one-step queryBatchSwap(GIVEN_IN) call.

    BatchSwapStep[] contains a tuple with dynamic bytes, so the array needs an
    element-offset word before the tuple body. FundManagement is a static tuple,
    so its four words belong inline in the top-level head, not in a dynamic tail.
    ABI offsets are relative to the start of the argument block (after selector).
    """
    kind = 0  # GIVEN_IN
    raw_pool_id = bytes.fromhex(
        pool_id_hex32[2:] if pool_id_hex32.startswith("0x") else pool_id_hex32
    )
    if len(raw_pool_id) != 32:
        raise ValueError("Balancer pool id must be exactly 32 bytes")
    if int(amount_in) <= 0:
        raise ValueError("Balancer quote amount must be positive")

    step_head = b"".join(
        [
            enc_bytes32(raw_pool_id),
            enc_uint(0),
            enc_uint(1),
            enc_uint(int(amount_in)),
            enc_uint(32 * 5),
        ]
    )
    user_data = enc_bytes_dyn(b"")
    step = step_head + user_data

    # A dynamic array of dynamic tuple elements encodes the length, an array
    # of offsets (relative to the element-head area after the length), then
    # the tuple bodies. The one tuple starts 32 bytes after that area.
    swaps = enc_uint(1) + enc_uint(32) + step
    assets = enc_uint(2) + enc_address(token_in) + enc_address(token_out)

    zero_address = "0x0000000000000000000000000000000000000000"
    funds = (
        enc_address(zero_address)
        + enc_bool(False)
        + enc_address(zero_address)
        + enc_bool(False)
    )

    # The static FundManagement tuple expands to four head words. The full
    # top-level head is 7 words: kind, swaps offset, assets offset, and funds.
    head_size = 32 * 7
    swaps_offset = head_size
    assets_offset = swaps_offset + len(swaps)
    head = (
        enc_uint(kind)
        + enc_uint(swaps_offset)
        + enc_uint(assets_offset)
        + funds
    )
    data = selector(_SIG) + head + swaps + assets
    return "0x" + data.hex()


def parse_balancer_query_result(hex_result: str) -> Optional[int]:
    deltas = _decode_balancer_swap_deltas(hex_result)
    if len(deltas) < 2:
        return None
    amt_out = -deltas[1]
    if amt_out <= 0:
        return None
    return int(amt_out)


async def quote_balancer_given_in_many(
    rpc: JsonRpcClient,
    vault: str,
    reqs: list[tuple[str, str, str, int]],
    diagnostics: dict | None = None,
) -> list[Optional[BalancerQuote]]:
    """Batch Balancer queryBatchSwap GIVEN_IN quotes.

    Each req: (pool_id_hex32, token_in, token_out, amount_in). A malformed
    request fails locally in its own slot and does not abort valid siblings.
    """
    if not reqs:
        return []
    out: list[Optional[BalancerQuote]] = [None] * len(reqs)
    calls = []
    valid_indices: list[int] = []
    for index, (pool_id, token_in, token_out, amount_in) in enumerate(reqs):
        try:
            data = build_balancer_query_batchswap_calldata(
                pool_id, token_in, token_out, int(amount_in)
            )
        except (TypeError, ValueError, OverflowError):
            record_quote_parse_failure(diagnostics, "invalid_balancer_request")
            continue
        calls.append({"to": vault, "data": data})
        valid_indices.append(index)

    if not calls:
        return out

    results = await rpc.eth_call_batch(calls)
    for position, request_index in enumerate(valid_indices):
        if position >= len(results):
            record_quote_parse_failure(diagnostics, "missing_rpc_batch_result")
            continue
        rr = results[position]
        if not rr.ok:
            record_quote_failure(diagnostics, classify_quote_error(rr.error))
            continue
        if not isinstance(rr.result, str):
            record_quote_parse_failure(diagnostics, "invalid_rpc_result")
            continue
        try:
            amt = parse_balancer_query_result(rr.result)
        except (TypeError, ValueError):
            amt = None
        if amt is None:
            record_quote_parse_failure(diagnostics, "invalid_quote_result")
            continue
        out[request_index] = BalancerQuote(amount_out=amt)

    if len(results) > len(valid_indices):
        record_quote_parse_failure(diagnostics, "unexpected_rpc_batch_result")
    return out
