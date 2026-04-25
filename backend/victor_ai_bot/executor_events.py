from __future__ import annotations

"""Decode executor events for realized PnL.

We keep this tiny and deterministic. The contract emits:

event ArbExecuted(bytes32 indexed routeId, address indexed token, uint256 amountBorrowed, uint256 profit, uint8 provider);

topics:
- topic0: keccak256(signature)
- topic1: routeId (bytes32)
- topic2: token (address padded)
data:
- amountBorrowed (uint256)
- profit (uint256)
- provider (uint8 in uint256 slot)
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .abi_utils import topic0


_SAFE_EXECUTOR_EVENT_DECODE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


ARB_EXECUTED_SIG = "ArbExecuted(bytes32,address,uint256,uint256,uint8)"
ARB_EXECUTED_TOPIC0 = topic0(ARB_EXECUTED_SIG)


def _strip_0x(h: str) -> str:
    return h[2:] if isinstance(h, str) and h.startswith("0x") else h


def _addr_from_topic(t: str) -> str:
    h = _strip_0x(t)
    if len(h) != 64:
        h = h.rjust(64, "0")
    return "0x" + h[-40:]


@dataclass
class ArbExecuted:
    route_id: str
    token: str
    amount_borrowed: int
    profit: int
    provider: int


def decode_arb_executed(log: Dict[str, Any]) -> Optional[ArbExecuted]:
    try:
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) < 3:
            return None
        if str(topics[0]).lower() != ARB_EXECUTED_TOPIC0.lower():
            return None
        rid = "0x" + _strip_0x(str(topics[1])).rjust(64, "0")
        token = _addr_from_topic(str(topics[2]))

        data_hex = str(log.get("data") or "0x")
        data = bytes.fromhex(_strip_0x(data_hex))
        if len(data) < 32 * 3:
            return None
        amount = int.from_bytes(data[0:32], "big")
        profit = int.from_bytes(data[32:64], "big")
        provider = int.from_bytes(data[64:96], "big") & 0xFF
        return ArbExecuted(
            route_id=rid, token=token, amount_borrowed=amount, profit=profit, provider=provider
        )
    except _SAFE_EXECUTOR_EVENT_DECODE_EXCEPTIONS:
        return None
