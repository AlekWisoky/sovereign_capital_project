"""Deterministic utilities.

These helpers provide *reproducible* pseudo-randomness derived from a stable
hash of the provided seed.

Design goals:
- No dependence on Python's global RNG.
- Stable across processes and runs.
- Cheap enough for per-opportunity decisioning.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Sequence, Tuple, TypeVar

T = TypeVar("T")


def stable_hash_int(seed: str, *, modulo: int | None = None) -> int:
    """Return a stable non-negative integer derived from `seed`.

    If `modulo` is provided, result is in [0, modulo).
    """

    if seed is None:
        seed = ""
    b = seed.encode("utf-8", errors="ignore")
    # blake2b is fast and stable.
    h = hashlib.blake2b(b, digest_size=8).digest()
    x = int.from_bytes(h, "big", signed=False)
    if modulo is not None and int(modulo) > 0:
        return int(x % int(modulo))
    return int(x)


def stable_uniform_0_1(seed: str) -> float:
    """Stable uniform float in [0, 1)."""

    # Use 53 bits (mantissa) for a float in [0,1)
    x = stable_hash_int(seed)
    return float((x >> 11) & ((1 << 53) - 1)) / float(1 << 53)


def stable_choice(seq: Sequence[T], seed: str) -> T:
    """Deterministically choose one element from `seq`."""

    if not seq:
        raise ValueError("stable_choice on empty sequence")
    i = stable_hash_int(seed, modulo=len(seq))
    return seq[int(i)]


def stable_index_weighted(weights: Sequence[float], seed: str) -> int:
    """Deterministically sample an index from non-negative weights."""

    if not weights:
        return 0
    w: List[float] = [max(0.0, float(x)) for x in weights]
    s = float(sum(w))
    if s <= 1e-18:
        return int(stable_hash_int(seed, modulo=len(w)))
    r = stable_uniform_0_1(seed) * s
    acc = 0.0
    for i, wi in enumerate(w):
        acc += wi
        if r <= acc:
            return int(i)
    return int(len(w) - 1)


def stable_choice_weighted(
    items: Sequence[T], weights: Sequence[float], seed: str
) -> Tuple[int, T]:
    """Deterministically sample an item from weighted list."""

    if len(items) != len(weights):
        raise ValueError("items/weights length mismatch")
    idx = stable_index_weighted(weights, seed)
    return idx, items[int(idx)]


def stable_dict_hash(obj: Dict[str, Any], *, seed: str = "") -> str:
    """Best-effort stable hash for a dict (used for deterministic seeds).

    This is intentionally simple and avoids heavy serialization dependencies.
    """

    try:
        parts = []
        for k in sorted(obj.keys()):
            v = obj.get(k)
            parts.append(f"{k}={v}")
        base = "|".join(parts)
    except (AttributeError, TypeError):
        base = str(obj)
    h = hashlib.blake2b(
        (seed + "|" + base).encode("utf-8", errors="ignore"), digest_size=16
    ).hexdigest()
    return h
