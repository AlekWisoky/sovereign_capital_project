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


def ensure_decision_identity(
    opp: Any,
    decision: Any | None,
    *,
    chain_name: str,
    current_block: int,
    operator_intent: Mapping[str, Any] | None = None,
    intent_fingerprint: str = "",
) -> DecisionExecutionIdentity:
    """Create/preserve one canonical identity and persist it on both objects.

    Identity creation is independent of OMAR. Operator intent is immutable
    decision-time context for attribution only; it never grants authority and
    cannot be replaced by later operator changes.
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

    brain["canonical_decision_id"] = decision_id
    brain["correlation_id"] = correlation_id
    meta["brain"] = brain
    canonical_lineage = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "created_at_ms": int(lineage.get("created_at_ms") or time.time() * 1000),
    }

    existing_intent = lineage.get("operator_intent")
    existing_fp = _text(lineage.get("intent_fingerprint"))
    if existing_intent is None:
        existing_intent = decision_meta.get("operator_intent")
    if not existing_fp:
        existing_fp = _text(decision_meta.get("intent_fingerprint"))

    if existing_intent is not None:
        canonical_lineage["operator_intent"] = _dict(existing_intent)
        canonical_lineage["intent_fingerprint"] = existing_fp
    elif operator_intent is not None:
        canonical_lineage["operator_intent"] = _dict(operator_intent)
        canonical_lineage["intent_fingerprint"] = _text(intent_fingerprint)
    meta["canonical_lineage"] = canonical_lineage

    if decision is not None:
        decision_meta["canonical_decision_id"] = decision_id
        decision_meta["correlation_id"] = correlation_id
        decision_meta["decision_lineage"] = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        }
        if existing_intent is not None:
            decision_meta["operator_intent"] = _dict(existing_intent)
            decision_meta["intent_fingerprint"] = existing_fp
        elif operator_intent is not None:
            decision_meta["operator_intent"] = _dict(operator_intent)
            decision_meta["intent_fingerprint"] = _text(intent_fingerprint)
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
