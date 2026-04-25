from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict


@dataclass
class VisitationCounter:
    """Simple state visitation counter for intrinsic rewards."""

    def __post_init__(self):
        self.counts: Dict[str, int] = {}
        self.total: int = 0

    def observe(self, state_key: str) -> int:
        c = int(self.counts.get(state_key, 0)) + 1
        self.counts[state_key] = c
        self.total += 1
        return c

    def novelty(self, state_key: str) -> float:
        c = int(self.counts.get(state_key, 0))
        # high novelty on first visits, decays as 1/sqrt(n)
        return float(1.0 / math.sqrt(max(1, c)))

    def entropy(self) -> float:
        if self.total <= 0:
            return 0.0
        h = 0.0
        for c in self.counts.values():
            p = float(c) / float(self.total)
            if p > 1e-12:
                h -= p * math.log(p)
        return float(h)
