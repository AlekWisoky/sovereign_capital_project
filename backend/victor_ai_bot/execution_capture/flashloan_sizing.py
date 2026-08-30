from __future__ import annotations

from typing import Any, Dict, List

from ..capital_family_policy import (
    family_alias_candidates,
    resolve_family_target as resolve_canonical_family_target,
)
from ..runtime_services.treasury_governance_truth import treasury_governance_view
from .flashloan_sizing_integration import apply_adaptive_flashloan_controller
from .models import OpportunityEnvelope, SafeSizePoint


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


_PROVIDER_LIMITS = {"aave": 5.0, "balancer": 4.0, "maker": 3.5, "uniswap_flash": 2.5, "default": 3.0}


def _provider_limit(provider: str) -> float:
    return float(_PROVIDER_LIMITS.get(str(provider or "").lower(), _PROVIDER_LIMITS["default"]))


def _unique(values: List[str]) -> List[str]:
    out: List[str] = []
    for value in values:
        value_s = str(value or "")
        if value_s and value_s not in out:
            out.append(value_s)
    return out


def _family_target_candidates(envelope: OpportunityEnvelope) -> List[str]:
    metadata = dict(envelope.metadata or {}) if isinstance(envelope.metadata, dict) else {}
    meta = dict(metadata.get("meta") or {}) if isinstance(metadata.get("meta"), dict) else {}
    route_family = str(envelope.route_family or "")
    route_prefix = str(route_family.split("|", 1)[0] or "")
    return family_alias_candidates(_unique([str(metadata.get("strategy_family") or ""), str(meta.get("strategy_family") or ""), route_prefix, route_family]))


def _resolve_family_target(*, envelope: OpportunityEnvelope, family_targets: Dict[str, Any]) -> tuple[str, float, bool]:
    resolved_key, target, known = resolve_canonical_family_target(family_targets=family_targets, family=_family_target_candidates(envelope))
    return resolved_key, float(target), bool(known)


def _safe_curve_candidates(curve: List[SafeSizePoint]) -> List[SafeSizePoint]:
    items = list(curve or [])[:10]
    return items or [SafeSizePoint(1.0, 0.0, 0.0, 0.0, 0.0)]


def _legacy_choose_flashloan_size(
    *, envelope: OpportunityEnvelope, requested_size_mult: float, route_plan: Dict[str, Any],
    flashloan_resilience: Dict[str, Any], adversarial_state: Dict[str, Any],
    treasury_state: Dict[str, Any] | None = None, wealth_goal_state: Dict[str, Any] | None = None,
    drawdown_state: Dict[str, Any] | None = None, kill_switch_state: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    requested = max(0.10, float(requested_size_mult or 1.0))
    safe_curve = _safe_curve_candidates(list(envelope.safe_size_curve or []))
    route_score = float(route_plan.get("score") or 0.0)
    reserve_distortion = float(flashloan_resilience.get("reserve_distortion") or 0.0)
    interference = float(adversarial_state.get("interference_probability") or 0.0)
    stale = float(adversarial_state.get("stale_probability") or 0.0)
    copy_risk = float(adversarial_state.get("copy_risk") or 0.0)
    post_edge = float(adversarial_state.get("post_ordering_realized_edge") or envelope.expected_profit_usd)
    drawdown_pct = float((drawdown_state or {}).get("drawdownPct") or 0.0)
    hard_stop = bool((((drawdown_state or {}).get("hardStop") or {}) if isinstance(drawdown_state, dict) else {}).get("active"))
    kill_active = bool((kill_switch_state or {}).get("suppressions"))
    wealth_state = dict((wealth_goal_state or {}).get("state") or wealth_goal_state or {})
    aggressiveness_cap = float(wealth_state.get("aggressivenessCap") or 1.0)
    goal_commitment = float(wealth_state.get("capitalCommitmentPct") or 25.0)
    treasury_governance = treasury_governance_view(dict(treasury_state or {}))
    treasury_cap = float(treasury_governance.get("effective_borrow_mult_target_cap") or 1.0)
    family_targets = dict((treasury_state or {}).get("capital_engine", {}).get("family_targets") or {}) if isinstance(treasury_state, dict) else {}
    resolved_family_target_key, family_target, family_target_known = _resolve_family_target(envelope=envelope, family_targets=family_targets)
    capital_truth_requires_match = bool(family_targets)
    family_target_unresolved = bool(capital_truth_requires_match and not family_target_known)
    providers = [str(x) for x in list(flashloan_resilience.get("provider_priority") or []) if str(x)] or ["aave"]
    provider_scores = {str(x.get("provider") or ""): float(x.get("score") or 0.0) for x in list(flashloan_resilience.get("provider_scores") or []) if isinstance(x, dict)}
    selected_provider = str(flashloan_resilience.get("selected_provider") or providers[0])
    fallback_provider = str(flashloan_resilience.get("fallback_provider") or "")
    leg_states = [dict(x) for x in list(flashloan_resilience.get("leg_states") or []) if isinstance(x, dict)]
    leg_viability = min([float(x.get("viable", True)) and (1.0 - float(x.get("distortion") or 0.0)) or 0.0 for x in leg_states] or [1.0])
    avg_leg_distortion = sum(float(x.get("distortion") or 0.0) for x in leg_states) / max(1, len(leg_states))
    route_viable = bool(flashloan_resilience.get("route_viable", True)) and leg_viability > 0.0
    wealth_cap = max(0.35, min(1.8, aggressiveness_cap * max(0.70, goal_commitment / 30.0)))
    family_cap = _clip(max(0.35, family_target * 1.8), 0.35, 1.8) if family_target_known else (0.50 if capital_truth_requires_match else 1.0)
    risk_cap = 0.85 if drawdown_pct >= 8.0 else 1.0
    if hard_stop or kill_active: risk_cap = min(risk_cap, 0.75)
    density_reference = max(0.01, float(safe_curve[0].expected_profit_usd) / max(0.10, float(safe_curve[0].size_mult)))
    pool_depth_cap = 5.0
    prior_density = density_reference
    for point in safe_curve[1:]:
        mult = max(0.10, float(point.size_mult)); density = float(point.expected_profit_usd) / mult
        if density < prior_density * 0.72 or float(point.slippage_cost_usd) > float(point.expected_profit_usd) * 0.42:
            pool_depth_cap = min(pool_depth_cap, max(0.75, mult)); break
        prior_density = density
    provider_candidates: List[Dict[str, Any]] = []
    for provider in providers:
        provider_cap = _provider_limit(provider); provider_score = float(provider_scores.get(provider) or 0.75)
        provider_hard_cap = min(5.0, max(0.5, provider_cap), max(0.5, treasury_cap), wealth_cap, risk_cap, family_cap, pool_depth_cap)
        route_viability_cap = _clip(provider_hard_cap * (0.75 + 0.30 * max(0.0, route_score)) * (0.75 + 0.25 * leg_viability) * (0.75 + 0.20 * provider_score), 0.50, provider_hard_cap)
        distortion_cap = _clip(provider_hard_cap * (1.0 - max(reserve_distortion, avg_leg_distortion) * 0.60), 0.50, provider_hard_cap)
        fragility_cap = _clip(provider_hard_cap * (1.0 - (0.45 * interference + 0.30 * stale + 0.20 * copy_risk)), 0.50, provider_hard_cap)
        min_safe_candidate = min([max(0.5, float(pt.size_mult)) for pt in safe_curve] or [0.5])
        hard_cap = max(min_safe_candidate, min(provider_hard_cap, route_viability_cap, distortion_cap, fragility_cap))
        candidates: List[Dict[str, Any]] = []
        for idx, point in enumerate(safe_curve):
            point_mult = float(point.size_mult)
            if point_mult <= 0.0 or point_mult > hard_cap + 1e-6: continue
            fragility = _clip(reserve_distortion * 0.25 + avg_leg_distortion * 0.16 + interference * 0.26 + stale * 0.16 + copy_risk * 0.10 + max(0.0, point_mult - requested) * 0.20, 0.0, 0.98)
            route_bonus = _clip(route_score, 0.25, 1.25); provider_bonus = _clip(0.70 + provider_score * 0.40, 0.70, 1.10)
            net_edge = float(point.expected_profit_usd) * route_bonus * provider_bonus * (1.0 - fragility)
            net_edge -= float(point.slippage_cost_usd) + float(point.interference_penalty_usd) + float(point.latency_decay_cost_usd)
            if post_edge > 0.0: net_edge = min(net_edge, post_edge * max(0.25, 1.0 - fragility * 0.55))
            if idx > 0:
                prev = safe_curve[idx - 1]
                marginal_edge = (float(point.expected_profit_usd) - float(prev.expected_profit_usd)) - ((float(point.slippage_cost_usd) - float(prev.slippage_cost_usd)) + (float(point.interference_penalty_usd) - float(prev.interference_penalty_usd)) + (float(point.latency_decay_cost_usd) - float(prev.latency_decay_cost_usd)))
                if marginal_edge < 0.0: net_edge -= abs(marginal_edge) * 0.35
            borrow_mult = _clip(min(hard_cap, max(0.5, point_mult * (1.05 if provider_score >= 0.75 else 1.0))), 0.50, hard_cap)
            candidates.append({"provider": provider, "size_mult": round(point_mult, 6), "borrow_mult": round(borrow_mult, 6), "net_edge": round(net_edge, 6), "fragility": round(fragility, 6), "provider_score": round(provider_score, 6), "provider_limit": float(provider_cap), "reason": "safe_curve_candidate", "hard_cap": float(hard_cap), "route_viability_cap": float(route_viability_cap), "distortion_cap": float(distortion_cap), "fragility_cap": float(fragility_cap), "pool_depth_cap": float(pool_depth_cap)})
        candidates.sort(key=lambda x: (-float(x["net_edge"]), float(x["fragility"]), abs(float(x["size_mult"]) - requested), float(x["size_mult"])))
        best = candidates[0] if candidates else {"provider": provider, "size_mult": 1.0, "borrow_mult": 1.0, "net_edge": min(post_edge, envelope.expected_profit_usd), "fragility": 1.0, "provider_score": provider_score, "provider_limit": provider_cap, "hard_cap": hard_cap, "route_viability_cap": route_viability_cap, "distortion_cap": distortion_cap, "fragility_cap": fragility_cap, "pool_depth_cap": pool_depth_cap}
        provider_candidates.append({"provider": provider, "provider_score": provider_score, "provider_limit": provider_cap, "best": best, "candidates": candidates[:5]})
    provider_candidates.sort(key=lambda row: (-float(row["best"].get("net_edge") or 0.0), float(row["best"].get("fragility") or 1.0), providers.index(str(row["provider"])) if str(row["provider"]) in providers else 999))
    winner = provider_candidates[0] if provider_candidates else {"provider": selected_provider, "best": {"size_mult": 1.0, "borrow_mult": 1.0, "net_edge": min(post_edge, envelope.expected_profit_usd), "fragility": 1.0, "provider_limit": _provider_limit(selected_provider), "hard_cap": 1.0, "route_viability_cap": 1.0, "distortion_cap": 1.0, "fragility_cap": 1.0, "pool_depth_cap": pool_depth_cap}, "candidates": []}
    best = dict(winner.get("best") or {}); selected_provider_final = str(winner.get("provider") or selected_provider)
    provider_choice_reason = "preferred_provider_selected" if selected_provider_final == selected_provider else "fallback_provider_selected_for_higher_realized_ev"
    enforce_execution_floor = requested > 1.0 or float(best.get("size_mult") or 1.0) > 1.0
    min_edge_floor = max(0.75, float(envelope.gas_estimate_usd) * 0.90, (float(post_edge) * 0.20) if float(post_edge) > 0.0 else 0.75) if enforce_execution_floor else 0.0
    severe_distortion = max(reserve_distortion, avg_leg_distortion) >= 0.60
    severe_structure_collapse = requested > 0.0 and (float(best.get("size_mult") or 0.0) / requested) < 0.50
    allowed = bool(route_viable and float(best.get("net_edge") or 0.0) >= min_edge_floor and float(best.get("fragility") or 1.0) < 0.82 and not hard_stop and not kill_active and not family_target_unresolved and not (family_target_known and family_target <= 0.02) and not (severe_distortion and severe_structure_collapse))
    reason_codes: List[str] = []
    if float(best.get("size_mult") or 1.0) < requested: reason_codes.append("size_capped_for_net_ev")
    if float(best.get("hard_cap") or 0.0) < requested: reason_codes.append("hard_cap_applied")
    if reserve_distortion >= 0.45 or avg_leg_distortion >= 0.45: reason_codes.append("reserve_distortion_cap")
    if interference >= 0.55 or copy_risk >= 0.55: reason_codes.append("competition_fragility_cap")
    if stale >= 0.50: reason_codes.append("stale_risk_cap")
    if hard_stop: reason_codes.append("drawdown_hard_stop")
    if kill_active: reason_codes.append("kill_switch_active")
    if not route_viable: reason_codes.append("route_not_viable")
    if family_target_unresolved: reason_codes.append("family_target_unresolved")
    elif family_target_known and family_target <= 0.02: reason_codes.append("family_target_zero")
    if float(best.get("net_edge") or 0.0) <= 0.0: reason_codes.append("negative_net_ev")
    elif enforce_execution_floor and float(best.get("net_edge") or 0.0) < min_edge_floor: reason_codes.extend(["negative_net_ev", "net_ev_below_execution_floor"])
    if float(best.get("fragility") or 0.0) >= 0.82: reason_codes.append("fragility_too_high")
    if severe_distortion and severe_structure_collapse: reason_codes.append("structure_shift_too_large")
    if selected_provider_final != selected_provider: reason_codes.append("provider_fallback_selected")
    if fallback_provider and selected_provider_final == fallback_provider: reason_codes.append("configured_fallback_provider_used")
    return {"allowed": allowed, "requested_size_mult": requested, "size_mult": float(best.get("size_mult") or 1.0), "borrow_mult": float(best.get("borrow_mult") or 1.0), "net_edge": float(best.get("net_edge") or 0.0), "fragility": float(best.get("fragility") or 0.0), "provider_limit": float(best.get("provider_limit") or _provider_limit(selected_provider_final)), "provider_priority": providers, "provider_candidates": provider_candidates[:4], "provider_score": float(winner.get("provider_score") or best.get("provider_score") or 0.0), "selected_provider": selected_provider_final, "fallback_provider": fallback_provider or selected_provider, "provider_choice_reason": provider_choice_reason, "reason_codes": reason_codes, "candidates": list(winner.get("candidates") or [])[:5], "hard_cap": float(best.get("hard_cap") or 1.0), "goal_aggressiveness_cap": float(aggressiveness_cap), "goal_commitment_pct": float(goal_commitment), "pool_depth_cap": float(best.get("pool_depth_cap") or pool_depth_cap), "route_viability_cap": float(best.get("route_viability_cap") or 1.0), "distortion_cap": float(best.get("distortion_cap") or 1.0), "fragility_cap": float(best.get("fragility_cap") or 1.0), "family_budget_cap": float(family_cap), "family_target_pct": float(family_target), "family_target_known": bool(family_target_known), "resolved_family_target_key": resolved_family_target_key}


def choose_flashloan_size(
    *, envelope: OpportunityEnvelope, requested_size_mult: float, route_plan: Dict[str, Any], flashloan_resilience: Dict[str, Any], adversarial_state: Dict[str, Any],
    treasury_state: Dict[str, Any] | None = None, wealth_goal_state: Dict[str, Any] | None = None, drawdown_state: Dict[str, Any] | None = None, kill_switch_state: Dict[str, Any] | None = None,
    canonical_decision_id: str = "", correlation_id: str = "", capital_engine_state: Dict[str, Any] | None = None,
    governance_allowed: bool = True, capital_authority_fresh: bool = True, confidence: float = 1.0,
    aggressiveness: float | None = None, goal_gap_pct: float | None = None, max_borrow_usd: float | None = None, max_loss_usd: float | None = None,
    minimum_net_profit_usd: float = 0.0, minimum_net_roi_bps: float = 0.0, expected_loss_ratio: float = 0.0, max_size_mult: float | None = None,
) -> Dict[str, Any]:
    """Canonical production entrypoint: legacy hardening followed by adaptive risk-budget sizing."""
    metadata = dict(envelope.metadata or {}) if isinstance(envelope.metadata, dict) else {}
    meta = dict(metadata.get("meta") or {}) if isinstance(metadata.get("meta"), dict) else {}
    canonical_decision_id = str(canonical_decision_id or meta.get("canonical_decision_id") or meta.get("decision_id") or meta.get("decisionId") or "")
    correlation_id = str(correlation_id or meta.get("correlation_id") or meta.get("correlationId") or "")
    if capital_engine_state is None:
        candidate = meta.get("capital_engine_state") or meta.get("capitalEngineState")
        if isinstance(candidate, dict): capital_engine_state = dict(candidate)
    legacy = _legacy_choose_flashloan_size(envelope=envelope, requested_size_mult=requested_size_mult, route_plan=route_plan, flashloan_resilience=flashloan_resilience, adversarial_state=adversarial_state, treasury_state=treasury_state, wealth_goal_state=wealth_goal_state, drawdown_state=drawdown_state, kill_switch_state=kill_switch_state)
    wealth = dict((wealth_goal_state or {}).get("state") or wealth_goal_state or {})
    capital = dict(capital_engine_state or treasury_state or {})
    aggressiveness_value = float(aggressiveness if aggressiveness is not None else wealth.get("aggressivenessCap", 1.0))
    goal_gap_value = float(goal_gap_pct if goal_gap_pct is not None else wealth.get("goalGapPct", wealth.get("goal_gap_pct", 0.0)))
    max_borrow = float(max_borrow_usd if max_borrow_usd is not None else capital.get("max_borrow_usd", capital.get("maxBorrowUsd", capital.get("borrow_limit_usd", capital.get("borrow_capacity_usd", capital.get("borrowCapacityUsd", 0.0))))))
    max_loss = float(max_loss_usd if max_loss_usd is not None else capital.get("max_loss_usd", capital.get("maxLossUsd", capital.get("loss_limit_usd", capital.get("risk_budget_usd", capital.get("riskBudgetUsd", 0.0))))))
    if max_size_mult is None: max_size_mult = float(legacy.get("hard_cap") or 1.0)
    return apply_adaptive_flashloan_controller(legacy_result=legacy, canonical_decision_id=canonical_decision_id, correlation_id=correlation_id, route_id=str(envelope.route_id or route_plan.get("route_id") or ""), provider=str(legacy.get("selected_provider") or "aave"), requested_size_mult=requested_size_mult, capital_engine_state=capital_engine_state, treasury_state=treasury_state, wealth_goal_state=wealth_goal_state, drawdown_state=drawdown_state, governance_allowed=governance_allowed, capital_authority_fresh=capital_authority_fresh, confidence=confidence, aggressiveness=aggressiveness_value, goal_gap_pct=goal_gap_value, max_borrow_usd=max_borrow, max_loss_usd=max_loss, minimum_net_profit_usd=minimum_net_profit_usd, minimum_net_roi_bps=minimum_net_roi_bps, expected_loss_ratio=expected_loss_ratio, max_size_mult=float(max_size_mult))
