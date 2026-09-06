from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

from .goal_advancement import evaluate_goal_advancement
from .oos_evidence import oos_evidence_path
from .oos_lineage_integrity import filter_integrity_valid_oos_rows
from .performance_promotion import (
    PerformancePromotionResult,
    PerformancePromotionThresholds,
    evaluate_performance_promotion,
)


def _events_from_jsonl(path: str) -> Iterable[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(row, dict) and row.get("event") == "omar_oos_evidence":
                    yield row
    except OSError:
        return


def _valid_oos_rows(runtime: Any) -> tuple[list[Mapping[str, Any]], Any]:
    return filter_integrity_valid_oos_rows(_events_from_jsonl(performance_evaluation_path(runtime)))


def performance_evaluation_path(runtime: Any) -> str:
    """Return the single canonical OOS evidence stream for this runtime."""
    return oos_evidence_path(runtime)


def performance_promotion(
    runtime: Any,
    thresholds: PerformancePromotionThresholds | None = None,
) -> PerformancePromotionResult:
    """Evaluate promotion only from canonical OOS evidence with complete lineage.

    Incomplete evidence is excluded from the performance sample. Consequently,
    missing lineage reduces the observation count and fails closed through the
    existing minimum-observation threshold instead of being treated as neutral
    or successful evidence.
    """
    cfg = thresholds or PerformancePromotionThresholds(
        min_evaluation_observations=int(getattr(runtime.cfg, "performance_min_evaluation_observations", 50)),
        min_unique_states=int(getattr(runtime.cfg, "performance_min_unique_states", 10)),
        min_mean_advantage_usd=float(getattr(runtime.cfg, "performance_min_mean_advantage_usd", 0.0)),
        min_mean_advantage_bps=float(getattr(runtime.cfg, "performance_min_mean_advantage_bps", 5.0)),
        min_win_rate=float(getattr(runtime.cfg, "performance_min_win_rate", 0.55)),
        min_lower_confidence_advantage_usd=float(
            getattr(runtime.cfg, "performance_min_lower_confidence_advantage_usd", 0.0)
        ),
    )
    rows, _integrity = _valid_oos_rows(runtime)
    return evaluate_performance_promotion(rows, thresholds=cfg)


def _goal_state(runtime: Any) -> Mapping[str, Any]:
    """Read the canonical wealth-goal state without creating a second goal authority."""
    service = getattr(runtime, "_wealth_goal_service", None)
    if service is None or not hasattr(service, "state"):
        return {}
    try:
        state = service.state(runtime)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return {}
    if not isinstance(state, Mapping):
        return {}
    value = state.get("state")
    return dict(value) if isinstance(value, Mapping) else {}


def live_performance_promotion(runtime: Any) -> dict[str, Any]:
    rows, integrity = _valid_oos_rows(runtime)
    result = performance_promotion(runtime)
    payload = result.to_dict()
    payload["oos_lineage_integrity"] = integrity.to_dict()
    payload["oos_evidence_rows"] = len(rows)
    payload["source"] = "omar_canonical_oos_evidence_stream"
    payload["promotion_allowed"] = bool(result.ready and integrity.ready)
    if not payload["promotion_allowed"] and integrity.rejected_rows:
        payload["reason"] = "incomplete_oos_lineage"

    # Goal advancement is deliberately downstream of the same performance gate.
    # A completed wealth goal can be recorded, but the next goal is not promoted
    # unless the learned policy also has verified OOS advantage and healthy
    # execution/risk economics. This prevents goal pressure from becoming a
    # hidden source of trading aggressiveness.
    goal_advancement = evaluate_goal_advancement(_goal_state(runtime), payload)
    payload["goal_advancement"] = goal_advancement.to_dict()
    payload["goal_advancement_allowed"] = bool(goal_advancement.allowed)
    return payload
