from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .rpc import JsonRpcClient
from .ethabi import (
    selector,
    enc_uint,
    enc_address,
    enc_bool,
    enc_bytes32,
    enc_bytes_dyn,
    decode_int256_array,
)

_SIG = "queryBatchSwap(uint8,(bytes32,uint256,uint256,uint256,bytes)[],address[],(address,bool,address,bool))"


@dataclass
class BalancerQuote:
    amount_out: int


async def quote_balancer_given_in(
    rpc: JsonRpcClient,
    vault: str,
    pool_id_hex32: str,
    token_in: str,
    token_out: str,
    amount_in: int,
) -> Optional[BalancerQuote]:
    kind = 0  # GIVEN_IN
    pool_id = bytes.fromhex(pool_id_hex32[2:] if pool_id_hex32.startswith("0x") else pool_id_hex32)
    pool_id = pool_id.ljust(32, b"\x00")[:32]

    step_head = b"".join(
        [
            enc_bytes32(pool_id),
            enc_uint(0),
            enc_uint(1),
            enc_uint(amount_in),
            enc_uint(32 * 5),
        ]
    )
    user_data = enc_bytes_dyn(b"")
    step = step_head + user_data
    swaps = enc_uint(1) + step

    assets = enc_uint(2) + enc_address(token_in) + enc_address(token_out)
    funds = (
        enc_address("0x0000000000000000000000000000000000000000")
        + enc_bool(False)
        + enc_address("0x0000000000000000000000000000000000000000")
        + enc_bool(False)
    )

    head = b"".join(
        [
            enc_uint(kind),
            enc_uint(32 * 4),
            enc_uint(32 * 4 + len(swaps)),
            enc_uint(32 * 4 + len(swaps) + len(assets)),
        ]
    )
    data = selector(_SIG) + head + swaps + assets + funds

    r = await rpc.eth_call(vault, "0x" + data.hex())
    if not r.ok or not isinstance(r.result, str):
        return None
    raw = bytes.fromhex(r.result[2:]) if r.result.startswith("0x") else bytes.fromhex(r.result)
    deltas = decode_int256_array(raw)
    if len(deltas) < 2:
        return None
    amt_out = -deltas[1]
    if amt_out <= 0:
        return None
    return BalancerQuote(amount_out=amt_out)


def build_balancer_query_batchswap_calldata(
    pool_id_hex32: str, token_in: str, token_out: str, amount_in: int
) -> str:
    kind = 0  # GIVEN_IN
    pool_id = bytes.fromhex(pool_id_hex32[2:] if pool_id_hex32.startswith("0x") else pool_id_hex32)
    pool_id = pool_id.ljust(32, b"\x00")[:32]

    step_head = b"".join(
        [
            enc_bytes32(pool_id),
            enc_uint(0),
            enc_uint(1),
            enc_uint(int(amount_in)),
            enc_uint(32 * 5),
        ]
    )
    user_data = enc_bytes_dyn(b"")
    step = step_head + user_data
    swaps = enc_uint(1) + step

    assets = enc_uint(2) + enc_address(token_in) + enc_address(token_out)
    funds = (
        enc_address("0x0000000000000000000000000000000000000000")
        + enc_bool(False)
        + enc_address("0x0000000000000000000000000000000000000000")
        + enc_bool(False)
    )

    head = b"".join(
        [
            enc_uint(kind),
            enc_uint(32 * 4),
            enc_uint(32 * 4 + len(swaps)),
            enc_uint(32 * 4 + len(swaps) + len(assets)),
        ]
    )
    data = selector(_SIG) + head + swaps + assets + funds
    return "0x" + data.hex()


def parse_balancer_query_result(hex_result: str) -> Optional[int]:
    if not isinstance(hex_result, str):
        return None
    raw = (
        bytes.fromhex(hex_result[2:]) if hex_result.startswith("0x") else bytes.fromhex(hex_result)
    )
    deltas = decode_int256_array(raw)
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
) -> list[Optional[BalancerQuote]]:
    """Batch Balancer queryBatchSwap GIVEN_IN quotes.

    Each req: (pool_id_hex32, token_in, token_out, amount_in)
    """
    if not reqs:
        return []
    calls = []
    for pool_id, token_in, token_out, amount_in in reqs:
        calls.append(
            {
                "to": vault,
                "data": build_balancer_query_batchswap_calldata(
                    pool_id, token_in, token_out, int(amount_in)
                ),
            }
        )
    results = await rpc.eth_call_batch(calls)
    out: list[Optional[BalancerQuote]] = []
    for rr in results:
        if rr.ok and isinstance(rr.result, str):
            amt = parse_balancer_query_result(rr.result)
            out.append(BalancerQuote(amount_out=amt) if amt is not None else None)
        else:
            out.append(None)
    return out
