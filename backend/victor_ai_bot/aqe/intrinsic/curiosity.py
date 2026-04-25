from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class TransitionCuriosity:
    """Curiosity-driven prediction error (simple count-based model).

    We model P(outcome | state, action) where outcome is {ok,fail}.
    Surprise is -log(P). This yields higher intrinsic reward when outcomes are
    uncertain or rarely seen.
    """

    def __post_init__(self):
        self.counts: Dict[Tuple[str, str, str], int] = {}  # (state,action,outcome)->count
        self.totals: Dict[Tuple[str, str], int] = {}       # (state,action)->count

    def observe(self, state_key: str, action_key: str, *, ok: bool) -> float:
        outcome = "ok" if ok else "fail"
        k = (state_key, action_key, outcome)
        self.counts[k] = int(self.counts.get(k, 0)) + 1
        k2 = (state_key, action_key)
        self.totals[k2] = int(self.totals.get(k2, 0)) + 1

        # Laplace smoothing
        tot = float(self.totals[k2])
        p = (float(self.counts[k]) + 1.0) / (tot + 2.0)
        return float(-math.log(max(1e-12, p)))

    def surprise(self, state_key: str, action_key: str, *, ok: bool) -> float:
        outcome = "ok" if ok else "fail"
        k = (state_key, action_key, outcome)
        k2 = (state_key, action_key)
        tot = float(self.totals.get(k2, 0))
        p = (float(self.counts.get(k, 0)) + 1.0) / (tot + 2.0)
        return float(-math.log(max(1e-12, p)))
