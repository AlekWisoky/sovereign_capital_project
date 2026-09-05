from __future__ import annotations

from typing import Any, Mapping

from .identity import TradeIdentity, attach_identity, identity_from, new_decision_identity


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def ensure_decision_identity(
    opportunity: Any,
    decision: Any,
    *,
    chain_name: str = "default",
    current_block: int = 0,
    operator_intent: Any = None,
    intent_fingerprint: str = "",
) -> TradeIdentity:
    """Ensure one canonical decision/correlation pair at the decision boundary."""
    identity = identity_from(decision) or identity_from(opportunity)
    if identity is None or not identity.decision_id or not identity.correlation_id:
        identity = new_decision_identity()

    attach_identity(decision, identity)
    attach_identity(opportunity, identity)

    meta = getattr(decision, "metadata", None)
    if not isinstance(meta, dict):
        try:
            decision.metadata = {}
            meta = decision.metadata
        except (AttributeError, TypeError):
            meta = None
    if isinstance(meta, dict):
        lineage = meta.setdefault("canonical_lineage", {})
        lineage.update(identity.to_dict())
        lineage.update(
            {"chain": _text(chain_name) or "default", "decision_block": int(current_block)}
        )
        if operator_intent is not None and "operator_intent_snapshot" not in meta:
            payload = (
                operator_intent.to_dict()
                if hasattr(operator_intent, "to_dict")
                else _mapping(operator_intent)
            )
            meta["operator_intent_snapshot"] = dict(payload)
            lineage["operator_intent"] = dict(payload)
        if intent_fingerprint and not meta.get("intent_fingerprint"):
            fingerprint = _text(intent_fingerprint)
            meta["intent_fingerprint"] = fingerprint
            lineage["intent_fingerprint"] = fingerprint

    opp_meta = getattr(opportunity, "meta", None)
    if isinstance(opp_meta, dict):
        brain = opp_meta.setdefault("brain", {})
        if isinstance(brain, dict):
            brain["canonical_decision_id"] = identity.decision_id
            brain["correlation_id"] = identity.correlation_id
        lineage = opp_meta.setdefault("canonical_lineage", {})
        if isinstance(lineage, dict):
            lineage.update(identity.to_dict())
            if operator_intent is not None and "operator_intent" not in lineage:
                payload = (
                    operator_intent.to_dict()
                    if hasattr(operator_intent, "to_dict")
                    else _mapping(operator_intent)
                )
                lineage["operator_intent"] = dict(payload)
            if intent_fingerprint and not lineage.get("intent_fingerprint"):
                lineage["intent_fingerprint"] = _text(intent_fingerprint)

    return identity


def lineage_from_opportunity(opportunity: Any) -> dict[str, str]:
    """Return only the canonical decision/correlation lineage already present."""
    identity = identity_from(opportunity)
    if identity is None:
        meta = _mapping(getattr(opportunity, "meta", None))
        identity = identity_from(_mapping(meta.get("canonical_lineage")))
    if identity is None:
        return {"decision_id": "", "correlation_id": ""}
    return {"decision_id": identity.decision_id, "correlation_id": identity.correlation_id}
