"""Canonical OMAR-facing operator-intent compatibility surface.

The authority remains ``victor_ai_bot.operator_intent``. This module keeps the
historical OMAR snapshot call shape while delegating all authority to the
canonical resolver.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..operator_intent import intent_fingerprint, resolve_operator_intent


def _persisted_intent(decision: Any) -> dict[str, Any] | None:
    metadata = getattr(decision, "metadata", None)
    if not isinstance(metadata, Mapping):
        return None
    intent = metadata.get("operator_intent")
    return dict(intent) if isinstance(intent, Mapping) else None


def _opportunity_recommendation(opportunity: Any) -> dict[str, Any]:
    meta = getattr(opportunity, "meta", None)
    if not isinstance(meta, Mapping):
        return {}
    brain = meta.get("brain")
    if not isinstance(brain, Mapping):
        return {}
    recommendation = brain.get("ai_recommendation")
    return dict(recommendation) if isinstance(recommendation, Mapping) else {}


def snapshot_operator_intent(
    runtime: Any,
    opportunity: Any = None,
    decision: Any = None,
) -> tuple[dict[str, Any], str]:
    """Return the canonical intent snapshot and fingerprint.

    Once a decision carries an operator-intent snapshot, that snapshot is
    immutable for the decision lineage. For a new decision, the canonical
    resolver supplies controls and wealth-goal state; the opportunity's
    production AI recommendation is used only when the runtime has no separate
    recommendation state.
    """
    persisted = _persisted_intent(decision)
    if persisted is not None:
        return persisted, intent_fingerprint(persisted)

    intent = resolve_operator_intent(runtime)
    if not intent.get("ai_recommendation", {}).get("present"):
        recommendation = _opportunity_recommendation(opportunity)
        if recommendation:
            ai = dict(intent.get("ai_recommendation") or {})
            ai.update(
                {
                    "present": True,
                    "action": str(recommendation.get("action") or ""),
                    "posture": str(recommendation.get("posture") or ""),
                    "confidence": float(recommendation.get("confidence") or 0.0),
                    "source": str(recommendation.get("source") or recommendation.get("kind") or ""),
                }
            )
            intent["ai_recommendation"] = ai
    return intent, intent_fingerprint(intent)


__all__ = ["intent_fingerprint", "resolve_operator_intent", "snapshot_operator_intent"]
