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
) -> DecisionExecutionIdentity:
    """Create/preserve one canonical identity and persist it on both objects.

    Identity creation is deliberately independent of OMAR. The decision,
    execution, and settlement lifecycle must remain traceable even when the
    OMAR learning policy is disabled.
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
    meta["canonical_lineage"] = {
        **lineage,
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

    return DecisionExecutionIdentity(decision_id=decision_id, correlation_id=correlation_id)


# @codescene(disable:"Bumpy Road Ahead") Canonical lineage helper keeps sizing identity atomic; revisit after lifecycle stabilizes.
def ensure_sizing_identity(
    opp: Any,
    decision: Any | None,
    *,
    decision_id: str = "",
    applied_size_mult: float | None = None,
) -> str:
    """Create/preserve a deterministic identity for the applied trade size.

    The sizing identity is lineage, not a learning feature. It binds the
    selected decision to the concrete amount/size multiplier that reaches the
    execution boundary, allowing the settled outcome to attribute realized
    economics to the exact sized action.
    """
    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        return ""
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    decision_meta = _dict(getattr(decision, "metadata", None)) if decision is not None else {}
    canonical_decision_id = _text(
        decision_id
        or brain.get("canonical_decision_id")
        or lineage.get("decision_id")
        or decision_meta.get("canonical_decision_id")
    )
    if not canonical_decision_id:
        return ""

    if applied_size_mult is None:
        try:
            applied_size_mult = float(
                getattr(decision, "size_mult", None)
                if decision is not None
                else brain.get("size_mult_applied") or brain.get("size_mult_omar") or 1.0
            )
        except (TypeError, ValueError):
            applied_size_mult = 1.0
    try:
        size_mult = float(applied_size_mult)
    except (TypeError, ValueError):
        size_mult = 1.0

    amount_in_wei = ""
    try:
        amount_in_wei = _text(getattr(opp.route.legs[0], "amount_in", ""))
    except (AttributeError, IndexError, TypeError):
        amount_in_wei = _text(meta.get("amount_in_wei") or meta.get("amountInWei"))

    existing = _text(
        brain.get("sizing_id") or lineage.get("sizing_id") or decision_meta.get("sizing_id")
    )
    sizing_id = existing or _stable_id(
        "sizing",
        canonical_decision_id,
        _text(getattr(opp, "id", "")),
        _text(getattr(opp, "route_id", "")),
        amount_in_wei,
        f"{size_mult:.12f}",
    )
    brain["sizing_id"] = sizing_id
    brain["size_mult_applied"] = size_mult
    if amount_in_wei:
        brain["amount_in_wei"] = amount_in_wei
    meta["brain"] = brain
    lineage["decision_id"] = canonical_decision_id
    lineage["sizing_id"] = sizing_id
    meta["canonical_lineage"] = lineage
    if decision is not None:
        decision_meta["sizing_id"] = sizing_id
        decision_meta["size_mult_applied"] = size_mult
        try:
            decision.metadata = decision_meta
        except (AttributeError, TypeError):
            pass
    return sizing_id


def lineage_from_opportunity(opp: Any) -> dict[str, str]:
    meta = _dict(getattr(opp, "meta", None))
    brain = _dict(meta.get("brain"))
    lineage = _dict(meta.get("canonical_lineage"))
    result = {
        "decision_id": _text(brain.get("canonical_decision_id") or lineage.get("decision_id")),
        "correlation_id": _text(brain.get("correlation_id") or lineage.get("correlation_id")),
    }
    sizing_id = _text(brain.get("sizing_id") or lineage.get("sizing_id"))
    if sizing_id:
        result["sizing_id"] = sizing_id
    return result
