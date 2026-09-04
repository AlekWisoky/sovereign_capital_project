from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np


@dataclass
class PolicyOutput:
    action: Dict[str, float]
    value: float
    info: Dict[str, Any]


class UnifiedRolePolicy:
    """Small persistent policy/value head used by OMAR.

    Its checkpoint is operational learning state: restarting OMAR must not erase
    the policy learned from settled real outcomes.
    """

    CHECKPOINT_VERSION = 1

    def __init__(
        self,
        state_dim: int,
        role_dim: int,
        action_keys: Tuple[str, ...],
        checkpoint_path: str | None = None,
    ):
        self.state_dim = int(state_dim)
        self.role_dim = int(role_dim)
        self.action_keys = tuple(action_keys)
        self.checkpoint_path = str(checkpoint_path or "")
        self.load_error = ""
        self.save_error = ""
        d = self.state_dim + self.role_dim
        rng = np.random.default_rng(7)
        self.W = rng.normal(0, 0.02, size=(len(self.action_keys), d)).astype(np.float32)
        self.b = np.zeros((len(self.action_keys),), dtype=np.float32)
        self.Wv = rng.normal(0, 0.02, size=(d,)).astype(np.float32)
        self.bv = np.float32(0.0)
        self.updates = 0
        if self.checkpoint_path:
            self.load()

    def forward(self, role_vec: np.ndarray, state_vec: np.ndarray) -> PolicyOutput:
        x = np.concatenate([role_vec.astype(np.float32), state_vec.astype(np.float32)], axis=0)
        logits = self.W @ x + self.b
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
        X = batch["X"].astype(np.float32)
        A = batch["A"].astype(np.int64)
        ADV = batch["ADV"].astype(np.float32)
        OLD_P = batch["OLD_P"].astype(np.float32)
        logits = (X @ self.W.T) + self.b
        logits = logits - logits.max(axis=1, keepdims=True)
        probs = np.exp(logits) / (np.sum(np.exp(logits), axis=1, keepdims=True) + 1e-9)
        new_p = probs[np.arange(len(A)), A]
        ratio = new_p / (OLD_P + 1e-9)
        clipped = np.clip(ratio, 1.0 - clip_eps, 1.0 + clip_eps)
        w = np.where(ratio < clipped, ratio, clipped) * ADV
        grad_logits = np.zeros_like(probs)
        grad_logits[np.arange(len(A)), A] = 1.0
        grad_logits = (grad_logits - probs) * (w[:, None] / max(1, len(A)))
        gradW = grad_logits.T @ X
        gradb = grad_logits.sum(axis=0)
        self.W += lr * gradW
        self.b += lr * gradb
        ret = batch["RET"].astype(np.float32)
        v = X @ self.Wv + self.bv
        dv = (ret - v) / max(1, len(A))
        self.Wv += lr * (X.T @ dv)
        self.bv += lr * float(dv.sum())
        self.updates += int(len(A))
        return {
            "mean_adv": float(ADV.mean()),
            "mean_ratio": float(ratio.mean()),
            "mean_new_p": float(new_p.mean()),
        }

    def update_from_real_outcome(
        self,
        *,
        role_vec: np.ndarray,
        state_vec: np.ndarray,
        action_index: int,
        reward_scaled: float,
        learning_rate: float,
        clip_epsilon: float,
    ) -> Dict[str, float]:
        idx = int(action_index)
        if idx < 0 or idx >= len(self.action_keys):
            return {"updated": 0.0, "reason": 0.0}
        x = np.concatenate([role_vec.astype(np.float32), state_vec.astype(np.float32)], axis=0)
        out = self.forward(role_vec, state_vec)
        old_p = float(out.action[self.action_keys[idx]])
        reward = float(np.clip(float(reward_scaled), -1_000_000.0, 1_000_000.0))
        batch = {
            "X": np.asarray([x], dtype=np.float32),
            "A": np.asarray([idx], dtype=np.int64),
            "ADV": np.asarray([reward], dtype=np.float32),
            "OLD_P": np.asarray([old_p], dtype=np.float32),
            "RET": np.asarray([reward], dtype=np.float32),
        }
        stats = self.update_ppo(batch, lr=float(learning_rate), clip_eps=float(clip_epsilon))
        stats["updated"] = 1.0
        stats["reward_scaled"] = reward
        return stats

    def save(self) -> bool:
        if not self.checkpoint_path:
            return False
        try:
            os.makedirs(os.path.dirname(self.checkpoint_path), exist_ok=True)
            payload = {
                "version": self.CHECKPOINT_VERSION,
                "state_dim": self.state_dim,
                "role_dim": self.role_dim,
                "action_keys": list(self.action_keys),
                "W": self.W.tolist(),
                "b": self.b.tolist(),
                "Wv": self.Wv.tolist(),
                "bv": float(self.bv),
                "updates": int(self.updates),
            }
            tmp = f"{self.checkpoint_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, self.checkpoint_path)
            self.save_error = ""
            return True
        except (OSError, TypeError, ValueError) as exc:
            self.save_error = str(exc)
            return False

    def load(self) -> bool:
        if not self.checkpoint_path or not os.path.exists(self.checkpoint_path):
            return False
        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if (
                not isinstance(payload, dict)
                or int(payload.get("version", 0)) != self.CHECKPOINT_VERSION
            ):
                raise ValueError("invalid_policy_checkpoint")
            if (
                int(payload.get("state_dim", -1)) != self.state_dim
                or int(payload.get("role_dim", -1)) != self.role_dim
            ):
                raise ValueError("policy_dimension_mismatch")
            if tuple(payload.get("action_keys") or []) != self.action_keys:
                raise ValueError("policy_action_space_mismatch")
            self.W = np.asarray(payload["W"], dtype=np.float32)
            self.b = np.asarray(payload["b"], dtype=np.float32)
            self.Wv = np.asarray(payload["Wv"], dtype=np.float32)
            self.bv = np.float32(payload["bv"])
            self.updates = int(payload.get("updates", 0) or 0)
            self.load_error = ""
            return True
        except (OSError, TypeError, ValueError, KeyError) as exc:
            self.load_error = str(exc)
            return False

    def state(self) -> Dict[str, Any]:
        return {
            "checkpointPath": self.checkpoint_path,
            "updates": int(self.updates),
            "loadError": self.load_error,
            "saveError": self.save_error,
        }
