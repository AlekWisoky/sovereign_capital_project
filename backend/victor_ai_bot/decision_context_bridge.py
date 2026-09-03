from __future__ import annotations

"""Small lifecycle bridge for canonical decision identity propagation.

This module is intentionally independent of execution and governance. It gives
those layers one stable envelope to carry the same decision identity and the
inputs that explain why a decision was made.
"""

import time
import uuid
from typing import Any, Dict, Mapping, MutableMapping, Optional

from .canonical_decision_context import (
    AIRecommendation,
    CanonicalDecisionContext,
    HumanIntent,
    LatencyContext,
    WealthObjective,
    capital_authority_from_engine_state,
)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def build_decision_context(
    *,
    opportunity: Any,
    current_block: int,
    capital_engine_state: Optional[Mapping[str, Any]] = None,
    human_intent: Optional[Mapping[str, Any]] = None,
    wealth_objective: Optional[Mapping[str, Any]] = None,
    ai_recommendation: Optional[Mapping[str, Any]] = None,
    latency: Optional[Mapping[str, Any]] = None,
    decision_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> CanonicalDecisionContext:
    """Create one canonical context at the decision boundary."""
    meta = getattr(opportunity, "meta", None)
    meta = meta if isinstance(meta, dict) else {}
    brain = meta.get("brain") if isinstance(meta.get("brain"), dict) else {}
    aqe = meta.get("aqe") if isinstance(meta.get("aqe"), dict) else {}

    human = dict(human_intent or {})
    wealth = dict(wealth_objective or {})
    ai = dict(ai_recommendation or {})
    timing = dict(latency or {})

    if not human:
        human = dict(meta.get("human_intent") or {})
    if not wealth:
        wealth = dict(meta.get("wealth_objective") or {})
    if not ai:
        ai = {
            "action": str(brain.get("action") or ""),
            "confidence": float(brain.get("p_success") or 0.0),
            "model": str(brain.get("model") or ""),
            "rationale": str(brain.get("reason") or ""),
        }
    if not timing:
        timing = dict(meta.get("latency") or meta.get("latency_context") or {})

    timing.setdefault("observed_at_ns", time.time_ns())
    timing.setdefault("gas_mode", str(brain.get("gas_mode") or "standard"))

    return CanonicalDecisionContext(
        decision_id=str(decision_id or _new_id("dec")),
        correlation_id=str(correlation_id or _new_id("corr")),
        human_intent=HumanIntent(
            instruction=str(human.get("instruction") or human.get("intent") or ""),
            aggressiveness=str(human.get("aggressiveness") or "normal"),
            risk_multiplier=float(human.get("risk_multiplier", 1.0) or 1.0),
        ),
        wealth_objective=WealthObjective(
            target_amount=wealth.get("target_amount", wealth.get("goal_amount", "0")),
            currency=str(wealth.get("currency") or ""),
            timeframe_seconds=int(wealth.get("timeframe_seconds", wealth.get("timeframe", 0)) or 0),
        ),
        ai_recommendation=AIRecommendation(
            action=str(ai.get("action") or ""),
            rationale=str(ai.get("rationale") or ""),
            confidence=float(ai.get("confidence", ai.get("p_success", 0.0)) or 0.0),
            model=str(ai.get("model") or ""),
        ),
        capital_authority=capital_authority_from_engine_state(capital_engine_state),
        latency=LatencyContext(
            observed_at_ns=int(timing.get("observed_at_ns") or time.time_ns()),
            market_data_age_ms=float(timing.get("market_data_age_ms", 0.0) or 0.0),
            decision_latency_ms=float(timing.get("decision_latency_ms", 0.0) or 0.0),
            execution_deadline_ms=float(timing.get("execution_deadline_ms", 0.0) or 0.0),
            gas_mode=str(timing.get("gas_mode") or "standard"),
        ),
        strategy_family=str(meta.get("strategy_family") or meta.get("family") or ""),
        opportunity_id=str(getattr(opportunity, "id", "") or ""),
        route_id=str(getattr(opportunity, "route_id", "") or ""),
        created_at_ns=time.time_ns(),
    )


def attach_context(record: MutableMapping[str, Any], context: CanonicalDecisionContext) -> MutableMapping[str, Any]:
    """Attach the same canonical lineage/context to any lifecycle record."""
    record["decision_context"] = context.to_dict()
    record.update(context.lineage())
    return record


def execution_record(
    context: CanonicalDecisionContext,
    *,
    execution_id: str,
    status: str = "prepared",
    tx_hash: str = "",
    **details: Any,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "execution_id": str(execution_id),
        "status": str(status),
        "tx_hash": str(tx_hash or ""),
        "record_type": "execution",
    }
    attach_context(record, context)
    record["details"] = dict(details)
    return record


def settled_outcome_record(
    context: CanonicalDecisionContext,
    *,
    outcome_id: str,
    status: str,
    tx_hash: str = "",
    **details: Any,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "outcome_id": str(outcome_id),
        "status": str(status),
        "tx_hash": str(tx_hash or ""),
        "record_type": "settled_outcome",
    }
    attach_context(record, context)
    record["details"] = dict(details)
    return record


def learning_record(
    context: CanonicalDecisionContext,
    *,
    outcome_id: str,
    reward: Any,
    **details: Any,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "outcome_id": str(outcome_id),
        "reward": reward,
        "record_type": "learning",
    }
    attach_context(record, context)
    record["details"] = dict(details)
    return record
