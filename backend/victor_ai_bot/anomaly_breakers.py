"""Anomaly breakers (additive, safety-first).

These are *observability-driven* circuit breakers that can optionally trigger
"Defensive Mode" (size clamps) or pause auto-trading when conditions indicate
execution is likely to be uncompetitive or unsafe.

Key design constraints:
- Additive: disabled by default at runtime unless enabled by Command Center controls.
- Deterministic logic given inputs (no randomness).
- Must never be used to create risk-seeking behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Optional
from collections import deque


def gas_spike_detected(
    *,
    history_gwei: list[float],
    current_gwei: float,
    mult: float = 2.5,
    min_abs_gwei: float = 40.0,
) -> bool:
    """Return True if the current gas basefee appears anomalously high.

    Heuristic:
      current > max(min_abs_gwei, median(history)*mult)
    """
    if current_gwei <= 0:
        return False
    if not history_gwei:
        return current_gwei >= float(min_abs_gwei)
    xs = sorted(float(x) for x in history_gwei if x is not None)
    if not xs:
        return current_gwei >= float(min_abs_gwei)
    med = xs[len(xs) // 2]
    thresh = max(float(min_abs_gwei), float(med) * float(mult))
    return float(current_gwei) > thresh


@dataclass
class AnomalyBreakerState:
    gas_history: Deque[float]
    rpc_error_streak: int = 0
    gas_spike: bool = False


class AnomalyBreaker:
    """Maintains rolling inputs to detect gas spikes and RPC error storms."""

    def __init__(self, *, window: int = 60):
        self.state = AnomalyBreakerState(gas_history=deque(maxlen=max(10, int(window))))

    def observe_gas(self, *, basefee_gwei: float) -> bool:
        self.state.gas_history.append(float(basefee_gwei))
        self.state.gas_spike = gas_spike_detected(
            history_gwei=list(self.state.gas_history), current_gwei=float(basefee_gwei)
        )
        return bool(self.state.gas_spike)

    def observe_rpc_error(self, *, ok: bool, threshold: int = 5) -> bool:
        if ok:
            self.state.rpc_error_streak = 0
            return False
        self.state.rpc_error_streak += 1
        return self.state.rpc_error_streak >= int(threshold)

    def snapshot(self) -> dict:
        return {
            "rpc_error_streak": int(self.state.rpc_error_streak),
            "gas_spike": bool(self.state.gas_spike),
            "gas_history_len": int(len(self.state.gas_history)),
        }
