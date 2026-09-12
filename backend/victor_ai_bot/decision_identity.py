from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4


@dataclass(frozen=True)
class DecisionExecutionIdentity:
    """One canonical identity carried from decision through settlement."""

    decision_id: str
    correlation_id: str


@dataclass(frozen=True)
class ExecutionIdentity:
    """One identity for a concrete execution attempt."""

    execution_id: str
    decision_id: str
    correlation_id: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _stable_id(prefix: str, *parts: Any) -> str:
    body = "|".join(_text(value) for value in parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def ensure_decision_identity(
    opp: Any,
    decision: Any | None,
    *,
    chain_name: str,
    current_block: int,
    operator_intent: Mapping[str, Any] | None = None,
    intent_fingerprint: str | None = None,
) -> DecisionExecutionIdentity:
    """Create/preserve one canonical decision/correlation identity.

    Identity belongs to the canonical decision boundary, not to OMAR.
    Operator intent is a write-once decision-time attribution snapshot.
    """
    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        meta = {}
        try:
            opp.meta = meta
        except (AttributeError, TypeError):
            pass
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    decision_meta = _dict(getattr(decision, "metadata", None)) if decision is not None else {}

    decision_id = _text(
        brain.get("canonical_decision_id")
        or lineage.get("decision_id")
        or decision_meta.get("canonical_decision_id")
        or decision_meta.get("decision_id")
    ) or _stable_id(
        "decision", chain_name, int(current_block), getattr(opp, "id", ""), getattr(opp, "route_id", "")
    )
    correlation_id = _text(
        brain.get("correlation_id") or lineage.get("correlation_id") or decision_meta.get("correlation_id")
    ) or _stable_id("corr", decision_id, chain_name)

    intent_snapshot = _dict(
        brain.get("operator_intent") or lineage.get("operator_intent") or decision_meta.get("operator_intent")
    )
    if not intent_snapshot and operator_intent is not None:
        intent_snapshot = dict(operator_intent)
    fingerprint = _text(
        brain.get("intent_fingerprint") or lineage.get("intent_fingerprint") or decision_meta.get("intent_fingerprint")
    ) or _text(intent_fingerprint)

    canonical_lineage: dict[str, Any] = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "created_at_ms": int(lineage.get("created_at_ms") or time.time() * 1000),
    }
    if intent_snapshot:
        canonical_lineage["operator_intent"] = dict(intent_snapshot)
    if fingerprint:
        canonical_lineage["intent_fingerprint"] = fingerprint

    brain["canonical_decision_id"] = decision_id
    brain["correlation_id"] = correlation_id
    if intent_snapshot:
        brain["operator_intent"] = dict(intent_snapshot)
    if fingerprint:
        brain["intent_fingerprint"] = fingerprint
    meta["brain"] = brain
    meta["canonical_lineage"] = canonical_lineage

    if decision is not None:
        decision_meta["canonical_decision_id"] = decision_id
        decision_meta["correlation_id"] = correlation_id
        if intent_snapshot:
            decision_meta["operator_intent"] = dict(intent_snapshot)
        if fingerprint:
            decision_meta["intent_fingerprint"] = fingerprint
        decision_meta["decision_lineage"] = {"decision_id": decision_id, "correlation_id": correlation_id}
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass
    return DecisionExecutionIdentity(decision_id=decision_id, correlation_id=correlation_id)


def _require_sizing_metadata(opp: Any) -> dict[str, Any]:
    meta = getattr(opp, "meta", None)
    if isinstance(meta, dict):
        return meta
    meta = {}
    try:
        opp.meta = meta
    except (AttributeError, TypeError) as exc:
        raise ValueError("opportunity_metadata_unavailable") from exc
    return meta


def _sizing_lineage_parts(meta: dict[str, Any], decision: Any | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    decision_meta = _dict(getattr(decision, "metadata", None)) if decision is not None else {}
    existing = _text(
        brain.get("sizing_id") or lineage.get("sizing_id") or decision_meta.get("sizing_id")
    )
    return brain, lineage, decision_meta, existing


def _attach_decision_sizing(decision: Any, decision_meta: dict[str, Any], sizing_id: str) -> None:
    decision_meta["sizing_id"] = sizing_id
    decision_lineage = _dict(decision_meta.get("decision_lineage"))
    decision_lineage["sizing_id"] = sizing_id
    decision_meta["decision_lineage"] = decision_lineage
    try:
        decision.metadata = decision_meta
    except (AttributeError, TypeError):
        pass


def attach_sizing_identity(
    opp: Any,
    decision: Any | None,
    *,
    sizing_id: str,
    approved_notional_usd: float | None = None,
) -> str:
    """Attach a kernel-owned sizing identity without creating another authority."""
    sid = _text(sizing_id)
    if not sid:
        raise ValueError("sizing_id_missing")

    meta = _require_sizing_metadata(opp)
    brain, lineage, decision_meta, existing = _sizing_lineage_parts(meta, decision)
    if existing and existing != sid:
        raise ValueError("sizing_id_lineage_conflict")

    lineage["sizing_id"] = sid
    brain["sizing_id"] = sid
    meta["canonical_lineage"] = lineage
    meta["brain"] = brain
    meta["sizing_id"] = sid
    if approved_notional_usd is not None:
        try:
            lineage["approved_notional_usd"] = float(approved_notional_usd)
        except (TypeError, ValueError):
            pass
    if decision is not None:
        _attach_decision_sizing(decision, decision_meta, sid)
    return sid


def create_execution_identity(decision: Any, opp: Any) -> ExecutionIdentity:
    """Mint one execution-attempt ID from existing canonical decision lineage."""
    decision_meta = _dict(getattr(decision, "metadata", None))
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain")); lineage = _dict(meta.get("canonical_lineage"))
    decision_id = _text(decision_meta.get("canonical_decision_id") or decision_meta.get("decision_id") or brain.get("canonical_decision_id") or lineage.get("decision_id"))
    correlation_id = _text(decision_meta.get("correlation_id") or brain.get("correlation_id") or lineage.get("correlation_id"))
    if not decision_id or not correlation_id:
        raise ValueError("canonical_decision_lineage_required_for_execution_identity")
    return ExecutionIdentity(execution_id=f"execution_{uuid4().hex}", decision_id=decision_id, correlation_id=correlation_id)


def attach_execution_identity(identity: ExecutionIdentity, *, decision: Any, opp: Any, result: Any | None = None) -> None:
    """Propagate one execution identity without replacing canonical decision identity."""
    decision_meta = _dict(getattr(decision, "metadata", None))
    decision_meta.update({"execution_id": identity.execution_id, "canonical_decision_id": identity.decision_id, "correlation_id": identity.correlation_id})
    execution_lineage = _dict(decision_meta.get("execution_lineage")); execution_lineage.update({"decision_id": identity.decision_id, "correlation_id": identity.correlation_id, "execution_id": identity.execution_id})
    sizing_id = _text(decision_meta.get("sizing_id"))
    if sizing_id: execution_lineage["sizing_id"] = sizing_id
    decision_meta["execution_lineage"] = execution_lineage
    try: decision.metadata = decision_meta
    except (AttributeError, TypeError): pass

    meta = _dict(getattr(opp, "meta", None)); brain = _dict(meta.get("brain")); brain.update({"execution_id": identity.execution_id, "canonical_decision_id": identity.decision_id, "correlation_id": identity.correlation_id})
    opp_lineage = _dict(meta.get("canonical_lineage")); opp_lineage.update({"decision_id": identity.decision_id, "correlation_id": identity.correlation_id, "execution_id": identity.execution_id})
    sizing_id = _text(brain.get("sizing_id") or opp_lineage.get("sizing_id") or meta.get("sizing_id"))
    if sizing_id: opp_lineage["sizing_id"] = sizing_id
    meta["brain"] = brain; meta["canonical_lineage"] = opp_lineage
    pending_context = _dict(meta.get("pending_context")); pending_lineage = {"decision_id": identity.decision_id, "correlation_id": identity.correlation_id, "execution_id": identity.execution_id}
    if sizing_id: pending_lineage["sizing_id"] = sizing_id
    pending_context["execution_lineage"] = pending_lineage; meta["pending_context"] = pending_context
    try: opp.meta = meta
    except (AttributeError, TypeError): pass

    if result is not None:
        plan = _dict(getattr(result, "plan", None)); plan.update({"execution_id": identity.execution_id, "canonical_decision_id": identity.decision_id, "correlation_id": identity.correlation_id})
        plan_lineage = _dict(plan.get("execution_lineage")); plan_lineage.update({"decision_id": identity.decision_id, "correlation_id": identity.correlation_id, "execution_id": identity.execution_id})
        if sizing_id: plan_lineage["sizing_id"] = sizing_id
        plan["execution_lineage"] = plan_lineage
        try: result.plan = plan
        except (AttributeError, TypeError): pass


def lineage_from_opportunity(opp: Any) -> dict[str, str]:
    meta = _dict(getattr(opp, "meta", None)); brain = _dict(meta.get("brain")); lineage = _dict(meta.get("canonical_lineage"))
    result = {"decision_id": _text(brain.get("canonical_decision_id") or lineage.get("decision_id")), "correlation_id": _text(brain.get("correlation_id") or lineage.get("correlation_id"))}
    sizing_id = _text(brain.get("sizing_id") or lineage.get("sizing_id") or meta.get("sizing_id"))
    if sizing_id: result["sizing_id"] = sizing_id
    execution_id = _text(brain.get("execution_id") or lineage.get("execution_id"))
    if execution_id: result["execution_id"] = execution_id
    return result
