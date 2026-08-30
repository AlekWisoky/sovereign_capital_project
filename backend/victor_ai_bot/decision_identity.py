from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DecisionExecutionIdentity:
    """Canonical identity carried from decision through execution to settlement."""

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


def _preserve_or_set(mapping: dict[str, Any], key: str, value: Any) -> None:
    """Set attribution only when the canonical snapshot has no value yet."""
    if value is None:
        return
    if key not in mapping or mapping[key] in (None, ""):
        mapping[key] = value


def ensure_decision_identity(
    opp: Any,
    decision: Any | None,
    *,
    chain_name: str,
    current_block: int,
    operator_intent: Mapping[str, Any] | None = None,
    intent_fingerprint: str = "",
) -> DecisionExecutionIdentity:
    """Create/preserve one canonical identity and immutable decision attribution.

    The first operator-intent snapshot attached to a canonical decision is
    authoritative for that decision. Later live control changes are not allowed
    to overwrite it during execution bookkeeping or settlement.
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
    )
    if not decision_id:
        decision_id = _stable_id(
            "decision",
            chain_name,
            int(current_block),
            getattr(opp, "id", ""),
            getattr(opp, "route_id", ""),
        )

    correlation_id = _text(
        brain.get("correlation_id")
        or lineage.get("correlation_id")
        or decision_meta.get("correlation_id")
    )
    if not correlation_id:
        correlation_id = _stable_id("corr", decision_id, chain_name)

    # Attribution is write-once. This is the key anti-contamination invariant:
    # execution-time resolution of current controls may enrich a missing field,
    # but can never rewrite the snapshot recorded at decision time.
    intent_snapshot = _dict(
        brain.get("operator_intent")
        or lineage.get("operator_intent")
        or decision_meta.get("operator_intent")
    )
    if not intent_snapshot and operator_intent is not None:
        intent_snapshot = dict(operator_intent)

    fingerprint = _text(
        brain.get("intent_fingerprint")
        or lineage.get("intent_fingerprint")
        or decision_meta.get("intent_fingerprint")
    )
    if not fingerprint and intent_fingerprint:
        fingerprint = str(intent_fingerprint)

    canonical_lineage = {
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
        decision_meta["decision_lineage"] = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        }
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass

    return DecisionExecutionIdentity(decision_id=decision_id, correlation_id=correlation_id)


def lineage_from_opportunity(opp: Any) -> dict[str, str]:
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    return {
        "decision_id": _text(brain.get("canonical_decision_id") or lineage.get("decision_id")),
        "correlation_id": _text(brain.get("correlation_id") or lineage.get("correlation_id")),
    }
