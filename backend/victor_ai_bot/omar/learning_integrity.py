from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping

CANONICAL_SETTLEMENT_SOURCES = frozenset(
    {"canonical_outcome_ledger", "phase2_canonical_outcome_ledger"}
)


@dataclass(frozen=True)
class LearningIntegrityResult:
    allowed: bool
    reason: str
    decision_id: str
    correlation_id: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _pending_sizing_id(pending: Mapping[str, Any]) -> str:
    p = _dict(pending)
    lineage = _dict(p.get("canonical_lineage"))
    direct = _text(p.get("sizing_id") or lineage.get("sizing_id"))
    if direct:
        return direct
    admission = _dict(p.get("capital_admission"))
    details = _dict(admission.get("details"))
    institutional = _dict(details.get("institutionalSizing"))
    sizing = _dict(institutional.get("sizing"))
    return _text(sizing.get("sizing_id"))


def validate_learning_transition(
    pending: Mapping[str, Any], outcome: Mapping[str, Any], *, decision_id: str
) -> LearningIntegrityResult:
    """Fail closed until settlement is physically and exactly attributed."""
    p = _dict(pending)
    row = _dict(outcome)
    did = _text(decision_id)
    correlation = _text(p.get("correlation_id"))
    action = _text(p.get("action"))
    if not did:
        return LearningIntegrityResult(False, "missing_decision_id", did, correlation, action)
    if not action:
        return LearningIntegrityResult(False, "missing_decision_action", did, correlation, action)
    if not _text(p.get("state_key")):
        return LearningIntegrityResult(False, "missing_learning_state_key", did, correlation, action)
    if _text(row.get("status")).lower() != "settled":
        return LearningIntegrityResult(False, "outcome_not_canonically_settled", did, correlation, action)
    lineage = _dict(row.get("canonical_lineage"))
    if _text(row.get("decision_id") or lineage.get("decision_id")) != did:
        return LearningIntegrityResult(False, "decision_lineage_mismatch", did, correlation, action)
    if not correlation or _text(row.get("correlation_id") or lineage.get("correlation_id")) != correlation:
        return LearningIntegrityResult(False, "correlation_lineage_mismatch", did, correlation, action)
    if _text(row.get("action") or lineage.get("action")) != action:
        return LearningIntegrityResult(False, "action_attribution_mismatch", did, correlation, action)
    for field in ("execution_id", "outcome_id", "sizing_id", "opportunity_id", "route_id"):
        if not _text(row.get(field) or lineage.get(field)):
            return LearningIntegrityResult(False, f"missing_{field}", did, correlation, action)

    pending_sizing = _pending_sizing_id(p)
    outcome_sizing = _text(row.get("sizing_id") or lineage.get("sizing_id"))
    if pending_sizing and pending_sizing != outcome_sizing:
        return LearningIntegrityResult(False, "sizing_lineage_mismatch", did, correlation, action)

    if _text(p.get("opportunity_id")) != _text(
        row.get("opportunity_id") or lineage.get("opportunity_id")
    ):
        return LearningIntegrityResult(False, "opportunity_lineage_mismatch", did, correlation, action)
    if _text(p.get("route_id")) != _text(row.get("route_id") or lineage.get("route_id")):
        return LearningIntegrityResult(False, "route_attribution_mismatch", did, correlation, action)
    if not bool(
        row.get("settlement_verified", row.get("truth_verified", row.get("outcome_truth_verified", False)))
    ):
        return LearningIntegrityResult(False, "settlement_unverified", did, correlation, action)
    if _text(row.get("source")) not in CANONICAL_SETTLEMENT_SOURCES:
        return LearningIntegrityResult(False, "noncanonical_learning_source", did, correlation, action)
    if not _finite_number(p.get("expected_net_usd")):
        return LearningIntegrityResult(False, "missing_or_invalid_expected_net", did, correlation, action)
    if not _finite_number(row.get("realized_net_usd")):
        return LearningIntegrityResult(False, "missing_or_invalid_realized_net", did, correlation, action)
    if not _finite_number(row.get("expected_net_usd")):
        return LearningIntegrityResult(False, "missing_or_invalid_settlement_expected_net", did, correlation, action)
    if float(row["expected_net_usd"]) != float(p["expected_net_usd"]):
        return LearningIntegrityResult(False, "expected_net_attribution_mismatch", did, correlation, action)
    if not _finite_number(row.get("expectation_error")):
        return LearningIntegrityResult(False, "missing_or_invalid_expectation_error", did, correlation, action)
    expected = float(p["expected_net_usd"])
    realized = float(row["realized_net_usd"])
    if float(row["expectation_error"]) != realized - expected:
        return LearningIntegrityResult(False, "expectation_error_mismatch", did, correlation, action)
    context = _dict(p.get("context"))
    capital = _dict(context.get("capital_authority")) or context
    if _text(capital.get("capital_authority_source")) != "capital_engine_state":
        return LearningIntegrityResult(False, "capital_authority_not_canonical", did, correlation, action)
    if _text(capital.get("capital_authority_status")).lower() in {"", "unknown", "unavailable"}:
        return LearningIntegrityResult(False, "capital_authority_unavailable", did, correlation, action)
    if _text(capital.get("capital_authority_freshness")).lower() in {"", "unknown", "unavailable"}:
        return LearningIntegrityResult(False, "capital_authority_freshness_unknown", did, correlation, action)
    return LearningIntegrityResult(True, "integrity_verified", did, correlation, action)
