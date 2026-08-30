"""Compatibility integration helpers for the canonical adaptive flash-loan controller."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from .adaptive_flashloan_risk_budget import build_risk_budget, choose_adaptive_size


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _first(mapping: Mapping[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return _num(mapping.get(key), default)
    return float(default)


def apply_adaptive_flashloan_controller(
    *, legacy_result: Dict[str, Any], canonical_decision_id: str, correlation_id: str,
    route_id: str, provider: str, requested_size_mult: float,
    capital_engine_state: Mapping[str, Any] | None, treasury_state: Mapping[str, Any] | None,
    wealth_goal_state: Mapping[str, Any] | None, drawdown_state: Mapping[str, Any] | None,
    governance_allowed: bool, capital_authority_fresh: bool, confidence: float,
    aggressiveness: float, goal_gap_pct: float, max_borrow_usd: float, max_loss_usd: float,
    minimum_net_profit_usd: float, minimum_net_roi_bps: float, expected_loss_ratio: float,
    max_size_mult: float,
) -> Dict[str, Any]:
    """Apply Phase 23 adaptive sizing inside the canonical flash-loan path."""
    decision_id = str(canonical_decision_id or "").strip()
    correlation = str(correlation_id or "").strip()
    if not decision_id or not correlation:
        return dict(legacy_result)
    root = dict(capital_engine_state or treasury_state or {})
    capital = dict(root.get("capital_engine") or root) if isinstance(root, Mapping) else {}
    wealth = dict(wealth_goal_state or {})
    wealth = dict(wealth.get("state") or wealth)
    drawdown = dict(drawdown_state or {})
    hard_stop = bool(drawdown.get("hardStop", False))
    if isinstance(drawdown.get("hardStop"), Mapping):
        hard_stop = bool(drawdown["hardStop"].get("active"))
    available = _first(capital, "capital_available_usd", "capitalAvailableUsd", "available_usd", "availableUsd")
    deployable = _first(capital, "deployable_capital_usd", "deployableCapitalUsd", "deployable_usd", "deployableUsd", default=available)
    family = _first(capital, "family_allocation_usd", "familyAllocationUsd", "family_capital_usd", "familyCapitalUsd")
    if family <= 0.0:
        targets = capital.get("family_targets")
        key = str((legacy_result or {}).get("resolved_family_target_key") or "")
        if isinstance(targets, Mapping) and key:
            family = _first(targets, key)
    if family <= 0.0:
        family = deployable
    selected = str((legacy_result or {}).get("selected_provider") or provider or "aave")
    rows = list((legacy_result or {}).get("provider_candidates") or [])
    selected_row = next((row for row in rows if str(row.get("provider") or "") == selected), None)
    candidates = list((selected_row or {}).get("candidates") or [])
    if not candidates:
        candidates = [{"size_mult": float((legacy_result or {}).get("size_mult") or requested_size_mult or 1.0), "net_profit_usd": float((legacy_result or {}).get("net_edge") or 0.0), "net_roi_bps": 0.0}]
    normalized = []
    for raw in candidates:
        item = dict(raw or {})
        size = _num(item.get("size_mult"))
        net = _num(item.get("net_profit_usd", item.get("net_edge")))
        roi = _num(item.get("net_roi_bps"))
        loss = _num(item.get("estimated_loss_usd"), size * max(0.0, expected_loss_ratio))
        if roi == 0.0 and family > 0.0:
            roi = net / family * 10_000.0
        item.update(size_mult=size, net_profit_usd=net, net_roi_bps=roi, estimated_loss_usd=loss)
        normalized.append(item)
    budget = build_risk_budget(
        capital_available_usd=available, deployable_capital_usd=deployable,
        family_allocation_usd=family, max_borrow_usd=max_borrow_usd,
        max_loss_usd=max_loss_usd, current_drawdown_pct=_first(drawdown, "drawdownPct", "drawdown_pct"),
        hard_stop=hard_stop, governance_allowed=governance_allowed,
        capital_authority_fresh=capital_authority_fresh, confidence=confidence,
        aggressiveness=aggressiveness, goal_gap_pct=goal_gap_pct,
    )
    adaptive = choose_adaptive_size(
        canonical_decision_id=decision_id, correlation_id=correlation, route_id=route_id,
        provider=selected, requested_size_mult=requested_size_mult, candidates=normalized,
        risk_budget_usd=budget, minimum_net_profit_usd=minimum_net_profit_usd,
        minimum_net_roi_bps=minimum_net_roi_bps, expected_loss_ratio=expected_loss_ratio,
        max_size_mult=max_size_mult,
    )
    result = dict(legacy_result)
    result.update(adaptive_risk_budget=adaptive.to_dict(), risk_budget_usd=float(budget), sizing_id=adaptive.sizing_id, canonical_decision_id=decision_id, correlation_id=correlation, adaptive_controller="phase23")
    if adaptive.allowed and bool(result.get("allowed", True)):
        result["size_mult"] = float(adaptive.selected_size_mult)
        result["borrow_mult"] = min(float(result.get("borrow_mult") or adaptive.selected_size_mult), float(adaptive.selected_size_mult))
        result["adaptive_allowed"] = True
    else:
        result["adaptive_allowed"] = False
        result["allowed"] = False
        result.setdefault("reason_codes", []).append(str(adaptive.reason))
    return result
