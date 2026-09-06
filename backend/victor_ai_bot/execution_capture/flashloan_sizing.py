from __future__ import annotations

from typing import Any, Dict

from . import flashloan_sizing_legacy as _legacy
from .adaptive_flashloan_risk_budget import build_risk_budget, choose_adaptive_size

# Preserve the legacy module's helper surface while making this file the
# canonical production entrypoint.
_clip = _legacy._clip
_provider_limit = _legacy._provider_limit
_unique = _legacy._unique
_family_target_candidates = _legacy._family_target_candidates
_resolve_family_target = _legacy._resolve_family_target
_safe_curve_candidates = _legacy._safe_curve_candidates


def choose_flashloan_size(
    *,
    envelope,
    requested_size_mult: float,
    route_plan: Dict[str, Any],
    flashloan_resilience: Dict[str, Any],
    adversarial_state: Dict[str, Any],
    treasury_state: Dict[str, Any] | None = None,
    wealth_goal_state: Dict[str, Any] | None = None,
    drawdown_state: Dict[str, Any] | None = None,
    kill_switch_state: Dict[str, Any] | None = None,
    canonical_decision_id: str = "",
    correlation_id: str = "",
    capital_engine_state: Dict[str, Any] | None = None,
    governance_allowed: bool = True,
    capital_authority_fresh: bool = True,
    confidence: float = 1.0,
    aggressiveness: float | None = None,
    goal_gap_pct: float | None = None,
    max_borrow_usd: float | None = None,
    max_loss_usd: float | None = None,
    minimum_net_profit_usd: float = 0.0,
    minimum_net_roi_bps: float = 0.0,
    expected_loss_ratio: float = 0.0,
    max_size_mult: float | None = None,
) -> Dict[str, Any]:
    """Run legacy hardening, then Phase 23 adaptive risk-budget sizing."""
    metadata = dict(getattr(envelope, "metadata", {}) or {})
    meta = dict(metadata.get("meta") or {}) if isinstance(metadata.get("meta"), dict) else {}
    canonical_decision_id = str(
        canonical_decision_id
        or meta.get("canonical_decision_id")
        or meta.get("decision_id")
        or meta.get("decisionId")
        or ""
    )
    correlation_id = str(
        correlation_id or meta.get("correlation_id") or meta.get("correlationId") or ""
    )
    if capital_engine_state is None:
        candidate = meta.get("capital_engine_state") or meta.get("capitalEngineState")
        if isinstance(candidate, dict):
            capital_engine_state = dict(candidate)

    legacy_result = _legacy.choose_flashloan_size(
        envelope=envelope,
        requested_size_mult=requested_size_mult,
        route_plan=route_plan,
        flashloan_resilience=flashloan_resilience,
        adversarial_state=adversarial_state,
        treasury_state=treasury_state,
        wealth_goal_state=wealth_goal_state,
        drawdown_state=drawdown_state,
        kill_switch_state=kill_switch_state,
    )
    if not canonical_decision_id or not correlation_id:
        return legacy_result

    capital = dict(capital_engine_state or treasury_state or {})
    if isinstance(capital.get("capital_engine"), dict):
        capital = dict(capital["capital_engine"])
    wealth = dict((wealth_goal_state or {}).get("state") or wealth_goal_state or {})
    drawdown = dict(drawdown_state or {})
    hard_stop = bool(drawdown.get("hardStop", False))
    if isinstance(drawdown.get("hardStop"), dict):
        hard_stop = bool(drawdown["hardStop"].get("active"))

    def num(*keys: str, default: float = 0.0) -> float:
        for key in keys:
            if capital.get(key) is not None:
                try:
                    return float(capital[key])
                except (TypeError, ValueError):
                    pass
        return default

    available = num("capital_available_usd", "capitalAvailableUsd", "available_usd", "availableUsd")
    deployable = num(
        "deployable_capital_usd",
        "deployableCapitalUsd",
        "deployable_usd",
        "deployableUsd",
        default=available,
    )
    family = num(
        "family_allocation_usd", "familyAllocationUsd", "family_capital_usd", "familyCapitalUsd"
    )
    if family <= 0.0:
        targets = capital.get("family_targets")
        key = str(legacy_result.get("resolved_family_target_key") or "")
        if isinstance(targets, dict) and key:
            try:
                family = float(targets.get(key) or 0.0)
            except (TypeError, ValueError):
                family = 0.0
    if family <= 0.0:
        family = deployable

    max_borrow = float(
        max_borrow_usd
        if max_borrow_usd is not None
        else num(
            "max_borrow_usd",
            "maxBorrowUsd",
            "borrow_limit_usd",
            "borrow_capacity_usd",
            "borrowCapacityUsd",
        )
    )
    max_loss = float(
        max_loss_usd
        if max_loss_usd is not None
        else num("max_loss_usd", "maxLossUsd", "loss_limit_usd", "risk_budget_usd", "riskBudgetUsd")
    )
    if max_size_mult is None:
        max_size_mult = float(legacy_result.get("hard_cap") or 1.0)
    aggression = float(
        aggressiveness if aggressiveness is not None else wealth.get("aggressivenessCap", 1.0)
    )
    goal_gap = float(
        goal_gap_pct
        if goal_gap_pct is not None
        else wealth.get("goalGapPct", wealth.get("goal_gap_pct", 0.0))
    )
    selected = str(legacy_result.get("selected_provider") or "aave")
    rows = list(legacy_result.get("provider_candidates") or [])
    selected_row = next((row for row in rows if str(row.get("provider") or "") == selected), None)
    candidates = list((selected_row or {}).get("candidates") or [])
    if not candidates:
        candidates = [
            {
                "size_mult": float(legacy_result.get("size_mult") or requested_size_mult or 1.0),
                "net_profit_usd": float(legacy_result.get("net_edge") or 0.0),
                "net_roi_bps": 0.0,
            }
        ]
    normalized = []
    for raw in candidates:
        item = dict(raw or {})
        size = float(item.get("size_mult") or 0.0)
        net = float(item.get("net_profit_usd", item.get("net_edge")) or 0.0)
        roi = float(item.get("net_roi_bps") or 0.0)
        loss = float(item.get("estimated_loss_usd") or (size * max(0.0, expected_loss_ratio)))
        if roi == 0.0 and family > 0.0:
            roi = net / family * 10000.0
        item.update(
            {
                "size_mult": size,
                "net_profit_usd": net,
                "net_roi_bps": roi,
                "estimated_loss_usd": loss,
            }
        )
        normalized.append(item)
    budget = build_risk_budget(
        capital_available_usd=available,
        deployable_capital_usd=deployable,
        family_allocation_usd=family,
        max_borrow_usd=max_borrow,
        max_loss_usd=max_loss,
        current_drawdown_pct=float(
            drawdown.get("drawdownPct") or drawdown.get("drawdown_pct") or 0.0
        ),
        hard_stop=hard_stop,
        governance_allowed=governance_allowed,
        capital_authority_fresh=capital_authority_fresh,
        confidence=confidence,
        aggressiveness=aggression,
        goal_gap_pct=goal_gap,
    )
    adaptive = choose_adaptive_size(
        canonical_decision_id=canonical_decision_id,
        correlation_id=correlation_id,
        route_id=str(getattr(envelope, "route_id", "") or route_plan.get("route_id") or ""),
        provider=selected,
        requested_size_mult=requested_size_mult,
        candidates=normalized,
        risk_budget_usd=budget,
        minimum_net_profit_usd=minimum_net_profit_usd,
        minimum_net_roi_bps=minimum_net_roi_bps,
        expected_loss_ratio=expected_loss_ratio,
        max_size_mult=float(max_size_mult),
    )
    result = dict(legacy_result)
    result.update(
        {
            "adaptive_risk_budget": adaptive.to_dict(),
            "risk_budget_usd": float(budget),
            "sizing_id": adaptive.sizing_id,
            "canonical_decision_id": canonical_decision_id,
            "correlation_id": correlation_id,
            "adaptive_controller": "phase23",
        }
    )
    if adaptive.allowed and bool(result.get("allowed", True)):
        result["size_mult"] = float(adaptive.selected_size_mult)
        result["borrow_mult"] = min(
            float(result.get("borrow_mult") or adaptive.selected_size_mult),
            float(adaptive.selected_size_mult),
        )
        result["adaptive_allowed"] = True
    else:
        result["adaptive_allowed"] = False
        result["allowed"] = False
        result.setdefault("reason_codes", []).append(str(adaptive.reason))
    return result
