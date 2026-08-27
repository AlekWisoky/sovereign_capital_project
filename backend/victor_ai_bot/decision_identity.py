from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DecisionExecutionIdentity:
    """Canonical identity carried from decision through execution to settlement.

    The identifiers are deterministic for a decision opportunity on a block.
    Re-entering the same decision does not manufacture a second learning
    identity, while an existing identity is always preserved.
    """

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
) -> DecisionExecutionIdentity:
    """Create/preserve one canonical identity and persist it on both objects."""
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
    meta["canonical_lineage"] = {
        "decision_id": decision_id,
        "correlation_id": correlation_id,
        "created_at_ms": int(lineage.get("created_at_ms") or time.time() * 1000),
    }

    if decision is not None:
        decision_meta["canonical_decision_id"] = decision_id
        decision_meta["correlation_id"] = correlation_id
        decision_meta["decision_lineage"] = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
        }
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass

    return DecisionExecutionIdentity(
        decision_id=decision_id,
        correlation_id=correlation_id,
    )


def lineage_from_opportunity(opp: Any) -> dict[str, str]:
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    return {
        "decision_id": _text(brain.get("canonical_decision_id") or lineage.get("decision_id")),
        "correlation_id": _text(brain.get("correlation_id") or lineage.get("correlation_id")),
    }
