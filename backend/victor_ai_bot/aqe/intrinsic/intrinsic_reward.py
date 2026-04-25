from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .rnd import RND
from .visitation import VisitationCounter
from .curiosity import TransitionCuriosity


@dataclass
class IntrinsicConfig:
    beta: float = 0.15
    rnd_weight: float = 0.50
    visit_weight: float = 0.35
    surprise_weight: float = 0.15


class IntrinsicReward:
    """Intrinsic reward module (Phase 2).

    Combines:
    - RND novelty
    - visitation count novelty
    - transition surprise (outcome prediction)

    Returns both a scalar reward and a breakdown for observability.
    """

    def __init__(self, *, cfg: IntrinsicConfig | None = None):
        self.cfg = cfg or IntrinsicConfig()
        self.rnd = RND()
        self.visits = VisitationCounter()
        self.curiosity = TransitionCuriosity()

    def observe_state(self, state_key: str) -> Dict[str, Any]:
        c = self.visits.observe(state_key)
        rnd = self.rnd.novelty(state_key, train=True)
        visit = self.visits.novelty(state_key)
        return {
            "count": int(c),
            "rnd": float(rnd),
            "visit": float(visit),
            "entropy": float(self.visits.entropy()),
        }

    def observe_outcome(self, state_key: str, action_key: str, *, ok: bool) -> Dict[str, Any]:
        surprise = self.curiosity.observe(state_key, action_key, ok=ok)
        return {"surprise": float(surprise)}

    def intrinsic(self, *, state_key: str, action_key: str | None = None, ok: bool | None = None) -> Dict[str, Any]:
        st = self.observe_state(state_key)
        surprise = 0.0
        if action_key is not None and ok is not None:
            surprise = float(self.curiosity.surprise(state_key, action_key, ok=bool(ok)))
        r = (
            float(self.cfg.rnd_weight) * float(st.get("rnd", 0.0))
            + float(self.cfg.visit_weight) * float(st.get("visit", 0.0))
            + float(self.cfg.surprise_weight) * float(surprise)
        )
        return {"r_intrinsic": float(r), "components": {**st, "surprise": float(surprise)}}

    def combine(self, *, r_team: float, r_intrinsic: float) -> float:
        return float(r_team) + float(self.cfg.beta) * float(r_intrinsic)
