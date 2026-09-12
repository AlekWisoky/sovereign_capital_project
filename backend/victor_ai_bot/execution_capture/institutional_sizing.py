from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping


# These are design tiers only. They do not enable capital authority or change
# the existing V1 sizing path. Activation belongs to governance/live-authority.
INSTITUTIONAL_V1_TIERS: tuple[dict[str, Any], ...] = (
    {"id": "controlled_250k", "target_notional_usd": 250_000.0, "enabled": False},
    {"id": "controlled_500k", "target_notional_usd": 500_000.0, "enabled": False},
    {"id": "institutional_1m", "target_notional_usd": 1_000_000.0, "enabled": False},
    {"id": "institutional_2m", "target_notional_usd": 2_000_000.0, "enabled": False},
)


class SizingContractError(ValueError):
    """Raised only when a contract cannot be constructed from its inputs."""


@dataclass(frozen=True)
class LiquiditySizingContext:
    available_usd: float | None = None
    depth_usd: float | None = None
    pool_depth_cap_usd: float | None = None
    reserve_distortion: float = 0.0
    liquidity_fragility: float = 0.0
    slippage_sensitivity: float = 0.0
    provider_capacity_usd: float | None = None
    route_capacity_usd: float | None = None


@dataclass(frozen=True)
class ExecutionSizingContext:
    expected_pipeline_latency_ms: float | None = None
    latency_half_life_ms: float | None = None
    latency_pressure: float = 0.0
    endpoint_quality: float = 0.0
    venue_reliability: float = 0.0
    simulation_confidence: float = 0.0
    freshness_score: float = 0.0
    private_send_preference: bool = False


@dataclass(frozen=True)
class EconomicsSizingContext:
    expected_gross_profit_usd: float = 0.0
    expected_net_profit_usd: float | None = None
    gas_cost_usd: float = 0.0
    borrow_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    latency_cost_usd: float = 0.0
    failure_cost_usd: float = 0.0
    min_profit_usd: float = 0.0
    min_profit_bps: float = 0.0
    success_probability: float | None = None
    margin_ratio: float | None = None


@dataclass(frozen=True)
class CapitalAuthoritySizingContext:
    source: str = "capital_engine_state"
    status: str = "unavailable"
    freshness: str = "unavailable"
    authority_id: str = ""
    available_usd: float | None = None
    deployable_usd: float | None = None
    reserve_usd: float | None = None
    drawdown_buffer_usd: float | None = None
    borrowed_usd: float = 0.0
    prime_available: bool = False
    prime_capacity_usd: float | None = None
    prime_utilization: float = 0.0
    prime_reserved_usd: float = 0.0
    prime_family_exposure_usd: float = 0.0
    family_cap_usd: float | None = None


@dataclass(frozen=True)
class WealthGoalSizingContext:
    target_return_pct: float = 0.0
    current_return_pct: float = 0.0
    capital_commitment_pct: float = 25.0
    aggressiveness_cap: float = 1.0
    max_drawdown_pct: float = 10.0
    drawdown_pct: float = 0.0
    timeframe_days: int = 30
    goal_status: str = "active"
    pacing: str = "steady"
    goal_horizon_compatibility: float = 1.0


@dataclass(frozen=True)
class GovernanceSizingContext:
    admitted: bool = False
    reason_code: str = "unavailable"
    strategy_family: str = ""
    capital_source: str = ""
    live_authority: bool = False
    execution_allowed: bool = False
    hard_stop: bool = False
    kill_switch: bool = False
    sandbox_only: bool = False
    defensive_mode: bool = False
    max_deployable_pct: float = 0.35
    max_family_concentration: float = 0.45


@dataclass(frozen=True)
class SettlementSizingContext:
    # Settlement is evidence, never an execution authority.
    verified: bool = False
    outcome_id: str = ""
    decision_id: str = ""
    execution_id: str = ""
    receipt_id: str = ""
    realized_net_profit_usd: float | None = None
    expectation_error_usd: float | None = None


@dataclass(frozen=True)
class InstitutionalSizingContract:
    """Canonical input boundary for institutional sizing.

    This contract deliberately does not calculate a size. It normalizes the
    existing authorities and constraints so the future sizing kernel has one
    auditable input surface. No field here grants execution authority.
    """

    contract_version: str
    strategy_family: str
    capital_source: str
    requested_notional_usd: float
    target_notional_usd: float | None
    base_borrow_amount_wei: int
    max_borrow_amount_wei: int
    liquidity: LiquiditySizingContext
    execution: ExecutionSizingContext
    economics: EconomicsSizingContext
    capital: CapitalAuthoritySizingContext
    wealth_goal: WealthGoalSizingContext
    governance: GovernanceSizingContext
    settlement: SettlementSizingContext
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> tuple[bool, tuple[str, ...]]:
        errors: list[str] = []
        errors.extend(_validate_identity_and_notional(self))
        errors.extend(_validate_capital_authority(self.capital))
        errors.extend(_validate_governance(self.governance))
        errors.extend(_validate_economics(self.economics))
        errors.extend(_validate_wealth_goal(self.wealth_goal))
        errors.extend(_validate_prime_authority(self))
        if self.settlement.verified and not self.settlement.outcome_id:
            errors.append("settlement_outcome_id_missing")
        return (not errors, tuple(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _finite_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _dict(value: Any) -> dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _present(mapping: Mapping[str, Any], primary: str, fallback: str | None = None) -> Any:
    if primary in mapping:
        return mapping[primary]
    if fallback is not None and fallback in mapping:
        return mapping[fallback]
    return None


def _validate_identity_and_notional(contract: InstitutionalSizingContract) -> list[str]:
    errors: list[str] = []
    if not contract.strategy_family:
        errors.append("strategy_family_missing")
    if not contract.capital_source:
        errors.append("capital_source_missing")
    if contract.requested_notional_usd < 0 or not math.isfinite(contract.requested_notional_usd):
        errors.append("requested_notional_invalid")
    if contract.target_notional_usd is not None and (
        contract.target_notional_usd < 0 or not math.isfinite(contract.target_notional_usd)
    ):
        errors.append("target_notional_invalid")
    if contract.base_borrow_amount_wei < 0 or contract.max_borrow_amount_wei < 0:
        errors.append("borrow_amount_invalid")
    if contract.max_borrow_amount_wei and contract.base_borrow_amount_wei > contract.max_borrow_amount_wei:
        errors.append("base_borrow_exceeds_hard_cap")
    return errors


def _validate_capital_authority(capital: CapitalAuthoritySizingContext) -> list[str]:
    errors: list[str] = []
    if capital.source != "capital_engine_state":
        errors.append("capital_authority_source_invalid")
    if capital.status != "ok":
        errors.append("capital_authority_unavailable")
    if capital.freshness in {"stale", "unavailable"}:
        errors.append("capital_authority_stale")
    if capital.deployable_usd is None or not math.isfinite(capital.deployable_usd):
        errors.append("deployable_capital_missing")
    return errors


def _validate_governance(governance: GovernanceSizingContext) -> list[str]:
    errors: list[str] = []
    if not governance.admitted:
        errors.append("governance_not_admitted")
    if governance.hard_stop:
        errors.append("drawdown_hard_stop")
    if governance.kill_switch:
        errors.append("kill_switch_active")
    if governance.sandbox_only and governance.live_authority:
        errors.append("sandbox_live_authority_conflict")
    return errors


def _validate_economics(economics: EconomicsSizingContext) -> list[str]:
    errors: list[str] = []
    if economics.expected_net_profit_usd is None or not math.isfinite(economics.expected_net_profit_usd):
        errors.append("expected_net_profit_missing")
    if economics.success_probability is None or not math.isfinite(economics.success_probability):
        errors.append("success_probability_missing")
    elif economics.success_probability < 0 or economics.success_probability > 1:
        errors.append("success_probability_invalid")
    if economics.margin_ratio is None or not math.isfinite(economics.margin_ratio):
        errors.append("margin_ratio_missing")
    elif economics.margin_ratio < 0:
        errors.append("margin_ratio_invalid")
    return errors


def _validate_wealth_goal(goal: WealthGoalSizingContext) -> list[str]:
    errors: list[str] = []
    if goal.aggressiveness_cap <= 0 or not math.isfinite(goal.aggressiveness_cap):
        errors.append("aggressiveness_cap_invalid")
    if goal.max_drawdown_pct < 0 or goal.drawdown_pct < 0:
        errors.append("drawdown_invalid")
    return errors


def _validate_prime_authority(contract: InstitutionalSizingContract) -> list[str]:
    errors: list[str] = []
    if contract.capital_source == "internal_prime" and not contract.capital.prime_available:
        errors.append("internal_prime_unavailable")
    if contract.capital_source == "internal_prime" and contract.capital.prime_capacity_usd is None:
        errors.append("internal_prime_capacity_missing")
    return errors


def _build_liquidity_context(capture: Mapping[str, Any]) -> LiquiditySizingContext:
    return LiquiditySizingContext(
        available_usd=_finite_float(capture.get("available_usd") or capture.get("liquidity_available_usd")),
        depth_usd=_finite_float(capture.get("depth_usd") or capture.get("pool_depth_usd")),
        pool_depth_cap_usd=_finite_float(capture.get("pool_depth_cap_usd")),
        reserve_distortion=float(_finite_float(capture.get("reserve_distortion"), 0.0) or 0.0),
        liquidity_fragility=float(_finite_float(capture.get("liquidity_fragility"), 0.0) or 0.0),
        slippage_sensitivity=float(_finite_float(capture.get("slippage_sensitivity"), 0.0) or 0.0),
        provider_capacity_usd=_finite_float(capture.get("provider_capacity_usd")),
        route_capacity_usd=_finite_float(capture.get("route_capacity_usd")),
    )


def _build_execution_context(latency: Mapping[str, Any], capture: Mapping[str, Any]) -> ExecutionSizingContext:
    return ExecutionSizingContext(
        expected_pipeline_latency_ms=_finite_float(latency.get("pipeline_latency_ms") or capture.get("pipeline_latency_ms")),
        latency_half_life_ms=_finite_float(capture.get("latency_half_life_ms")),
        latency_pressure=float(_finite_float(latency.get("pressure") or capture.get("latency_pressure"), 0.0) or 0.0),
        endpoint_quality=float(_finite_float(latency.get("endpoint_quality") or capture.get("endpoint_quality"), 0.0) or 0.0),
        venue_reliability=float(_finite_float(capture.get("venue_reliability_score"), 0.0) or 0.0),
        simulation_confidence=float(_finite_float(capture.get("simulation_confidence"), 0.0) or 0.0),
        freshness_score=float(_finite_float(capture.get("freshness_score"), 0.0) or 0.0),
        private_send_preference=bool(capture.get("private_send_preference", False)),
    )


def _build_economics_context(econ: Mapping[str, Any]) -> EconomicsSizingContext:
    return EconomicsSizingContext(
        expected_gross_profit_usd=float(_finite_float(econ.get("expected_gross_profit_usd"), 0.0) or 0.0),
        expected_net_profit_usd=_finite_float(_present(econ, "expected_net_profit_usd", "expected_realized_pnl")),
        gas_cost_usd=float(_finite_float(econ.get("gas_cost_usd"), 0.0) or 0.0),
        borrow_cost_usd=float(_finite_float(econ.get("borrow_cost_usd"), 0.0) or 0.0),
        slippage_cost_usd=float(_finite_float(econ.get("slippage_cost_usd"), 0.0) or 0.0),
        latency_cost_usd=float(_finite_float(econ.get("latency_cost_usd") or econ.get("latency_decay_cost_usd"), 0.0) or 0.0),
        failure_cost_usd=float(_finite_float(econ.get("failure_cost_usd"), 0.0) or 0.0),
        min_profit_usd=float(_finite_float(econ.get("min_profit_usd"), 0.0) or 0.0),
        min_profit_bps=float(_finite_float(econ.get("min_profit_bps"), 0.0) or 0.0),
        success_probability=_finite_float(_present(econ, "success_probability", "p_success")),
        margin_ratio=_finite_float(econ.get("margin_ratio")),
    )


def _build_capital_context(
    cap: Mapping[str, Any], prime: Mapping[str, Any], strategy_family: str
) -> CapitalAuthoritySizingContext:
    family_exposure = _dict(prime.get("familyExposure"))
    family_caps = _dict(cap.get("family_caps_usd"))
    return CapitalAuthoritySizingContext(
        source="capital_engine_state",
        status=str(cap.get("status") or cap.get("capital_status") or "unavailable"),
        freshness=str(cap.get("freshness_class") or cap.get("freshness") or "unavailable"),
        authority_id=str(cap.get("authority_id") or ""),
        available_usd=_finite_float(cap.get("available_usd") or cap.get("availableUsd")),
        deployable_usd=_finite_float(cap.get("deployable_usd") or cap.get("deployableUsd")),
        reserve_usd=_finite_float(cap.get("reserve_usd") or cap.get("reserveUsd")),
        drawdown_buffer_usd=_finite_float(cap.get("drawdown_buffer_usd") or cap.get("drawdownBufferUsd")),
        borrowed_usd=float(_finite_float(prime.get("borrowedUsd"), 0.0) or 0.0),
        prime_available=bool(cap.get("internal_prime_available", cap.get("prime_available", False))) or bool(prime.get("stateReady", False)),
        prime_capacity_usd=_finite_float(prime.get("capacityUsd") or cap.get("prime_capacity_usd")),
        prime_utilization=float(_finite_float(prime.get("utilization"), 0.0) or 0.0),
        prime_reserved_usd=float(_finite_float(prime.get("reservedCollateralUsd"), 0.0) or 0.0),
        prime_family_exposure_usd=float(_finite_float(family_exposure.get(str(strategy_family)), 0.0) or 0.0),
        family_cap_usd=_finite_float(family_caps.get(str(strategy_family))),
    )


def _build_wealth_goal_context(goal: Mapping[str, Any]) -> WealthGoalSizingContext:
    return WealthGoalSizingContext(
        target_return_pct=float(_finite_float(goal.get("targetReturnPct") or goal.get("target_return_percentage"), 0.0) or 0.0),
        current_return_pct=float(_finite_float(goal.get("currentReturnPct") or goal.get("current_return_pct"), 0.0) or 0.0),
        capital_commitment_pct=float(_finite_float(goal.get("capitalCommitmentPct") or goal.get("capital_commitment_pct"), 25.0) or 25.0),
        aggressiveness_cap=float(_finite_float(goal.get("aggressivenessCap") or goal.get("aggressiveness_cap"), 1.0) or 1.0),
        max_drawdown_pct=float(_finite_float(goal.get("maxDrawdownPct") or goal.get("max_drawdown_pct"), 10.0) or 10.0),
        drawdown_pct=float(_finite_float(goal.get("drawdownPct") or goal.get("drawdown_pct"), 0.0) or 0.0),
        timeframe_days=max(1, int(goal.get("timeframeDays") or goal.get("timeframe_days") or 30)),
        goal_status=str(goal.get("goalStatus") or goal.get("goal_status") or "active"),
        pacing=str(goal.get("pacing") or "steady"),
        goal_horizon_compatibility=float(_finite_float(goal.get("goalHorizonCompatibility") or goal.get("goal_horizon_compatibility"), 1.0) or 1.0),
    )


def _build_governance_context(
    gov: Mapping[str, Any], strategy_family: str, capital_source: str
) -> GovernanceSizingContext:
    return GovernanceSizingContext(
        admitted=bool(gov.get("admitted", gov.get("allowed", False))),
        reason_code=str(gov.get("reason_code") or gov.get("reason") or "unavailable"),
        strategy_family=str(strategy_family or ""),
        capital_source=str(capital_source or ""),
        live_authority=bool(gov.get("live_authority", gov.get("liveAuthority", False))),
        execution_allowed=bool(gov.get("execution_allowed", gov.get("executionAllowed", False))),
        hard_stop=bool(gov.get("hard_stop", gov.get("hardStop", False))),
        kill_switch=bool(gov.get("kill_switch", gov.get("killSwitch", False))),
        sandbox_only=bool(gov.get("sandbox_only", gov.get("sandboxOnly", False))),
        defensive_mode=bool(gov.get("defensive_mode", gov.get("defensiveMode", False))),
        max_deployable_pct=float(_finite_float(gov.get("max_deployable_pct"), 0.35) or 0.35),
        max_family_concentration=float(_finite_float(gov.get("max_family_concentration"), 0.45) or 0.45),
    )


def _build_settlement_context(settled: Mapping[str, Any]) -> SettlementSizingContext:
    return SettlementSizingContext(
        verified=bool(settled.get("verified", settled.get("settlement_verified", False))),
        outcome_id=str(settled.get("outcome_id") or settled.get("outcomeId") or ""),
        decision_id=str(settled.get("decision_id") or settled.get("decisionId") or ""),
        execution_id=str(settled.get("execution_id") or settled.get("executionId") or ""),
        receipt_id=str(settled.get("receipt_id") or settled.get("receiptId") or ""),
        realized_net_profit_usd=_finite_float(settled.get("realized_net_profit_usd") or settled.get("realizedNetProfitUsd")),
        expectation_error_usd=_finite_float(settled.get("expectation_error_usd") or settled.get("expectationErrorUsd")),
    )


def build_institutional_sizing_contract(
    *,
    requested_notional_usd: float,
    strategy_family: str,
    capital_source: str,
    capital_engine_state: Mapping[str, Any],
    treasury_state: Mapping[str, Any] | None = None,
    internal_prime_state: Mapping[str, Any] | None = None,
    wealth_goal_state: Mapping[str, Any] | None = None,
    execution_capture: Mapping[str, Any] | None = None,
    latency_state: Mapping[str, Any] | None = None,
    economics: Mapping[str, Any] | None = None,
    governance: Mapping[str, Any] | None = None,
    settlement: Mapping[str, Any] | None = None,
    base_borrow_amount_wei: int = 0,
    max_borrow_amount_wei: int = 0,
    target_notional_usd: float | None = None,
) -> InstitutionalSizingContract:
    cap = _dict(capital_engine_state)
    prime = _dict(internal_prime_state)
    goal_root = _dict(wealth_goal_state)
    goal = _dict(goal_root.get("state") or goal_root)
    capture = _dict(execution_capture)
    latency = _dict(latency_state)
    econ = _dict(economics)
    gov = _dict(governance)
    settled = _dict(settlement)
    _dict(treasury_state)

    return InstitutionalSizingContract(
        contract_version="institutional_sizing_v1",
        strategy_family=str(strategy_family or ""),
        capital_source=str(capital_source or ""),
        requested_notional_usd=float(requested_notional_usd or 0.0),
        target_notional_usd=_finite_float(target_notional_usd),
        base_borrow_amount_wei=max(0, int(base_borrow_amount_wei or 0)),
        max_borrow_amount_wei=max(0, int(max_borrow_amount_wei or 0)),
        liquidity=_build_liquidity_context(capture),
        execution=_build_execution_context(latency, capture),
        economics=_build_economics_context(econ),
        capital=_build_capital_context(cap, prime, strategy_family),
        wealth_goal=_build_wealth_goal_context(goal),
        governance=_build_governance_context(gov, strategy_family, capital_source),
        settlement=_build_settlement_context(settled),
        metadata={
            "tier_candidates": [dict(x) for x in INSTITUTIONAL_V1_TIERS],
            "treasury_state_source": "capital_engine_state",
            "prime_state_source": "internal_prime_state",
            "settlement_source": "canonical_settlement",
            "behavior_change": "none",
        },
    )
