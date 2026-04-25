from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Tuple
import numpy as np


@dataclass
class PolicyOutput:
    action: Dict[str, float]  # action logits/probs by key
    value: float
    info: Dict[str, Any]


class UnifiedRolePolicy:
    """Tiny linear policy/value head for OMAR self-play.

    This is a lightweight placeholder to keep the system dependency-free.
    It can be swapped with a real torch model later without changing interfaces.
    """

    def __init__(self, state_dim: int, role_dim: int, action_keys: Tuple[str, ...]):
        self.state_dim = state_dim
        self.role_dim = role_dim
        self.action_keys = action_keys

        d = state_dim + role_dim
        rng = np.random.default_rng(7)
        self.W = rng.normal(0, 0.02, size=(len(action_keys), d)).astype(np.float32)
        self.b = np.zeros((len(action_keys),), dtype=np.float32)
        self.Wv = rng.normal(0, 0.02, size=(d,)).astype(np.float32)
        self.bv = np.float32(0.0)

    def forward(self, role_vec: np.ndarray, state_vec: np.ndarray) -> PolicyOutput:
        x = np.concatenate([role_vec.astype(np.float32), state_vec.astype(np.float32)], axis=0)
        logits = self.W @ x + self.b
        # softmax
        logits = logits - np.max(logits)
        probs = np.exp(logits) / (np.sum(np.exp(logits)) + 1e-9)
        action = {k: float(p) for k, p in zip(self.action_keys, probs)}
        value = float(self.Wv @ x + self.bv)
        return PolicyOutput(action=action, value=value, info={"probs": action, "value": value})

    def sample_action(self, out: PolicyOutput, rng: np.random.Generator) -> str:
        ps = np.array([out.action[k] for k in self.action_keys], dtype=np.float32)
        idx = int(rng.choice(len(self.action_keys), p=ps / ps.sum()))
        return self.action_keys[idx]

    def update_ppo(
        self, batch: Dict[str, np.ndarray], lr: float, clip_eps: float
    ) -> Dict[str, float]:
        """Very small PPO-style update (approx)."""
        # batch keys: X (N,d), A (N,), ADV (N,), OLD_P (N,), returns (N,)
        X = batch["X"].astype(np.float32)
        A = batch["A"].astype(np.int64)
        ADV = batch["ADV"].astype(np.float32)
        OLD_P = batch["OLD_P"].astype(np.float32)
        # compute new probs
        logits = (X @ self.W.T) + self.b
        logits = logits - logits.max(axis=1, keepdims=True)
        probs = np.exp(logits) / (np.sum(np.exp(logits), axis=1, keepdims=True) + 1e-9)
        new_p = probs[np.arange(len(A)), A]
        ratio = new_p / (OLD_P + 1e-9)
        clipped = np.clip(ratio, 1.0 - clip_eps, 1.0 + clip_eps)
        # surrogate gradient sign
        w = np.where(ratio < clipped, ratio, clipped) * ADV
        # gradient approx for softmax linear head
        grad_logits = np.zeros_like(probs)
        grad_logits[np.arange(len(A)), A] = 1.0
        grad_logits = (grad_logits - probs) * (w[:, None] / max(1, len(A)))
        gradW = grad_logits.T @ X
        gradb = grad_logits.sum(axis=0)

        self.W += lr * gradW
        self.b += lr * gradb

        # value head (simple regression)
        ret = batch["RET"].astype(np.float32)
        v = X @ self.Wv + self.bv
        dv = (ret - v) / max(1, len(A))
        self.Wv += lr * (X.T @ dv)
        self.bv += lr * float(dv.sum())

        return {
            "mean_adv": float(ADV.mean()),
            "mean_ratio": float(ratio.mean()),
            "mean_new_p": float(new_p.mean()),
        }
