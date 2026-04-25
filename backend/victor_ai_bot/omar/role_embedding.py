from __future__ import annotations
import hashlib
import numpy as np


def encode_role_vector(role_name: str, dim: int) -> np.ndarray:
    """Deterministic role embedding (no external deps)."""
    h = hashlib.sha256(role_name.encode("utf-8")).digest()
    # expand bytes to dim floats deterministically
    arr = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
    reps = int(np.ceil(dim / arr.shape[0]))
    v = np.tile(arr, reps)[:dim]
    v = (v - v.mean()) / (v.std() + 1e-6)
    return v
