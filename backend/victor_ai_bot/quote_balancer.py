from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any, Iterator, Optional
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
# Balancer V2 deliberately reverts with QueryError(int256[]) after simulating a
# queryBatchSwap. This is not an ordinary failed quote: the error data contains
# the raw array length and int256 deltas after this selector.
_QUERY_ERROR_SELECTOR = bytes.fromhex("fa61cc12")
_MAX_QUERY_ERROR_BYTES = 4096


@dataclass
class BalancerQuote:
    amount_out: int


def _is_hex_payload(value: str) -> bool:
    return len(value) >= 10 and all(ch in "0123456789abcdefABCDEF" for ch in value[2:])


def _iter_text_hex_payloads(value: str) -> Iterator[str]:
    """Extract bounded hex candidates from a provider message or raw string."""
    text = value[:8192]
    stripped = text.strip().strip("\\'\" ,;")
    if stripped.startswith("0x"):
        candidate = stripped.split()[0].rstrip(",;")
        if _is_hex_payload(candidate):
            yield candidate
    yielded = 0
    for match in re.finditer(r"0x[0-9a-fA-F]{8,}", text):
        candidate = match.group(0)
        if candidate == stripped:
            continue
        yield candidate
        yielded += 1
        if yielded >= 8:
            break


def _iter_error_children(value: Any) -> Iterator[Any]:
    """Yield likely revert-data children first, bounded against noisy RPC errors."""
    if isinstance(value, dict):
        priority = ("data", "return", "result", "originalError", "error", "cause", "message")
        visited = set(priority).intersection(value)
        for key in priority:
            if key in value:
                yield value[key]
        for key, item in list(value.items())[:12]:
            if str(key) not in visited:
                yield item
    elif isinstance(value, (list, tuple)):
        yield from list(value)[:8]


def _iter_error_hex_payloads(value: Any, *, depth: int = 0) -> Iterator[str]:
    """Yield bounded hex payload candidates from common JSON-RPC error shapes."""
    if depth > 5:
        return
    if isinstance(value, str):
        yield from _iter_text_hex_payloads(value)
        return
    for child in _iter_error_children(value):
        yield from _iter_error_hex_payloads(child, depth=depth + 1)


def _decode_query_error_body(body: bytes) -> list[int] | None:
    if len(body) < 32 or len(body) > _MAX_QUERY_ERROR_BYTES or (len(body) - 32) % 32:
        return None
    count = int.from_bytes(body[:32], "big")
    if count < 2 or count > 64 or len(body) != 32 + count * 32:
        return None
    deltas: list[int] = []
    for start in range(32, len(body), 32):
        value = int.from_bytes(body[start:start + 32], "big")
        deltas.append(value - 2**256 if value >= 2**255 else value)
    return deltas


def _decode_query_error_candidate(candidate: str) -> tuple[list[int] | None, bool]:
    payload = candidate[2:] if candidate.startswith("0x") else candidate
    if len(payload) < 8 or len(payload) % 2:
        return None, False
    try:
        raw = bytes.fromhex(payload)
    except ValueError:
        return None, False
    if raw[:4] != _QUERY_ERROR_SELECTOR:
        return None, False
    return _decode_query_error_body(raw[4:]), True


def _decode_query_batch_swap_error(error: Any) -> tuple[list[int] | None, bool]:
    """Decode the documented QueryError(int256[]) envelope; fail closed otherwise.

    Balancer's payload is selector + raw array length + signed deltas, not the
    ordinary ABI return envelope that starts with an offset word.
    """
    saw_query_error = False
    for candidate in _iter_error_hex_payloads(error):
        deltas, recognized = _decode_query_error_candidate(candidate)
        saw_query_error = saw_query_error or recognized
        if deltas is not None:
            return deltas, True
    return None, saw_query_error


def _quote_from_deltas(
    deltas: list[int],
    diagnostics: dict | None = None,
) -> Optional["BalancerQuote"]:
    if len(deltas) != 2:
        record_quote_parse_failure(diagnostics, "unexpected_swap_delta_count")
        return None
    amount_out = -int(deltas[1])
    if amount_out <= 0:
        record_quote_parse_failure(diagnostics, "non_positive_quote_output")
        return None
    return BalancerQuote(amount_out=amount_out)


def _record_query_revert_decoded(diagnostics: dict | None) -> None:
    if diagnostics is not None:
        diagnostics["query_revert_decoded"] = int(
            diagnostics.get("query_revert_decoded", 0) or 0
        ) + 1


def _decode_balancer_rpc_result(rpc_result: Any, diagnostics: dict | None = None) -> Optional[BalancerQuote]:
    """Normalize ordinary returndata and Balancer's documented query-revert result."""
    if not getattr(rpc_result, "ok", False):
        deltas, recognized = _decode_query_batch_swap_error(getattr(rpc_result, "error", None))
        if deltas is None:
            reason = "invalid_query_batch_swap_revert_data" if recognized else classify_quote_error(
                getattr(rpc_result, "error", None)
            )
            if recognized:
                record_quote_parse_failure(diagnostics, reason)
            else:
                record_quote_failure(diagnostics, reason)
            return None
        _record_query_revert_decoded(diagnostics)
        return _quote_from_deltas(deltas, diagnostics)

    value = getattr(rpc_result, "result", None)
    if not isinstance(value, str):
        record_quote_parse_failure(diagnostics, "invalid_rpc_result")
        return None
    try:
        return _quote_from_deltas(_decode_balancer_swap_deltas(value), diagnostics)
    except (TypeError, ValueError):
        record_quote_parse_failure(diagnostics, "invalid_quote_result")
        return None


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
    try:
        data = build_balancer_query_batchswap_calldata(
            pool_id_hex32,
            token_in,
            token_out,
            int(amount_in),
        )
    except (TypeError, ValueError, OverflowError):
        record_quote_parse_failure(diagnostics, "invalid_balancer_request")
        return None
    r = await rpc.eth_call(vault, data)
    return _decode_balancer_rpc_result(r, diagnostics)


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
        out[request_index] = _decode_balancer_rpc_result(results[position], diagnostics)

    if len(results) > len(valid_indices):
        record_quote_parse_failure(diagnostics, "unexpected_rpc_batch_result")
    return out
