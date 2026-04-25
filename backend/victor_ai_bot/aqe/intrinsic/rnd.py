from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


def _hash_u32(s: str) -> int:
    h = 2166136261
    for ch in s:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return int(h)


def _target_vec(key: str, *, dim: int) -> List[float]:
    # Deterministic pseudo-random target embedding in [-1,1]
    base = _hash_u32(key)
    out: List[float] = []
    for i in range(dim):
        x = (base ^ (i * 0x9E3779B9)) & 0xFFFFFFFF
        # map to (0,1)
        u = (x % 10_000_000) / 10_000_000.0
        out.append(math.sin((u * 2.0 - 1.0) * math.pi))
    return out


def _mse(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    s = 0.0
    for i in range(n):
        d = float(a[i]) - float(b[i])
        s += d * d
    return s / float(n)


@dataclass
class RND:
    """Random Network Distillation (dependency-free approximation).

    Classic RND uses a fixed random network (target) and a trainable predictor.
    Prediction error becomes intrinsic reward (novelty).

    Here we implement a lightweight hashed-linear predictor:
      - target embedding is deterministic from `state_key`
      - predictor stores a small vector per hashed bucket
      - SGD update nudges predictor toward target

    This is cheap, stable, and works in production environments without heavy ML deps.
    """

    buckets: int = 2048
    dim: int = 8
    lr: float = 0.05

    def __post_init__(self):
        self._w: Dict[int, List[float]] = {}

    def _bucket(self, state_key: str) -> int:
        return _hash_u32(state_key) % int(max(1, self.buckets))

    def predict(self, state_key: str) -> Tuple[List[float], List[float]]:
        t = _target_vec(state_key, dim=int(self.dim))
        b = self._bucket(state_key)
        p = self._w.get(b)
        if p is None:
            p = [0.0 for _ in range(int(self.dim))]
            self._w[b] = p
        return p, t

    def novelty(self, state_key: str, *, train: bool = True) -> float:
        pred, tgt = self.predict(state_key)
        err = _mse(pred, tgt)
        if train:
            # SGD: pred += lr*(tgt - pred)
            lr = float(self.lr)
            for i in range(min(len(pred), len(tgt))):
                pred[i] = float(pred[i]) + lr * (float(tgt[i]) - float(pred[i]))
        return float(err)
