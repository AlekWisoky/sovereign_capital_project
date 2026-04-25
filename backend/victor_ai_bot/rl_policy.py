from __future__ import annotations

import json
import os
from .determinism import stable_hash_int, stable_uniform_0_1
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


_SAFE_RL_SAVE_EXCEPTIONS = (OSError, TypeError, ValueError)
_SAFE_RL_LOAD_EXCEPTIONS = (OSError, json.JSONDecodeError, TypeError, ValueError)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class Action:
    """Action chosen by RL.

    size_mult is constrained to <= 1.0 by design (safety: do not upsize without re-quoting).
    gas_mode may override config for the single attempt.
    """

    size_mult: float
    gas_mode: str
    borrow_mult: float = 1.0


class RlPolicy:
    """Tabular contextual bandit (Q-learning with gamma=0).

    Efficient and stable online learning:
    - Very small state representation (bucketized)
    - O(1) update per trade
    - Persisted to JSON for portability

    Reward is normalized (profit_after_gas / amount_in), then scaled.
    """

    # Expanded action space (alpha): includes borrow scaling.
    # borrow_mult may be >1.0; execution path will re-quote and enforce hard caps.
    ACTIONS: List[Action] = []

    @classmethod
    def _build_actions(cls) -> List[Action]:
        sizes = [1.0, 0.75, 0.5]
        gas_modes = ["standard", "fast", "instant"]
        borrows = [0.75, 1.0, 1.5, 2.0]
        out: List[Action] = []
        for gm in gas_modes:
            for bm in borrows:
                for sm in sizes:
                    out.append(Action(size_mult=float(sm), gas_mode=str(gm), borrow_mult=float(bm)))
        return out

    @classmethod
    def ensure_actions(cls) -> None:
        if not cls.ACTIONS:
            cls.ACTIONS = cls._build_actions()

    def __init__(
        self,
        *,
        path: str,
        alpha: float = 0.12,
        epsilon: float = 0.08,
        epsilon_min: float = 0.02,
        epsilon_decay_per_1k: float = 0.02,
    ):
        # Ensure expanded action space is initialized before loading persisted Q-table.
        type(self).ensure_actions()
        self.path = path
        self.alpha = float(alpha)
        self.epsilon = float(epsilon)
        self.epsilon_min = float(epsilon_min)
        self.epsilon_decay_per_1k = float(epsilon_decay_per_1k)

        self.q: Dict[str, List[float]] = {}
        self.n: Dict[str, int] = {}
        self.total_updates: int = 0
        self._load()

    # -----------------
    # State bucketing
    # -----------------
    def bucket_state(
        self, *, margin_ratio: float, gas_ratio: float, has_curve: int, has_balancer: int, legs: int
    ) -> str:
        # margin buckets (profit - gas) as ratio of amount_in
        mr = margin_ratio
        if mr < 0:
            b_m = "m_neg"
        elif mr < 0.0005:
            b_m = "m_tiny"
        elif mr < 0.0010:
            b_m = "m_low"
        elif mr < 0.0020:
            b_m = "m_mid"
        else:
            b_m = "m_hi"

        gr = gas_ratio
        if gr < 0.0002:
            b_g = "g_vlow"
        elif gr < 0.0005:
            b_g = "g_low"
        elif gr < 0.0010:
            b_g = "g_mid"
        else:
            b_g = "g_hi"

        b_p = "p_uni"
        if has_curve:
            b_p = "p_curve"
        if has_balancer:
            b_p = "p_bal"

        b_l = "l2" if legs <= 2 else "l3"
        return f"{b_m}|{b_g}|{b_p}|{b_l}"

    def _ensure_state(self, s: str) -> None:
        if s not in self.q:
            self.q[s] = [0.0 for _ in self.ACTIONS]
            self.n[s] = 0

    # -----------------
    # Action selection
    # -----------------
    def select(
        self, s: str, *, force_conservative: bool = False, seed: str = ""
    ) -> Tuple[int, Action, float]:
        """Return (action_index, Action, q_value)."""
        self._ensure_state(s)

        eps = self.epsilon
        if force_conservative:
            eps = 0.0

        # Deterministic exploration derived from seed.
        # IMPORTANT: decisions must be reproducible for identical state+seed.
        u = stable_uniform_0_1(f"rl:eps:{seed}:{s}:{int(self.total_updates)}")
        if u < eps:
            idx = stable_hash_int(
                f"rl:pick:{seed}:{s}:{int(self.total_updates)}", modulo=len(self.ACTIONS)
            )
            return idx, self.ACTIONS[idx], float(self.q[s][idx])

        # exploit
        qs = self.q[s]
        # Exploit: deterministic tie-break by lowest index.
        best = max(float(v) for v in qs)
        idx = next((i for i, v in enumerate(qs) if float(v) == best), 0)
        return int(idx), self.ACTIONS[int(idx)], float(qs[int(idx)])

    # -----------------
    # Update
    # -----------------
    def update(self, s: str, a_idx: int, reward: float) -> None:
        self._ensure_state(s)
        reward = float(_clamp(reward, -50.0, 50.0))

        old = float(self.q[s][a_idx])
        self.q[s][a_idx] = old + self.alpha * (reward - old)
        self.n[s] = int(self.n.get(s, 0)) + 1
        self.total_updates += 1

        # epsilon decay every 1k updates
        if self.total_updates % 1000 == 0:
            self.epsilon = max(self.epsilon_min, self.epsilon - self.epsilon_decay_per_1k)

        # persist occasionally
        if self.total_updates % 25 == 0:
            self.save()

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            payload = {
                "v": 2,
                "ts": int(time.time()),
                "alpha": self.alpha,
                "epsilon": self.epsilon,
                "epsilon_min": self.epsilon_min,
                "epsilon_decay_per_1k": self.epsilon_decay_per_1k,
                "total_updates": self.total_updates,
                "q": self.q,
                "n": self.n,
            }
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except _SAFE_RL_SAVE_EXCEPTIONS:
            return

    def _load(self) -> None:
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return
            v = int(payload.get("v", 0))
            if v not in {1, 2}:
                return
            self.alpha = float(payload.get("alpha", self.alpha))
            self.epsilon = float(payload.get("epsilon", self.epsilon))
            self.epsilon_min = float(payload.get("epsilon_min", self.epsilon_min))
            self.epsilon_decay_per_1k = float(
                payload.get("epsilon_decay_per_1k", self.epsilon_decay_per_1k)
            )
            self.total_updates = int(payload.get("total_updates", 0))
            q = payload.get("q")
            n = payload.get("n")
            if isinstance(q, dict):
                fixed: Dict[str, List[float]] = {}
                for k, arr in q.items():
                    if not isinstance(arr, list):
                        continue
                    if len(arr) == len(self.ACTIONS):
                        fixed[str(k)] = [float(x) for x in arr]
                        continue
                    # Back-compat v1: map old 7-action table to new expanded actions.
                    if v == 1 and len(arr) == 7:
                        mapped = [0.0 for _ in self.ACTIONS]
                        # old actions were: (1,0.75,0.5)*standard + (1,0.75,0.5)*fast + (1)*instant
                        old = [
                            Action(1.0, "standard", 1.0),
                            Action(0.75, "standard", 1.0),
                            Action(0.5, "standard", 1.0),
                            Action(1.0, "fast", 1.0),
                            Action(0.75, "fast", 1.0),
                            Action(0.5, "fast", 1.0),
                            Action(1.0, "instant", 1.0),
                        ]
                        for i_old, act in enumerate(old):
                            idx = self._index_for_action(act)
                            if idx >= 0:
                                mapped[idx] = float(arr[i_old])
                        fixed[str(k)] = mapped
                self.q = fixed
            if isinstance(n, dict):
                self.n = {str(k): int(v) for k, v in n.items() if isinstance(v, (int, float, str))}
        except _SAFE_RL_LOAD_EXCEPTIONS:
            return

    def summary(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "states": int(len(self.q)),
            "total_updates": int(self.total_updates),
            "epsilon": float(self.epsilon),
            "alpha": float(self.alpha),
            "actions": [
                {"size_mult": a.size_mult, "gas_mode": a.gas_mode, "borrow_mult": a.borrow_mult}
                for a in self.ACTIONS
            ],
        }

    def _index_for_action(self, a: Action) -> int:
        for i, act in enumerate(self.ACTIONS):
            if (
                act.gas_mode == a.gas_mode
                and abs(act.size_mult - a.size_mult) < 1e-9
                and abs(act.borrow_mult - a.borrow_mult) < 1e-9
            ):
                return i
        return -1
