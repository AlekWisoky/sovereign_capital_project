from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

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
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def performance_evaluation_path(runtime: Any) -> str:
    learner = getattr(runtime, "_real_learner", None)
    learner_path = str(getattr(learner, "path", "") or "")
    if learner_path:
        return os.path.join(os.path.dirname(learner_path), f"performance_{getattr(runtime, 'chain_name', 'default')}.jsonl")
    base_data_dir = str(os.environ.get("VICTOR_DATA_DIR", "data") or "data")
    return os.path.join(
        base_data_dir,
        "superstructure",
        "omar_learning",
        f"performance_{getattr(runtime, 'chain_name', 'default')}.jsonl",
    )


def performance_promotion(
    runtime: Any,
    thresholds: PerformancePromotionThresholds | None = None,
) -> PerformancePromotionResult:
    """Stable runtime-facing contract for policy performance promotion."""
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
    return evaluate_performance_promotion(
        _events_from_jsonl(performance_evaluation_path(runtime)),
        thresholds=cfg,
    )


def live_performance_promotion(runtime: Any) -> dict[str, Any]:
    result = performance_promotion(runtime)
    payload = result.to_dict()
    payload["source"] = "omar_out_of_sample_performance_event_stream"
    payload["promotion_allowed"] = bool(result.ready)
    return payload
