from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


_REQUIRED = (
    "decision_id",
    "correlation_id",
    "execution_record_id",
    "outcome_id",
    "action",
    "state_key",
    "policy_revision",
    "settled_at",
    "settlement_source",
    "settlement_truth_verified",
)


@dataclass(frozen=True)
class OosEvidence:
    """Immutable evidence row consumed by the independent OOS gate.

    The producer records observed canonical settlement lineage and explicit
    candidate/baseline realized rewards. It never updates policy, infers a
    baseline, or treats a receipt as settlement by itself.
    """

    evidence_id: str
    evaluation_split: str
    decision_id: str
    correlation_id: str
    execution_record_id: str
    outcome_id: str
    action: str
    state_key: str
    policy_revision: str
    settled_at: str
    settlement_source: str
    settlement_truth_verified: bool
    candidate_reward_usd: float
    baseline_reward_usd: float
    advantage_usd: float
    advantage_bps: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OosEvidenceError(ValueError):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _finite_number(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise OosEvidenceError(f"invalid_{field}") from exc
    if not math.isfinite(result):
        raise OosEvidenceError(f"nonfinite_{field}")
    return result


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _evidence_id(row: Mapping[str, Any]) -> str:
    material = {
        "decision_id": _text(row["decision_id"]),
        "correlation_id": _text(row["correlation_id"]),
        "execution_record_id": _text(row["execution_record_id"]),
        "outcome_id": _text(row["outcome_id"]),
        "action": _text(row["action"]),
        "policy_revision": _text(row["policy_revision"]),
        "candidate_reward_usd": float(row["candidate_reward_usd"]),
        "baseline_reward_usd": float(row["baseline_reward_usd"]),
    }
    return "oos-" + hashlib.sha256(_canonical_json(material).encode("utf-8")).hexdigest()


def produce_oos_evidence(
    settled_outcomes: Iterable[Mapping[str, Any]],
    *,
    evaluation_split: str = "out_of_sample",
) -> list[dict[str, Any]]:
    """Produce canonical OOS evidence from already-settled outcome records.

    OOS membership is explicit; this function deliberately does not derive a
    train/test split from reward, action, timestamp, or performance. The caller
    must provide canonical settled records with an explicit candidate and
    incumbent/baseline realized reward.
    """
    split = _text(evaluation_split)
    if split not in {"out_of_sample", "oos"}:
        raise OosEvidenceError("invalid_evaluation_split")

    produced: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in settled_outcomes:
        if not isinstance(row, Mapping):
            continue
        missing = [field for field in _REQUIRED if not _text(row.get(field))]
        if missing:
            raise OosEvidenceError("missing_canonical_fields:" + ",".join(missing))
        if _text(row.get("settlement_source")) != "canonical_outcome_ledger":
            raise OosEvidenceError("noncanonical_settlement_source")
        if row.get("settlement_truth_verified") is not True:
            raise OosEvidenceError("unverified_settlement_truth")

        candidate = _finite_number(row.get("candidate_reward_usd"), "candidate_reward_usd")
        baseline = _finite_number(row.get("baseline_reward_usd"), "baseline_reward_usd")
        advantage = candidate - baseline
        advantage_bps = advantage / max(abs(baseline), 1e-9) * 10_000.0
        if not math.isfinite(advantage_bps):
            raise OosEvidenceError("nonfinite_advantage_bps")

        evidence = OosEvidence(
            evidence_id=_evidence_id({**row, "candidate_reward_usd": candidate, "baseline_reward_usd": baseline}),
            evaluation_split=split,
            decision_id=_text(row["decision_id"]),
            correlation_id=_text(row["correlation_id"]),
            execution_record_id=_text(row["execution_record_id"]),
            outcome_id=_text(row["outcome_id"]),
            action=_text(row["action"]),
            state_key=_text(row["state_key"]),
            policy_revision=_text(row["policy_revision"]),
            settled_at=_text(row["settled_at"]),
            settlement_source=_text(row["settlement_source"]),
            settlement_truth_verified=True,
            candidate_reward_usd=candidate,
            baseline_reward_usd=baseline,
            advantage_usd=advantage,
            advantage_bps=advantage_bps,
        )
        if evidence.evidence_id in seen:
            raise OosEvidenceError("duplicate_oos_evidence_identity")
        seen.add(evidence.evidence_id)
        produced.append(evidence.to_dict())
    return produced
