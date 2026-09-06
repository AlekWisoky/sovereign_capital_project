from __future__ import annotations

from typing import Any, Mapping

from .promotion import PromotionBoundary, PromotionDecision
from .real_learning import ACTIONS, OmarRecommendation


def _candidate_snapshot(learner: Any) -> dict[str, Any]:
    q = getattr(learner, "q", {})
    n = getattr(learner, "n", {})
    return {
        "q": {str(state): {str(action): float(value) for action, value in values.items()} for state, values in q.items() if isinstance(values, Mapping)},
        "n": {str(state): int(value) for state, value in n.items()},
        "total_observations": int(getattr(learner, "total_observations", 0)),
        "learner_schema": 1,
    }


def _recommend_from_snapshot(learner: Any, context: Mapping[str, Any], snapshot: Mapping[str, Any], version: str) -> OmarRecommendation:
    state_key = learner.state_key(context)
    q_root = snapshot.get("q") if isinstance(snapshot, Mapping) else {}
    values = q_root.get(state_key) if isinstance(q_root, Mapping) else None
    if not isinstance(values, Mapping):
        return OmarRecommendation(state_key, "UNTRAINED", 0.0, False, 1.0, "standard", False, 0, "promoted_policy_no_state")
    ranked = sorted(((str(action), float(value)) for action, value in values.items() if str(action) in ACTIONS), key=lambda item: (-item[1], item[0]))
    if not ranked:
        return OmarRecommendation(state_key, "UNTRAINED", 0.0, False, 1.0, "standard", False, 0, "promoted_policy_empty_state")
    action, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = max(0.5, min(0.99, 0.5 + abs(top - second) * 0.05))
    observations = int((snapshot.get("n") or {}).get(state_key, 0)) if isinstance(snapshot.get("n"), Mapping) else 0
    if action in {"WAIT", "DEFEND"}:
        veto, size_mult, reason = True, 0.0, "promoted_defensive_action"
    elif action == "DECREASE_RISK":
        veto, size_mult, reason = False, 0.75, "promoted_size_reduction"
    else:
        veto, size_mult, reason = False, 1.0, "promoted_policy_action"
    gas_mode = "fast" if action == "SEEK_OPP" else "standard"
    return OmarRecommendation(state_key, action, confidence, veto, size_mult, gas_mode, True, observations, f"{reason}:{version}")


def install_promotion_runtime_hooks() -> None:
    """Attach the promotion boundary to the existing OMAR runtime contract."""
    from .runtime import OmarRuntime

    if getattr(OmarRuntime, "_omar_promotion_hooked", False):
        return
    original_recommend = OmarRuntime.recommend
    original_state = OmarRuntime.state

    def _boundary(self: Any) -> PromotionBoundary:
        boundary = getattr(self, "_promotion_boundary", None)
        if boundary is None:
            path = getattr(self, "promotion_path", None)
            if not path:
                path = f"{getattr(self, 'data_dir', 'data/superstructure')}/omar_learning/promotion_{getattr(self, 'chain_name', 'default')}.json"
            boundary = PromotionBoundary(path)
            self._promotion_boundary = boundary
        return boundary

    def recommend(self: Any, context: Mapping[str, Any]):
        boundary = _boundary(self)
        if not bool(getattr(self, "enabled", False)):
            return original_recommend(self, context)
        if boundary.active_version == "baseline-v0":
            return OmarRecommendation("", "UNTRAINED", 0.0, False, 1.0, "standard", False, 0, "no_promoted_policy")
        learner = getattr(self, "_real_learner", None)
        snapshot = boundary.active_snapshot()
        if learner is None or snapshot is None:
            return OmarRecommendation("", "UNAVAILABLE", 0.0, False, 1.0, "standard", False, 0, "promoted_policy_unavailable")
        rec = _recommend_from_snapshot(learner, context, snapshot, boundary.active_version)
        self.last_decision = rec.to_dict()
        return rec

    def state(self: Any):
        result = dict(original_state(self))
        result["promotion"] = _boundary(self).state()
        return result

    def prepare_candidate(self: Any) -> str:
        learner = getattr(self, "_real_learner", None)
        if learner is None:
            raise RuntimeError("real_learner_unavailable")
        boundary = _boundary(self)
        return boundary.register_candidate(_candidate_snapshot(learner), source_observations=int(getattr(learner, "total_observations", 0)))

    def evaluate_candidate_oos(self: Any, candidate_version: str, events: list[Mapping[str, Any]]) -> PromotionDecision:
        return _boundary(self).evaluate(candidate_version, events)

    def promote_candidate(self: Any, candidate_version: str, events: list[Mapping[str, Any]]) -> dict[str, Any]:
        decision = _boundary(self).evaluate(candidate_version, events)
        if not decision.ready:
            return {"ok": False, "decision": decision.to_dict()}
        policy = _boundary(self).promote(decision)
        return {"ok": True, "decision": decision.to_dict(), "policy": policy.to_dict()}

    OmarRuntime.recommend = recommend
    OmarRuntime.state = state
    OmarRuntime.prepare_candidate = prepare_candidate
    OmarRuntime.evaluate_candidate_oos = evaluate_candidate_oos
    OmarRuntime.promote_candidate = promote_candidate
    OmarRuntime._omar_promotion_hooked = True
