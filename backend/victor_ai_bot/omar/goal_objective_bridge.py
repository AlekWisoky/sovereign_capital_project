from __future__ import annotations

import inspect
from typing import Any, Mapping

from .goal_objective import (
    build_goal_objective_context,
    goal_advancement_reward,
    goal_state_bucket,
)

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def install_goal_objective_bridge() -> None:
    """Install bounded goal shaping on the existing OMAR learner contracts.

    The bridge only enriches learning context/reward. WealthGoalService,
    capital_engine_state(), governance, admission and execution remain the
    authoritative control surfaces.
    """
    try:
        from .real_learning import OmarRealLearner
        from .runtime import OmarRuntime

        state_key_original = getattr(OmarRealLearner, "state_key", None)
        if state_key_original is not None and not getattr(
            state_key_original, "_goal_objective_patched", False
        ):
            def state_key_with_goal(context: Mapping[str, Any]) -> str:
                base = str(state_key_original(context))
                bucket = goal_state_bucket(context)
                return f"{base}|goal:{bucket}"

            state_key_with_goal._goal_objective_patched = True
            OmarRealLearner.state_key = staticmethod(state_key_with_goal)

        observe_original = getattr(OmarRealLearner, "observe", None)
        if observe_original is not None and not getattr(
            observe_original, "_goal_objective_patched", False
        ):
            def observe_with_goal(self: Any, *, state_key: str, action: str, reward: float, outcome: Mapping[str, Any]):
                row = _dict(outcome)
                metadata = _dict(row.get("metadata"))
                goal_context = _dict(metadata.get("goal_objective_context"))
                if goal_context:
                    goal_reward = goal_advancement_reward(
                        context=goal_context,
                        realized_net_usd=float(row.get("realized_net_usd", 0.0) or 0.0),
                        expected_net_usd=float(row.get("expected_net_usd", 0.0) or 0.0),
                        amount_in_wei=int(row.get("amount_in_wei", 0) or 0),
                        drawdown_pct=float(goal_context.get("drawdown_pct", 0.0) or 0.0),
                        truth_verified=bool(row.get("outcome_truth_verified", True)),
                    )
                    weight = _dict(metadata.get("omar_config")).get("goal_objective_weight", 0.35)
                    try:
                        weight = max(0.0, min(1.0, float(weight)))
                    except (TypeError, ValueError):
                        weight = 0.35
                    reward = float(reward) + float(goal_reward) * weight
                    metadata["goal_objective_reward"] = float(goal_reward)
                    metadata["goal_objective_weight"] = float(weight)
                    row["metadata"] = metadata
                return observe_original(
                    self,
                    state_key=state_key,
                    action=action,
                    reward=reward,
                    outcome=row,
                )

            observe_with_goal._goal_objective_patched = True
            OmarRealLearner.observe = observe_with_goal

        runtime_original = getattr(OmarRuntime, "observe_outcome", None)
        if runtime_original is not None and not getattr(
            runtime_original, "_goal_objective_patched", False
        ):
            def observe_outcome_with_goal(self: Any, *, decision_id: str, ok: bool, realized_net_usd: float,
                                          expected_net_usd: float, amount_in_wei: int, gas_cost_usd: float = 0.0,
                                          slippage_bps: float = 0.0, latency_ms: int = 0, route_id: str = "",
                                          tx_hash: str = "", outcome_truth_verified: bool = True,
                                          metadata: Mapping[str, Any] | None = None):
                merged = _dict(metadata)
                try:
                    pending = _dict(getattr(self, "_pending_decisions", {}).get(str(decision_id)))
                    context = _dict(pending.get("context"))
                    if context:
                        merged["goal_objective_context"] = build_goal_objective_context(
                            {"state": context}
                        )
                        merged["goal_objective_context"]["drawdown_pct"] = float(
                            context.get("drawdown_pct", 0.0) or 0.0
                        )
                    merged["omar_config"] = {
                        "goal_objective_weight": float(
                            getattr(getattr(self, "cfg", None), "goal_objective_weight", 0.35)
                        )
                    }
                except _SAFE:
                    pass
                return runtime_original(
                    self,
                    decision_id=decision_id,
                    ok=ok,
                    realized_net_usd=realized_net_usd,
                    expected_net_usd=expected_net_usd,
                    amount_in_wei=amount_in_wei,
                    gas_cost_usd=gas_cost_usd,
                    slippage_bps=slippage_bps,
                    latency_ms=latency_ms,
                    route_id=route_id,
                    tx_hash=tx_hash,
                    outcome_truth_verified=outcome_truth_verified,
                    metadata=merged,
                )

            observe_outcome_with_goal._goal_objective_patched = True
            OmarRuntime.observe_outcome = observe_outcome_with_goal
    except _SAFE:
        return
