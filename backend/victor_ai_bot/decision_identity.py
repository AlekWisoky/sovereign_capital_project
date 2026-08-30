from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .operator_intent import intent_fingerprint, resolve_operator_intent


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


def snapshot_operator_intent(runtime: Any) -> dict[str, Any]:
    """Capture one detached operator-intent snapshot at the canonical boundary."""
    return deepcopy(resolve_operator_intent(runtime))


def ensure_decision_identity(
    opp: Any,
    decision: Any | None,
    *,
    chain_name: str,
    current_block: int,
    operator_intent: Mapping[str, Any] | None = None,
) -> DecisionExecutionIdentity:
    """Create/preserve canonical identity and attach operator-intent attribution."""
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

    intent = dict(operator_intent or decision_meta.get("operator_intent") or {})
    intent_fp = _text(
        brain.get("operator_intent_fingerprint")
        or lineage.get("operator_intent_fingerprint")
        or decision_meta.get("operator_intent_fingerprint")
    )
    if intent and not intent_fp:
        intent_fp = intent_fingerprint(intent)

    brain["canonical_decision_id"] = decision_id
    brain["correlation_id"] = correlation_id
    if intent:
        brain["operator_intent"] = intent
        brain["operator_intent_fingerprint"] = intent_fp
    meta["brain"] = brain
    meta["canonical_lineage"] = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "operator_intent_fingerprint": intent_fp,
        "created_at_ms": int(lineage.get("created_at_ms") or time.time() * 1000),
    }

    if decision is not None:
        decision_meta["canonical_decision_id"] = decision_id
        decision_meta["correlation_id"] = correlation_id
        decision_meta["decision_lineage"] = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        }
        if intent:
            decision_meta["operator_intent"] = intent
            decision_meta["operator_intent_fingerprint"] = intent_fp
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass

    return DecisionExecutionIdentity(decision_id=decision_id, correlation_id=correlation_id)


def lineage_from_opportunity(opp: Any) -> dict[str, str]:
    """Return the stable two-field decision/execution lineage contract."""
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    return {
        "decision_id": _text(brain.get("canonical_decision_id") or lineage.get("decision_id")),
        "correlation_id": _text(brain.get("correlation_id") or lineage.get("correlation_id")),
    }


def operator_intent_fingerprint_from_opportunity(opp: Any) -> str:
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    return _text(brain.get("operator_intent_fingerprint") or lineage.get("operator_intent_fingerprint"))
