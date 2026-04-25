from __future__ import annotations

"""Build executor calldata deterministically.

This module is intentionally *pure* and testable.
It must produce non-empty calldata for real execution.

Executor ABI (v2):

execute(
  uint8 provider,
  address borrowToken,
  uint256 amountBorrow,
  uint256 minProfit,
  address profitTo,
  uint256 deadline,
  bytes32 routeId,
  (uint8 dex, address venue, address tokenIn, address tokenOut, uint256 minOut, bytes32 aux)[] legs
)

All bigint-like values are passed in as Python ints; callers are responsible for string conversion
at API boundaries.
"""

# Builder versioning (prevents silent drift).
CALLDATA_BUILDER_ABI_VERSION = 2
CALLDATA_BUILDER_VERSION = "2.0.0"

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .ethabi import selector, enc_uint, enc_address, enc_bytes32
from .route_encoding import EncLeg, route_id_hex


PROVIDER_ID = {
    "aave": 1,
    "balancer": 2,
}


DEX_ID = {
    "univ3": 1,
    "curve": 2,
    "balancer": 3,
}


def _strip_0x(h: str) -> str:
    return h[2:] if isinstance(h, str) and h.startswith("0x") else h


def _b32_from_hex(aux_hex: str) -> bytes:
    h = _strip_0x(aux_hex or "")
    if not h:
        return b"\x00" * 32
    raw = bytes.fromhex(h)
    if len(raw) == 32:
        return raw
    if len(raw) > 32:
        return raw[-32:]
    return raw.rjust(32, b"\x00")


def _enc_uint8(n: int) -> bytes:
    # ABI uses uint256 slots; uint8 is right-padded in a 32-byte word.
    return enc_uint(n & 0xFF)


def _encode_leg_tuple(
    dex: str, venue: str, token_in: str, token_out: str, min_out: int, aux_hex: str
) -> bytes:
    return (
        _enc_uint8(int(DEX_ID[dex]))
        + enc_address(venue)
        + enc_address(token_in)
        + enc_address(token_out)
        + enc_uint(int(min_out))
        + enc_bytes32(_b32_from_hex(aux_hex))
    )


def _encode_dynamic_leg_array(legs: List[Dict[str, Any]]) -> bytes:
    # dynamic array encoding: length + elements
    out = bytearray()
    out += enc_uint(len(legs))
    for leg in legs:
        out += _encode_leg_tuple(
            dex=str(leg["dex"]),
            venue=str(leg["venue"]),
            token_in=str(leg["token_in"]),
            token_out=str(leg["token_out"]),
            min_out=int(leg["min_out"]),
            aux_hex=str(leg.get("aux") or "0x"),
        )
    return bytes(out)


def build_execute_calldata(
    *,
    provider: str,
    borrow_token: str,
    amount_borrow: int,
    min_profit: int,
    profit_to: str,
    deadline: int,
    legs: List[Dict[str, Any]],
) -> Tuple[str, str]:
    """Returns (calldata_hex, route_id_hex)."""
    prov_id = PROVIDER_ID.get(provider, 1)
    enc_legs_for_id = [
        EncLeg(
            dex=str(l["dex"]),
            venue=str(l["venue"]),
            token_in=str(l["token_in"]),
            token_out=str(l["token_out"]),
            aux=str(l.get("aux") or "0x"),
        )
        for l in legs
    ]
    rid = route_id_hex(enc_legs_for_id)

    # ABI encoding: head (8 args) with dynamic legs offset.
    # Head is 8 * 32 bytes. Legs data starts immediately after head.
    head_size = 8 * 32
    legs_blob = _encode_dynamic_leg_array(legs)

    head = bytearray()
    head += _enc_uint8(prov_id)
    head += enc_address(borrow_token)
    head += enc_uint(int(amount_borrow))
    head += enc_uint(int(min_profit))
    head += enc_address(profit_to)
    head += enc_uint(int(deadline))
    head += enc_bytes32(bytes.fromhex(_strip_0x(rid)))
    head += enc_uint(head_size)  # offset to legs

    sig = "execute(uint8,address,uint256,uint256,address,uint256,bytes32,(uint8,address,address,address,uint256,bytes32)[])"
    data = selector(sig) + bytes(head) + legs_blob
    return "0x" + data.hex(), rid
