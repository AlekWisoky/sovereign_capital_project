from __future__ import annotations

"""Deterministic route encoding.

We need a stable route representation so:
- the backend can compute a deterministic route_id (bytes32)
- the contract can emit the same route_id for receipt parsing

Constraints:
- Must be additive; existing Opportunity schema remains valid.
- Must be stable across Python versions.
- Must not depend on heavy ABI libraries.

Encoding (versioned, canonical):

route_bytes :=
  0x01 (version 1, 1 byte)
  n_legs (1 byte)
  for each leg:
    dex_id (1 byte)
    venue (20 bytes)
    token_in (20 bytes)
    token_out (20 bytes)
    aux (32 bytes)

dex_id mapping:
  1 = univ3
  2 = curve
  3 = balancer

aux is a bytes32 (hex string) used by the executor for dex-specific parameters.
"""

from dataclasses import dataclass
from typing import Iterable, List, Literal

from .ethabi import keccak256


DexType = Literal["univ3", "curve", "balancer"]


DEX_ID = {
    "univ3": 1,
    "curve": 2,
    "balancer": 3,
}


def _addr20(addr: str) -> bytes:
    a = (addr or "").lower()
    if a.startswith("0x"):
        a = a[2:]
    if len(a) != 40:
        a = a.rjust(40, "0")
    return bytes.fromhex(a)


def _b32(aux_hex: str) -> bytes:
    h = (aux_hex or "").lower()
    if h.startswith("0x"):
        h = h[2:]
    if not h:
        return b"\x00" * 32
    raw = bytes.fromhex(h)
    if len(raw) == 32:
        return raw
    if len(raw) > 32:
        return raw[-32:]
    return raw.rjust(32, b"\x00")


@dataclass(frozen=True)
class EncLeg:
    dex: DexType
    venue: str
    token_in: str
    token_out: str
    aux: str = "0x"


def encode_route(legs: Iterable[EncLeg]) -> bytes:
    legs_list = list(legs)
    if len(legs_list) > 255:
        raise ValueError("too many legs")
    out = bytearray()
    out.append(0x01)
    out.append(len(legs_list))
    for leg in legs_list:
        dex_id = DEX_ID.get(leg.dex)
        if not dex_id:
            raise ValueError(f"unknown dex: {leg.dex}")
        out.append(dex_id)
        out += _addr20(leg.venue)
        out += _addr20(leg.token_in)
        out += _addr20(leg.token_out)
        out += _b32(leg.aux)
    return bytes(out)


def route_id_hex(legs: Iterable[EncLeg]) -> str:
    b = encode_route(legs)
    return "0x" + keccak256(b).hex()
