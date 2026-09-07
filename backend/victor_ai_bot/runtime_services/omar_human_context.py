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


def _raw_mapping(source: Any) -> Dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, dict):
        return source
    raw = getattr(source, "__dict__", {})
    return raw if isinstance(raw, dict) else {}


def _normalize_mode(raw: Dict[str, Any]) -> str:
    mode = (
        str(raw.get("aggressiveness_mode", raw.get("aggressiveness", "balanced")) or "balanced")
        .strip()
        .lower()
    )
    return mode if mode in {"conservative", "balanced", "aggressive"} else "balanced"


def _normalize_amount(raw: Dict[str, Any]) -> Optional[float]:
    value = raw.get("desired_wealth_goal_amount", raw.get("wealth_goal_amount"))
    try:
        amount = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return amount if amount is None or amount >= 0 else None


def _normalize_timeframe(raw: Dict[str, Any]) -> Optional[int]:
    value = raw.get(
        "desired_wealth_goal_timeframe_days",
        raw.get("wealth_goal_timeframe_days"),
    )
    try:
        timeframe = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return timeframe if timeframe is None or timeframe > 0 else None


def _optional_text(raw: Dict[str, Any], key: str) -> Optional[str]:
    value = raw.get(key)
    return str(value) if value else None


def normalize_human_context(source: Any) -> OmarHumanContext:
    """Normalize optional intent without failing the trading hot path."""
    raw = _raw_mapping(source)
    return OmarHumanContext(
        aggressiveness_mode=_normalize_mode(raw),
        desired_wealth_goal_amount=_normalize_amount(raw),
        desired_wealth_goal_timeframe_days=_normalize_timeframe(raw),
        ai_recommendation_id=_optional_text(raw, "ai_recommendation_id"),
        ai_recommendation_source=_optional_text(raw, "ai_recommendation_source"),
    )


def learning_features(
    context: OmarHumanContext, current_wealth: Optional[float] = None
) -> Dict[str, float]:
    """Bound human intent into learning features; identifiers remain lineage-only."""
    aggressiveness = {
        "conservative": -1.0,
        "balanced": 0.0,
        "aggressive": 1.0,
    }[context.aggressiveness_mode]
    goal_progress = 0.0
    if context.desired_wealth_goal_amount and current_wealth is not None:
        goal_progress = max(
            -1.0,
            min(
                1.0,
                float(current_wealth) / context.desired_wealth_goal_amount - 1.0,
            ),
        )
    return {
        "human_aggressiveness": aggressiveness,
        "wealth_goal_progress": goal_progress,
        "wealth_goal_amount_present": (
            1.0 if context.desired_wealth_goal_amount is not None else 0.0
        ),
        "wealth_goal_timeframe_present": (
            1.0 if context.desired_wealth_goal_timeframe_days is not None else 0.0
        ),
        "ai_recommendation_present": 1.0 if context.ai_recommendation_id else 0.0,
    }
