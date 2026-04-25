from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Tuple
import numpy as np


@dataclass
class StepResult:
    state_vec: np.ndarray
    reward: float
    done: bool
    info: Dict[str, Any]


class SelfPlayEnv:
    """Multi-turn simulator for OMAR training.

    Non-breaking: this does NOT execute real trades.
    It simulates a simplified market+system dynamics using:
    - regime indicators (vol, gas, funding)
    - coordination and conflict penalties
    - stochastic opportunity arrival
    """

    def __init__(self, state_dim: int = 96, seed: int = 123):
        self.state_dim = state_dim
        self.rng = np.random.default_rng(seed)
        self.t = 0
        self.state = np.zeros((state_dim,), dtype=np.float32)

    def reset(self) -> np.ndarray:
        self.t = 0
        self.state = self.rng.normal(0, 1.0, size=(self.state_dim,)).astype(np.float32) * 0.1
        # set interpretable slots
        self.state[0] = float(self.rng.uniform(0.05, 0.35))  # vol
        self.state[1] = float(self.rng.uniform(0.05, 0.25))  # drawdown proxy
        self.state[2] = float(self.rng.uniform(20, 80))  # gas gwei proxy
        self.state[3] = float(self.rng.uniform(-0.02, 0.02))  # funding proxy
        self.state[4] = float(self.rng.uniform(0, 1))  # opportunity density
        return self.state.copy()

    def step(self, actions: Dict[str, str]) -> StepResult:
        self.t += 1
        # compute coordination score: how aligned actions are
        action_vals = list(actions.values())
        unique = len(set(action_vals))
        coordination = 1.0 / max(1, unique)  # 1 if all same, lower if fragmented
        conflict = 1.0 - coordination

        vol = float(self.state[0])
        gas = float(self.state[2])
        funding = float(self.state[3])
        opp = float(self.state[4])

        # reward shaping: profit proxy
        # risk-on actions help when opp high; risk-off helps when vol/gas high
        risk_on = sum(
            1 for a in action_vals if a in ("INCREASE_RISK", "SEEK_OPP", "EXECUTE")
        ) / max(1, len(action_vals))
        risk_off = sum(1 for a in action_vals if a in ("DECREASE_RISK", "WAIT", "DEFEND")) / max(
            1, len(action_vals)
        )

        pnl = (
            (opp * (0.8 * risk_on + 0.2)) - (vol * 0.6 * risk_on) - ((gas / 100.0) * 0.4 * risk_on)
        )
        pnl += (funding * 5.0) * (0.5 + risk_on)  # funding can help

        # penalty for conflict
        pnl -= conflict * 0.15

        # update state dynamics
        self.state[0] = np.clip(vol + self.rng.normal(0, 0.01), 0.01, 0.7)
        self.state[2] = np.clip(gas + self.rng.normal(0, 2.0), 5.0, 200.0)
        self.state[3] = np.clip(funding + self.rng.normal(0, 0.002), -0.05, 0.05)
        self.state[4] = np.clip(opp + self.rng.normal(0, 0.05), 0.0, 1.0)

        done = self.t >= 50
        info = {"coordination": coordination, "conflict": conflict, "pnl_proxy": float(pnl)}
        return StepResult(state_vec=self.state.copy(), reward=float(pnl), done=done, info=info)
