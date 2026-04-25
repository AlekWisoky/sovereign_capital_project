from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _softplus(x: float) -> float:
    # stable-ish softplus
    if x > 30:
        return x
    return math.log1p(math.exp(x))


def _hash01(s: str) -> float:
    # Deterministic pseudo-random in [0,1)
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return (h % 10_000_000) / 10_000_000.0


@dataclass
class VDN:
    """Value Decomposition Network (VDN): joint Q is the sum of per-agent Q."""

    def mix(self, agent_qs: List[Dict[str, float]]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for q in agent_qs:
            for a, v in q.items():
                out[a] = float(out.get(a, 0.0)) + float(v)
        return out


@dataclass
class QMIX:
    """Lightweight QMIX-style monotonic mixer.

    True QMIX uses a hypernetwork to generate mixing weights from global state.
    Here we keep the same *monotonicity* property (weights >= 0), but implement
    a tiny deterministic hypernet based on hashed state features.

    This is intentionally minimal and dependency-free; it is used primarily as
    a coordination baseline (Phase 1) and as a stable interface for later phases.
    """

    n_agents: int

    def _weights(self, state_key: str, action_key: str) -> Tuple[List[float], float]:
        ws: List[float] = []
        for i in range(self.n_agents):
            x = (_hash01(f"{state_key}|{action_key}|w|{i}") - 0.5) * 6.0
            ws.append(_softplus(x))  # >=0
        b = (_hash01(f"{state_key}|{action_key}|b") - 0.5) * 2.0
        return ws, b

    def mix(self, agent_qs: List[Dict[str, float]], *, state_key: str) -> Dict[str, float]:
        if not agent_qs:
            return {}
        # union of action keys
        action_keys = set()
        for q in agent_qs:
            action_keys.update(q.keys())

        out: Dict[str, float] = {}
        for a in action_keys:
            ws, b = self._weights(state_key, a)
            s = 0.0
            for i, q in enumerate(agent_qs):
                qi = float(q.get(a, 0.0))
                wi = ws[i] if i < len(ws) else 1.0
                s += wi * qi
            out[a] = s + b
        return out
