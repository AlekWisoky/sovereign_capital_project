from __future__ import annotations
import numpy as np


def compute_gae(rewards: np.ndarray, values: np.ndarray, gamma: float) -> np.ndarray:
    adv = np.zeros_like(rewards, dtype=np.float32)
    last = 0.0
    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * (values[t + 1] if t + 1 < len(values) else 0.0) - values[t]
        last = delta + gamma * 0.95 * last
        adv[t] = last
    return adv


def hierarchical_advantage(
    turn_adv: np.ndarray, token_adv: np.ndarray, w_turn: float, w_token: float
) -> np.ndarray:
    w_sum = max(1e-6, (w_turn + w_token))
    w_turn /= w_sum
    w_token /= w_sum
    return (turn_adv * w_turn + token_adv * w_token).astype(np.float32)
