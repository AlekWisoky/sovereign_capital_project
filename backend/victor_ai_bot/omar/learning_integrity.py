from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping


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


def _capital_context(pending: Mapping[str, Any]) -> dict[str, Any]:
    context = _dict(pending.get("context"))
    metadata = _dict(pending.get("metadata"))
    capital = _dict(context.get("capital_authority"))
    if not capital:
        capital = _dict(metadata.get("capital_authority"))
    if not capital:
        capital = context
    return capital


def validate_learning_transition(
    pending: Mapping[str, Any],
    outcome: Mapping[str, Any],
    *,
    decision_id: str,
) -> LearningIntegrityResult:
    """Authorize a policy update only from a fully attributed canonical settlement.

    This is a learning gate, not an execution/governance gate. It deliberately
    fails closed when lineage, action attribution, settlement truth, or the
    read-only capital authority context is missing.
    """
    did = _text(decision_id)
    correlation = _text(_dict(pending).get("correlation_id"))
    action = _text(_dict(pending).get("action"))
    row = _dict(outcome)

    if not did:
        return LearningIntegrityResult(False, "missing_decision_id", did, correlation, action)
    if not action:
        return LearningIntegrityResult(False, "missing_decision_action", did, correlation, action)
    if not _text(_dict(pending).get("state_key")):
        return LearningIntegrityResult(False, "missing_learning_state_key", did, correlation, action)

    if _text(row.get("status")).lower() != "settled":
        return LearningIntegrityResult(False, "outcome_not_canonically_settled", did, correlation, action)

    lineage = _dict(row.get("canonical_lineage"))
    outcome_did = _text(row.get("decision_id") or lineage.get("decision_id"))
    outcome_corr = _text(row.get("correlation_id") or lineage.get("correlation_id"))
    if outcome_did != did:
        return LearningIntegrityResult(False, "decision_lineage_mismatch", did, correlation, action)
    if not correlation or outcome_corr != correlation:
        return LearningIntegrityResult(False, "correlation_lineage_mismatch", did, correlation, action)

    outcome_action = _text(row.get("action"))
    if outcome_action and outcome_action != action:
        return LearningIntegrityResult(False, "action_attribution_mismatch", did, correlation, action)

    pending_opp = _text(_dict(pending).get("opportunity_id"))
    outcome_opp = _text(row.get("opportunity_id"))
    if pending_opp and outcome_opp and pending_opp != outcome_opp:
        return LearningIntegrityResult(False, "opportunity_lineage_mismatch", did, correlation, action)

    pending_route = _text(_dict(pending).get("route_id"))
    outcome_route = _text(row.get("route_id"))
    if pending_route and outcome_route and pending_route != outcome_route:
        return LearningIntegrityResult(False, "route_attribution_mismatch", did, correlation, action)

    if not bool(row.get("outcome_truth_verified", row.get("truth_verified", False))):
        return LearningIntegrityResult(False, "outcome_truth_unverified", did, correlation, action)

    source = _text(row.get("source"))
    if source != "canonical_outcome_ledger":
        return LearningIntegrityResult(False, "noncanonical_learning_source", did, correlation, action)

    capital = _capital_context(pending)
    if _text(capital.get("capital_authority_source")) != "capital_engine_state":
        return LearningIntegrityResult(False, "capital_authority_not_canonical", did, correlation, action)
    if _text(capital.get("capital_authority_status")).lower() in {"", "unknown", "unavailable"}:
        return LearningIntegrityResult(False, "capital_authority_unavailable", did, correlation, action)
    if _text(capital.get("capital_authority_freshness")).lower() in {"", "unknown", "unavailable"}:
        return LearningIntegrityResult(False, "capital_authority_freshness_unknown", did, correlation, action)

    return LearningIntegrityResult(True, "integrity_verified", did, correlation, action)
