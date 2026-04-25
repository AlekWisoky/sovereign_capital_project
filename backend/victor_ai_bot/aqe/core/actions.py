from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class ActionSpec:
    """A normalized action spec for execution.

    We keep this intentionally close to `victor_ai_bot.rl_policy.Action` so the
    existing execution pipeline can remain unchanged.
    """

    size_mult: float = 1.0
    borrow_mult: float = 1.0
    gas_mode: str = "standard"  # standard|fast|instant

    def key(self) -> str:
        # Stable key used by multi-agent aggregation.
        return f"{self.gas_mode}|{self.size_mult:.4f}|{self.borrow_mult:.4f}"


def actions_from_rl() -> List[ActionSpec]:
    """Import RL action space (if available) and convert it.

    This keeps backward compatibility: if RL actions change, AQE sees them.
    """
    try:
        from victor_ai_bot.rl_policy import RlPolicy

        RlPolicy.ensure_actions()
        out: List[ActionSpec] = []
        for a in RlPolicy.ACTIONS:
            out.append(
                ActionSpec(
                    size_mult=float(a.size_mult),
                    borrow_mult=float(getattr(a, "borrow_mult", 1.0)),
                    gas_mode=str(a.gas_mode),
                )
            )
        return out
    except (AttributeError, ImportError, ModuleNotFoundError, TypeError, ValueError):
        # Safe fallback: minimal action set.
        return [
            ActionSpec(1.0, 1.0, "standard"),
            ActionSpec(0.75, 1.0, "standard"),
            ActionSpec(0.5, 1.0, "standard"),
            ActionSpec(1.0, 1.0, "fast"),
        ]


def normalize_dist(dist: Dict[str, float], *, eps: float = 1e-12) -> Dict[str, float]:
    s = float(sum(max(0.0, float(v)) for v in dist.values()))
    if s <= eps:
        # Uniform if empty/invalid.
        n = max(1, len(dist))
        return {k: 1.0 / n for k in dist.keys()}
    return {k: max(0.0, float(v)) / s for k, v in dist.items()}


def dist_for_action(action: ActionSpec, actions: List[ActionSpec], *, p: float = 0.92) -> Dict[str, float]:
    """Create a peaked distribution around a chosen action."""
    keys = [a.key() for a in actions]
    out = {k: (1.0 - p) / max(1, len(keys) - 1) for k in keys}
    out[action.key()] = p
    return normalize_dist(out)


def to_action_spec(action_key: str, actions: List[ActionSpec]) -> ActionSpec:
    for a in actions:
        if a.key() == action_key:
            return a
    return actions[0] if actions else ActionSpec()
