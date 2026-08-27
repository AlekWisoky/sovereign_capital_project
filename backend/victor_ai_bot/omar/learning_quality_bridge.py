from __future__ import annotations

from typing import Any

from .learning_quality import LearningQualityThresholds
from .learning_quality_runtime import live_influence_quality
from .real_learning import OmarRecommendation

_SAFE = (AttributeError, RuntimeError, TypeError, ValueError)


def install_learning_quality_runtime_hooks() -> None:
    """Expose Gate B through OmarRuntime and block unqualified live influence."""
    from .runtime import OmarRuntime

    if getattr(OmarRuntime, "_learning_quality_hooks_installed", False):
        return

    original_state = getattr(OmarRuntime, "state")
    original_recommend = getattr(OmarRuntime, "recommend")

    def quality(self: Any) -> dict[str, Any]:
        try:
            return live_influence_quality(self)
        except _SAFE as exc:
            return {
                "ready": False,
                "reason": f"quality_evaluation_error:{type(exc).__name__}",
                "observations": 0,
                "unique_states": 0,
                "action_coverage": 0.0,
                "truth_rate": 0.0,
                "missing_lineage_rate": 1.0,
                "duplicate_rate": 0.0,
                "invalid_reward_count": 0,
                "failures": ["quality_evaluation_error"],
                "source": "omar_real_learning_event_stream",
                "live_influence_allowed": False,
            }

    def state(self: Any) -> dict[str, Any]:
        payload = dict(original_state(self))
        payload["learning_quality"] = quality(self)
        return payload

    def recommend(self: Any, context: Any) -> OmarRecommendation:
        rec = original_recommend(self, context)
        if not bool(getattr(rec, "trained", False)):
            return rec
        gate = quality(self)
        if bool(gate.get("ready", False)):
            return rec
        return OmarRecommendation(
            state_key=str(getattr(rec, "state_key", "") or ""),
            action="UNTRAINED",
            confidence=0.0,
            veto=False,
            size_mult=1.0,
            gas_mode="standard",
            trained=False,
            observations=int(gate.get("observations", 0) or 0),
            reason=f"learning_quality_gate:{gate.get('reason', 'not_ready')}",
        )

    OmarRuntime.learning_quality = quality
    OmarRuntime.state = state
    OmarRuntime.recommend = recommend
    OmarRuntime._learning_quality_hooks_installed = True
