from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class OOSLineageIntegrity:
    total_rows: int
    valid_rows: int
    rejected_rows: int
    missing_decision_id: int
    missing_correlation_id: int
    missing_execution_id: int
    missing_outcome_id: int
    missing_state_key: int
    missing_action: int

    @property
    def coverage(self) -> float:
        if self.total_rows <= 0:
            return 0.0
        return float(self.valid_rows / self.total_rows)

    @property
    def ready(self) -> bool:
        return self.total_rows > 0 and self.rejected_rows == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "rejected_rows": self.rejected_rows,
            "coverage": self.coverage,
            "ready": self.ready,
            "missing_decision_id": self.missing_decision_id,
            "missing_correlation_id": self.missing_correlation_id,
            "missing_execution_id": self.missing_execution_id,
            "missing_outcome_id": self.missing_outcome_id,
            "missing_state_key": self.missing_state_key,
            "missing_action": self.missing_action,
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lineage(row: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("canonical_lineage", "lineage"):
        value = row.get(key)
        if isinstance(value, Mapping):
            return value
    metadata = row.get("metadata")
    if isinstance(metadata, Mapping):
        for key in ("canonical_lineage", "lineage"):
            value = metadata.get(key)
            if isinstance(value, Mapping):
                return value
    return {}


def _value(row: Mapping[str, Any], lineage: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if _text(value):
            return _text(value)
        value = lineage.get(key)
        if _text(value):
            return _text(value)
    return ""


def validate_oos_lineage(row: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Validate the identity required before OOS evidence can promote a policy."""
    lineage = _lineage(row)
    missing: list[str] = []
    if not _value(row, lineage, "decision_id"):
        missing.append("decision_id")
    if not _value(row, lineage, "correlation_id"):
        missing.append("correlation_id")
    if not _value(row, lineage, "execution_id", "execution_record_id"):
        missing.append("execution_id")
    if not _value(row, lineage, "outcome_id", "settled_outcome_id"):
        missing.append("outcome_id")
    if not _text(row.get("state_key")):
        missing.append("state_key")
    if not _text(row.get("action")):
        missing.append("action")
    return not missing, tuple(missing)


def filter_integrity_valid_oos_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], OOSLineageIntegrity]:
    valid: list[Mapping[str, Any]] = []
    total = rejected = 0
    counts = {key: 0 for key in ("decision_id", "correlation_id", "execution_id", "outcome_id", "state_key", "action")}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        total += 1
        ok, missing = validate_oos_lineage(row)
        if ok:
            valid.append(row)
            continue
        rejected += 1
        for key in missing:
            counts[key] += 1
    report = OOSLineageIntegrity(
        total_rows=total,
        valid_rows=len(valid),
        rejected_rows=rejected,
        missing_decision_id=counts["decision_id"],
        missing_correlation_id=counts["correlation_id"],
        missing_execution_id=counts["execution_id"],
        missing_outcome_id=counts["outcome_id"],
        missing_state_key=counts["state_key"],
        missing_action=counts["action"],
    )
    return valid, report
