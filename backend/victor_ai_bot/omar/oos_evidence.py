from __future__ import annotations

import json
import os
import time
from math import isfinite
from typing import Any, Mapping


OOS_SPLITS = {"out_of_sample", "oos"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def oos_evidence_path(runtime: Any) -> str:
    base = str(getattr(runtime, "data_dir", "data/superstructure") or "data/superstructure")
    return os.path.join(
        base,
        "omar_learning",
        f"oos_evidence_{getattr(runtime, 'chain_name', 'default')}.jsonl",
    )


def record_oos_evidence(
    runtime: Any,
    *,
    decision_id: str,
    correlation_id: str,
    opportunity_id: str,
    route_id: str,
    state_key: str,
    action: str,
    candidate_reward_usd: float,
    baseline_reward_usd: float | None,
    evaluation_split: str,
    outcome_id: str = "",
    execution_id: str = "",
    tx_hash: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one canonical, independently attributable OOS evaluation record.

    This producer never invents a baseline. An OOS record is emitted only when
    the decision was explicitly marked for an OOS evaluation and an independent
    realized baseline reward is supplied by the evaluation surface.
    """
    split = _text(evaluation_split).lower()
    candidate = _number(candidate_reward_usd)
    baseline = _number(baseline_reward_usd)
    if split not in OOS_SPLITS:
        return {"ok": False, "reason": "not_oos_evaluation"}
    if candidate is None or baseline is None:
        return {"ok": False, "reason": "missing_realized_baseline"}

    row = {
        "event": "omar_oos_evidence",
        "ts_ms": int(time.time() * 1000),
        "evaluation_split": "out_of_sample",
        "decision_id": _text(decision_id),
        "correlation_id": _text(correlation_id),
        "opportunity_id": _text(opportunity_id),
        "route_id": _text(route_id),
        "state_key": _text(state_key),
        "action": _text(action),
        "outcome_id": _text(outcome_id),
        "execution_id": _text(execution_id),
        "tx_hash": _text(tx_hash),
        "candidate_reward_usd": float(candidate),
        "baseline_reward_usd": float(baseline),
        "metadata": dict(metadata or {}),
    }
    path = oos_evidence_path(runtime)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError):
        return {"ok": False, "reason": "oos_evidence_write_failed", "path": path}
    return {"ok": True, "path": path, "record": row}
