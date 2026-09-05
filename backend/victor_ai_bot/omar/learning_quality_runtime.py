from __future__ import annotations

import json
import os
from typing import Any, Iterable, Mapping

from .learning_quality import (
    LearningQualityResult,
    LearningQualityThresholds,
    evaluate_learning_quality,
)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _events_from_jsonl(path: str) -> Iterable[dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(row, dict) or row.get("event") != "omar_real_outcome":
                    continue
                outcome = _dict(row.get("outcome"))
                metadata = _dict(outcome.get("metadata"))
                lineage = _dict(metadata.get("canonical_lineage"))
                yield {
                    "decision_id": _text(
                        row.get("decision_id")
                        or outcome.get("decision_id")
                        or lineage.get("decision_id")
                    ),
                    "correlation_id": _text(
                        row.get("correlation_id")
                        or outcome.get("correlation_id")
                        or lineage.get("correlation_id")
                    ),
                    "state_key": _text(row.get("state_key")),
                    "action": _text(row.get("action")),
                    "reward": row.get("reward"),
                    "outcome_truth_verified": bool(outcome.get("outcome_truth_verified", False)),
                    "tx_hash": _text(outcome.get("tx_hash")),
                }
    except OSError:
        return


def learning_quality(
    runtime: Any,
    thresholds: LearningQualityThresholds | None = None,
) -> LearningQualityResult:
    """Evaluate the durable real-learning event stream used by this runtime.

    The learner JSONL is append-only evidence produced by ``observe_outcome``;
    callers do not get to mark an event as settled merely by supplying a receipt.
    The lifecycle bridge only calls this after canonical settlement attribution.
    """
    learner = getattr(runtime, "_real_learner", None)
    path = _text(getattr(learner, "path", ""))
    if not path:
        base_data_dir = str(os.environ.get("VICTOR_DATA_DIR", "data") or "data")
        path = os.path.join(
            base_data_dir,
            "superstructure",
            "omar_learning",
            f"real_policy_{getattr(runtime, 'chain_name', 'default')}.json",
        )
    return evaluate_learning_quality(_events_from_jsonl(path + ".jsonl"), thresholds=thresholds)


def live_influence_quality(
    runtime: Any,
    thresholds: LearningQualityThresholds | None = None,
) -> dict[str, Any]:
    """Stable runtime-facing quality contract for live OMAR influence."""
    result = learning_quality(runtime, thresholds=thresholds)
    payload = result.to_dict()
    payload["source"] = "omar_real_learning_event_stream"
    payload["live_influence_allowed"] = bool(result.ready)
    return payload
