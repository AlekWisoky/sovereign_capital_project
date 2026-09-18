from __future__ import annotations

import copy
import math
from typing import Any, Mapping

from ..runtime_subsystems.reward_trace import reward_function

_SAFE = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _bounded_calibration_reward(*, realized_net_usd: Any, expected_net_usd: Any) -> float | None:
    try:
        realized = float(realized_net_usd)
        expected = float(expected_net_usd)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(realized) or not math.isfinite(expected):
        return None
    denom = max(1.0, abs(expected))
    trace = reward_function(realized_net_pnl=realized - expected, deployed_notional=denom)
    try:
        return max(-1.0, min(1.0, float(trace.get("reward", 0.0))))
    except (TypeError, ValueError, OverflowError):
        return None


def _calibrate_from_attribution(
    runtime: Any,
    *,
    decision_id: str,
    receipt_id: str,
    outcome_id: str,
    opportunity_id: str,
    route_id: str,
    realized_net_usd: Any,
    expected_net_usd: Any,
) -> dict[str, Any]:
    store = getattr(runtime, "_agent_attribution", None)
    hub = getattr(runtime, "_agent_hub", None)
    agents = list(getattr(hub, "agents", None) or [])
    if store is None or not hasattr(store, "load") or not agents:
        return {"ok": False, "reason_code": "calibration_context_unavailable"}
    reward = _bounded_calibration_reward(realized_net_usd=realized_net_usd, expected_net_usd=expected_net_usd)
    if reward is None:
        return {"ok": False, "reason_code": "calibration_economics_invalid"}

    rows = list(store.load(limit=getattr(store, "max_items", 2000)) or [])
    match = None
    for candidate in reversed(rows):
        if _text(candidate.get("decision_id")) not in {"", str(decision_id)}:
            continue
        if receipt_id and _text(candidate.get("receipt_id")) not in {"", str(receipt_id)}:
            continue
        if outcome_id and _text(candidate.get("outcome_id")) not in {"", str(outcome_id)}:
            continue
        if opportunity_id and _text(candidate.get("opportunity_id")) not in {"", str(opportunity_id)}:
            continue
        if route_id and _text(candidate.get("route_id")) not in {"", str(route_id)}:
            continue
        match = candidate
        break
    if match is None:
        return {"ok": False, "reason_code": "calibration_attribution_missing"}

    by_name = {_text(getattr(agent, "name", agent.__class__.__name__)): agent for agent in agents}
    updated = []
    skipped = []
    for contributor in list(match.get("contributors") or []):
        item = _dict(contributor)
        name = _text(item.get("agent"))
        features = item.get("features_used")
        agent = by_name.get(name)
        if agent is None or not isinstance(features, Mapping) or not features:
            skipped.append(name or "unknown")
            continue
        calibrator = getattr(agent, "cal", None)
        if calibrator is None or not hasattr(calibrator, "update"):
            skipped.append(name)
            continue
        update_key = ":".join(part for part in (receipt_id, outcome_id, decision_id, name) if str(part))
        try:
            calibrator.update(reward=float(reward), features=dict(features), update_key=update_key)
            state = dict(calibrator.state() or {})
            if state.get("update", {}).get("code") == "calibration_update_duplicate":
                skipped.append(name)
            else:
                updated.append(name)
        except _SAFE:
            skipped.append(name)

    return {"ok": True, "reason_code": "calibration_updated" if updated else "calibration_noop", "reward": float(reward), "updated_agents": list(updated), "skipped_agents": list(skipped), "receipt_id": str(receipt_id), "outcome_id": str(outcome_id)}


def _observe_settled_outcome(runtime: Any, *, pending: Mapping[str, Any], outcome: Mapping[str, Any]) -> dict[str, Any]:
    """Feed exactly one physically persisted canonical settlement into OMAR."""
    p = _dict(pending)
    row = _dict(outcome)
    if _text(row.get("status")).lower() != "settled":
        return {"ok": False, "reason_code": "outcome_not_settled"}
    omar = getattr(runtime, "_omar", None)
    if omar is None or not bool(getattr(omar, "enabled", False)):
        return {"ok": False, "reason_code": "omar_disabled"}

    pending_lineage = _dict(p.get("canonical_lineage"))
    outcome_lineage = _dict(row.get("canonical_lineage"))
    decision_id = _text(p.get("canonical_decision_id") or pending_lineage.get("decision_id"))
    correlation_id = _text(p.get("correlation_id") or pending_lineage.get("correlation_id"))
    execution_id = _text(p.get("execution_id") or pending_lineage.get("execution_id"))
    sizing_id = _text(p.get("sizing_id") or pending_lineage.get("sizing_id"))
    opportunity_id = _text(p.get("opportunity_id") or pending_lineage.get("opportunity_id"))
    route_id = _text(p.get("route_id") or pending_lineage.get("route_id"))
    action = _text(p.get("action") or pending_lineage.get("action"))
    strategy_id = _text(p.get("strategy_id") or pending_lineage.get("strategy_id") or _dict(p.get("context")).get("strategy_id"))
    outcome_id = _text(row.get("outcome_id") or outcome_lineage.get("outcome_id"))
    receipt_id = _text(row.get("receipt_id") or outcome_lineage.get("receipt_id") or row.get("tx_hash"))

    if not decision_id or not correlation_id:
        return {"ok": False, "reason_code": "canonical_lineage_missing"}
    for name, expected, actual in (
        ("decision", decision_id, _text(row.get("decision_id") or outcome_lineage.get("decision_id"))),
        ("correlation", correlation_id, _text(row.get("correlation_id") or outcome_lineage.get("correlation_id"))),
        ("execution", execution_id, _text(row.get("execution_id") or outcome_lineage.get("execution_id"))),
        ("sizing", sizing_id, _text(row.get("sizing_id") or outcome_lineage.get("sizing_id"))),
        ("opportunity", opportunity_id, _text(row.get("opportunity_id") or outcome_lineage.get("opportunity_id"))),
        ("route", route_id, _text(row.get("route_id") or outcome_lineage.get("route_id"))),
        ("action", action, _text(row.get("action") or outcome_lineage.get("action"))),
        ("strategy", strategy_id, _text(row.get("strategy_id") or outcome_lineage.get("strategy_id") or _dict(row.get("metadata")).get("strategy_id"))),
    ):
        if expected and actual != expected:
            return {"ok": False, "reason_code": f"{name}_lineage_mismatch"}
    if not execution_id or not sizing_id or not opportunity_id or not route_id or not action or not outcome_id or not receipt_id:
        return {"ok": False, "reason_code": "canonical_lineage_incomplete"}

    operator_intent = _dict(pending_lineage.get("operator_intent") or p.get("operator_intent"))
    pending_context = _dict(p.get("context"))
    pending_metadata = _dict(p.get("metadata"))
    metadata = {
        "decision_context": {
            "operator_intent": copy.deepcopy(operator_intent),
            "wealth_goal_context": {
                key: copy.deepcopy(pending_context[key])
                for key in ("drawdown_pct", "execution_realism", "stability", "goal_gap_pct")
                if key in pending_context
            },
            "ai_recommendation": copy.deepcopy(
                pending_metadata.get("recommendation")
                or pending_context.get("ai_recommendation")
                or {}
            ),
            "capital_authority": copy.deepcopy(
                p.get("capital_authority")
                or pending_context.get("capital_authority")
                or {}
            ),
        },
        "canonical_lineage": {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "execution_id": execution_id,
            "sizing_id": sizing_id,
            "receipt_id": receipt_id,
            "outcome_id": outcome_id,
            "opportunity_id": opportunity_id,
            "route_id": route_id,
            "action": action,
            "strategy_id": strategy_id,
        },
        "source": "phase2_canonical_outcome_ledger",
        "settlement": copy.deepcopy(row),
        "strategy_id": strategy_id,
        "capital_demand": copy.deepcopy(row.get("capital_demand") or p.get("capital_demand") or {}),
        "capital_authority": copy.deepcopy(row.get("capital_authority") or p.get("capital_authority") or {}),
        "internal_prime_authority": copy.deepcopy(row.get("internal_prime_authority") or p.get("internal_prime_authority") or {}),
    }
    if operator_intent:
        metadata["operator_intent"] = copy.deepcopy(operator_intent)
    intent_fingerprint = _text(pending_lineage.get("intent_fingerprint") or p.get("intent_fingerprint"))
    if intent_fingerprint:
        metadata["intent_fingerprint"] = intent_fingerprint

    result = dict(omar.observe_outcome(
        decision_id=decision_id,
        ok=bool(row.get("ok", True)),
        realized_net_usd=row.get("realized_net_usd"),
        expected_net_usd=row.get("expected_net_usd", p.get("expected_net_usd")),
        amount_in_wei=row.get("amount_in_wei"),
        gas_cost_usd=row.get("gas_cost_usd"),
        slippage_bps=row.get("slippage_bps"),
        latency_ms=row.get("latency_ms"),
        route_id=route_id,
        tx_hash=_text(row.get("tx_hash") or receipt_id),
        outcome_truth_verified=bool(row.get("truth_verified", False)),
        metadata=metadata,
    ))
    calibration = _calibrate_from_attribution(runtime, decision_id=decision_id, receipt_id=receipt_id, outcome_id=outcome_id, opportunity_id=opportunity_id, route_id=route_id, realized_net_usd=row.get("realized_net_usd"), expected_net_usd=row.get("expected_net_usd", p.get("expected_net_usd")))
    result["calibration"] = calibration
    result["strategy_id"] = strategy_id
    return result
