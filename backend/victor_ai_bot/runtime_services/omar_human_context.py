from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class OmarHumanContext:
    """Normalized human/AI intent; never a capital or governance authority."""

    aggressiveness_mode: str = "balanced"
    desired_wealth_goal_amount: Optional[float] = None
    desired_wealth_goal_timeframe_days: Optional[int] = None
    ai_recommendation_id: Optional[str] = None
    ai_recommendation_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_human_context(source: Any) -> OmarHumanContext:
    """Normalize optional intent without failing the trading hot path."""
    if source is None:
        return OmarHumanContext()
    raw = source if isinstance(source, dict) else getattr(source, "__dict__", {})
    mode = str(raw.get("aggressiveness_mode", raw.get("aggressiveness", "balanced")) or "balanced").strip().lower()
    if mode not in {"conservative", "balanced", "aggressive"}:
        mode = "balanced"
    amount = raw.get("desired_wealth_goal_amount", raw.get("wealth_goal_amount"))
    try:
        amount = float(amount) if amount is not None else None
    except (TypeError, ValueError):
        amount = None
    if amount is not None and amount < 0:
        amount = None
    timeframe = raw.get("desired_wealth_goal_timeframe_days", raw.get("wealth_goal_timeframe_days"))
    try:
        timeframe = int(timeframe) if timeframe is not None else None
    except (TypeError, ValueError):
        timeframe = None
    if timeframe is not None and timeframe <= 0:
        timeframe = None
    return OmarHumanContext(
        aggressiveness_mode=mode,
        desired_wealth_goal_amount=amount,
        desired_wealth_goal_timeframe_days=timeframe,
        ai_recommendation_id=(str(raw["ai_recommendation_id"]) if raw.get("ai_recommendation_id") else None),
        ai_recommendation_source=(str(raw["ai_recommendation_source"]) if raw.get("ai_recommendation_source") else None),
    )


def learning_features(context: OmarHumanContext, current_wealth: Optional[float] = None) -> Dict[str, float]:
    """Bound human intent into learning features; identifiers remain lineage-only."""
    aggressiveness = {"conservative": -1.0, "balanced": 0.0, "aggressive": 1.0}[context.aggressiveness_mode]
    goal_progress = 0.0
    if context.desired_wealth_goal_amount and current_wealth is not None:
        goal_progress = max(-1.0, min(1.0, float(current_wealth) / context.desired_wealth_goal_amount - 1.0))
    return {
        "human_aggressiveness": aggressiveness,
        "wealth_goal_progress": goal_progress,
        "wealth_goal_amount_present": 1.0 if context.desired_wealth_goal_amount is not None else 0.0,
        "wealth_goal_timeframe_present": 1.0 if context.desired_wealth_goal_timeframe_days is not None else 0.0,
        "ai_recommendation_present": 1.0 if context.ai_recommendation_id else 0.0,
    }
