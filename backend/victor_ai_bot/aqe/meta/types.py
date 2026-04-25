from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List
import time


@dataclass
class StrategyCandidate:
    """A proposed strategy mutation.

    Candidates remain additive: runtime applies conservative config overlays while
    structural evolution metadata is recorded for selection, replay, and future
    promotion. Core execution semantics stay unchanged.
    """

    id: str
    created_ts: float
    description: str
    score: float
    settings_patch: Dict[str, Any]
    safety_patch: Dict[str, Any]
    regime: str = "unknown"
    reason: str = ""
    strategy_family: str = "flashloan_atomic"
    lifecycle_stage: str = "experimental"
    parent_ids: List[str] = field(default_factory=list)
    genealogy_depth: int = 0
    regime_tags: List[str] = field(default_factory=list)
    feature_tags: List[str] = field(default_factory=list)
    structure_patch: Dict[str, Any] = field(default_factory=dict)
    mutation_history: List[str] = field(default_factory=list)
    stress_report: Dict[str, Any] = field(default_factory=dict)
    meta_success_probability: float = 0.55
    diversity_bonus: float = 0.0
    correlation_penalty: float = 0.0
    novelty_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["created_iso"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.created_ts))
        return d


@dataclass
class MetaState:
    enabled: bool
    mode: str
    last_tick_ts: float
    last_regime: str
    last_actions: Dict[str, Any]
    last_candidates: List[Dict[str, Any]]
    memory_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "enabled": self.enabled,
            "mode": self.mode,
            "last_tick_ts": self.last_tick_ts,
            "last_regime": self.last_regime,
            "last_actions": self.last_actions,
            "last_candidates": self.last_candidates,
            "memory_summary": self.memory_summary,
        }
