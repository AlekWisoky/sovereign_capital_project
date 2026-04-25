from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from .rpc import JsonRpcClient
from .ethabi import selector, enc_address, enc_uint


@dataclass
class UniV3Quote:
    amount_out: int
    gas_estimate: int


_SIG = "quoteExactInputSingle((address,address,uint256,uint24,uint160))"


async def quote_exact_input_single(
    rpc: JsonRpcClient,
    quoter_v2: str,
    token_in: str,
    token_out: str,
    fee: int,
    amount_in: int,
    sqrt_price_limit_x96: int = 0,
    *,
    block: str = "latest",
) -> Optional[UniV3Quote]:
    data = b"".join(
        [
            selector(_SIG),
            enc_address(token_in),
            enc_address(token_out),
            enc_uint(amount_in),
            enc_uint(fee),
            enc_uint(sqrt_price_limit_x96),
        ]
    )
    r = await rpc.eth_call(quoter_v2, "0x" + data.hex(), block=block)
    if not r.ok or not isinstance(r.result, str):
        return None
    raw = bytes.fromhex(r.result[2:]) if r.result.startswith("0x") else bytes.fromhex(r.result)
    if len(raw) < 32 * 4:
        return None
    amount_out = int.from_bytes(raw[0:32], "big")
    gas_est = int.from_bytes(raw[96:128], "big")
    return UniV3Quote(amount_out=amount_out, gas_estimate=gas_est)


def build_quote_exact_input_single_calldata(
    token_in: str,
    token_out: str,
    fee: int,
    amount_in: int,
    sqrt_price_limit_x96: int = 0,
) -> str:
    data = b"".join(
        [
            selector(_SIG),
            enc_address(token_in),
            enc_address(token_out),
            enc_uint(amount_in),
            enc_uint(int(fee)),
            enc_uint(int(sqrt_price_limit_x96)),
        ]
    )
    return "0x" + data.hex()


def parse_quote_exact_input_single_result(hex_result: str) -> Optional[UniV3Quote]:
    if not isinstance(hex_result, str):
        return None
    raw = (
        bytes.fromhex(hex_result[2:]) if hex_result.startswith("0x") else bytes.fromhex(hex_result)
    )
    if len(raw) < 32 * 4:
        return None
    amount_out = int.from_bytes(raw[0:32], "big")
    gas_est = int.from_bytes(raw[96:128], "big")
    return UniV3Quote(amount_out=amount_out, gas_estimate=gas_est)


async def quote_exact_input_single_batch(
    rpc: JsonRpcClient,
    quoter_v2: str,
    reqs: list[tuple[str, str, int, int, int]],
    *,
    block: str = "latest",
) -> list[Optional[UniV3Quote]]:
    """Batch UniV3 QuoterV2 quotes.

    Each req is (token_in, token_out, fee, amount_in, sqrt_price_limit_x96).
    """
    calls = []
    for token_in, token_out, fee, amount_in, spl in reqs:
        calls.append(
            {
                "to": quoter_v2,
                "data": build_quote_exact_input_single_calldata(
                    token_in, token_out, int(fee), int(amount_in), int(spl)
                ),
            }
        )
    results = await rpc.eth_call_batch(calls, block=block)
    out: list[Optional[UniV3Quote]] = []
    for r in results:
        if not r.ok or not isinstance(r.result, str):
            out.append(None)
        else:
            out.append(parse_quote_exact_input_single_result(r.result))
    return out
