from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
from .rpc import JsonRpcClient

GWEI = 10**9

_SAFE_GAS_BATCH_EXCEPTIONS = (TypeError, ValueError, IndexError)


@dataclass
class GasQuote:
    max_fee_wei: int
    priority_fee_wei: int
    gas_limit: int

    @property
    def est_cost_wei(self) -> int:
        return self.max_fee_wei * self.gas_limit


def _gwei(n: int) -> int:
    return int(n) * GWEI


def _preset_value(presets, name: str, default: int) -> int:
    try:
        if isinstance(presets, dict):
            value = presets.get(name, default)
        else:
            value = getattr(presets, name, default)
        return int(value)
    except (TypeError, ValueError, AttributeError):
        return int(default)


async def suggest_gas(rpc: JsonRpcClient, *, mode: str, presets) -> Tuple[int, int]:
    # Returns (max_fee_wei, priority_fee_wei)
    mode = (mode or "standard").lower()
    if mode == "fast":
        max_fee = _gwei(_preset_value(presets, "fast_max_fee_gwei", 30))
        prio = _gwei(_preset_value(presets, "fast_priority_fee_gwei", 2))
    elif mode == "instant":
        max_fee = _gwei(_preset_value(presets, "instant_max_fee_gwei", 50))
        prio = _gwei(_preset_value(presets, "instant_priority_fee_gwei", 3))
    else:
        max_fee = _gwei(_preset_value(presets, "standard_max_fee_gwei", 20))
        prio = _gwei(_preset_value(presets, "standard_priority_fee_gwei", 1))

    # Latency optimization (additive): fetch feeHistory and gasPrice in one HTTP roundtrip
    # when JSON-RPC batching is supported by the provider.
    tip = None
    gp = None
    rs = await rpc.batch(
        [
            ("eth_feeHistory", ["0x5", "latest", [50]]),
            ("eth_gasPrice", []),
        ]
    )
    try:
        if len(rs) >= 1 and rs[0].ok and isinstance(rs[0].result, dict):
            rewards = rs[0].result.get("reward")
            if (
                rewards
                and isinstance(rewards, list)
                and rewards[-1]
                and isinstance(rewards[-1], list)
            ):
                tip_hex = rewards[-1][0]
                if isinstance(tip_hex, str):
                    tip = int(tip_hex, 16)
        if len(rs) >= 2 and rs[1].ok and isinstance(rs[1].result, str):
            gp = int(rs[1].result, 16)
    except _SAFE_GAS_BATCH_EXCEPTIONS:
        tip = None
        gp = None

    # If feeHistory tip is available, clamp priority fee to at least the median tip.
    if tip is None:
        tip = await rpc.fee_history_tip()
    if tip is not None and tip > prio:
        prio = tip

    # Fallback for networks without 1559: use gasPrice as max_fee.
    if gp is None:
        gp = await rpc.gas_price()
    if gp is not None and gp > max_fee:
        max_fee = gp
    return max_fee, prio


async def estimate_cost(
    rpc: JsonRpcClient,
    *,
    tx: dict,
    gas_mode: str,
    presets,
    gas_limit_fallback: int = 300_000,
) -> GasQuote:
    gl = await rpc.estimate_gas(tx) or int(gas_limit_fallback)
    max_fee, prio = await suggest_gas(rpc, mode=gas_mode, presets=presets)
    return GasQuote(max_fee_wei=max_fee, priority_fee_wei=prio, gas_limit=int(gl))
