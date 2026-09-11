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
    expected_net_profit_usd: float = 0.0
    gas_cost_usd: float = 0.0
    borrow_cost_usd: float = 0.0
    slippage_cost_usd: float = 0.0
    latency_cost_usd: float = 0.0
    failure_cost_usd: float = 0.0
    min_profit_usd: float = 0.0
    min_profit_bps: float = 0.0
    success_probability: float = 0.0
    margin_ratio: float = 0.0


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

        if not self.strategy_family:
            errors.append("strategy_family_missing")
        if not self.capital_source:
            errors.append("capital_source_missing")
        if self.requested_notional_usd < 0 or not math.isfinite(self.requested_notional_usd):
            errors.append("requested_notional_invalid")
        if self.target_notional_usd is not None and (
            self.target_notional_usd < 0 or not math.isfinite(self.target_notional_usd)
        ):
            errors.append("target_notional_invalid")
        if self.base_borrow_amount_wei < 0 or self.max_borrow_amount_wei < 0:
            errors.append("borrow_amount_invalid")
        if self.max_borrow_amount_wei and self.base_borrow_amount_wei > self.max_borrow_amount_wei:
            errors.append("base_borrow_exceeds_hard_cap")

        if self.capital.source != "capital_engine_state":
            errors.append("capital_authority_source_invalid")
        if self.capital.status != "ok":
            errors.append("capital_authority_unavailable")
        if self.capital.freshness in {"stale", "unavailable"}:
            errors.append("capital_authority_stale")
        if self.capital.deployable_usd is None or not math.isfinite(self.capital.deployable_usd):
            errors.append("deployable_capital_missing")

        if not self.governance.admitted:
            errors.append("governance_not_admitted")
        if self.governance.hard_stop:
            errors.append("drawdown_hard_stop")
        if self.governance.kill_switch:
            errors.append("kill_switch_active")
        if self.governance.sandbox_only and self.governance.live_authority:
            errors.append("sandbox_live_authority_conflict")

        if self.economics.success_probability < 0 or self.economics.success_probability > 1:
            errors.append("success_probability_invalid")
        if self.economics.margin_ratio < 0:
            errors.append("margin_ratio_invalid")
        if self.wealth_goal.aggressiveness_cap <= 0 or not math.isfinite(self.wealth_goal.aggressiveness_cap):
            errors.append("aggressiveness_cap_invalid")
        if self.wealth_goal.max_drawdown_pct < 0 or self.wealth_goal.drawdown_pct < 0:
            errors.append("drawdown_invalid")

        if self.capital_source == "internal_prime" and not self.capital.prime_available:
            errors.append("internal_prime_unavailable")
        if self.capital_source == "internal_prime" and self.capital.prime_capacity_usd is None:
            errors.append("internal_prime_capacity_missing")

        # Realized settlement values may inform later calibration, but cannot
        # be used to authorize a new trade.
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
    treasury = _dict(treasury_state)
    prime = _dict(internal_prime_state)
    goal_root = _dict(wealth_goal_state)
    goal = _dict(goal_root.get("state") or goal_root)
    capture = _dict(execution_capture)
    latency = _dict(latency_state)
    econ = _dict(economics)
    gov = _dict(governance)
    settled = _dict(settlement)

    contract = InstitutionalSizingContract(
        contract_version="institutional_sizing_v1",
        strategy_family=str(strategy_family or ""),
        capital_source=str(capital_source or ""),
        requested_notional_usd=float(requested_notional_usd or 0.0),
        target_notional_usd=_finite_float(target_notional_usd),
        base_borrow_amount_wei=max(0, int(base_borrow_amount_wei or 0)),
        max_borrow_amount_wei=max(0, int(max_borrow_amount_wei or 0)),
        liquidity=LiquiditySizingContext(
            available_usd=_finite_float(capture.get("available_usd") or capture.get("liquidity_available_usd")),
            depth_usd=_finite_float(capture.get("depth_usd") or capture.get("pool_depth_usd")),
            pool_depth_cap_usd=_finite_float(capture.get("pool_depth_cap_usd")),
            reserve_distortion=float(_finite_float(capture.get("reserve_distortion"), 0.0) or 0.0),
            liquidity_fragility=float(_finite_float(capture.get("liquidity_fragility"), 0.0) or 0.0),
            slippage_sensitivity=float(_finite_float(capture.get("slippage_sensitivity"), 0.0) or 0.0),
            provider_capacity_usd=_finite_float(capture.get("provider_capacity_usd")),
            route_capacity_usd=_finite_float(capture.get("route_capacity_usd")),
        ),
        execution=ExecutionSizingContext(
            expected_pipeline_latency_ms=_finite_float(latency.get("pipeline_latency_ms") or capture.get("pipeline_latency_ms")),
            latency_half_life_ms=_finite_float(capture.get("latency_half_life_ms")),
            latency_pressure=float(_finite_float(latency.get("pressure") or capture.get("latency_pressure"), 0.0) or 0.0),
            endpoint_quality=float(_finite_float(latency.get("endpoint_quality") or capture.get("endpoint_quality"), 0.0) or 0.0),
            venue_reliability=float(_finite_float(capture.get("venue_reliability_score"), 0.0) or 0.0),
            simulation_confidence=float(_finite_float(capture.get("simulation_confidence"), 0.0) or 0.0),
            freshness_score=float(_finite_float(capture.get("freshness_score"), 0.0) or 0.0),
            private_send_preference=bool(capture.get("private_send_preference", False)),
        ),
        economics=EconomicsSizingContext(
            expected_gross_profit_usd=float(_finite_float(econ.get("expected_gross_profit_usd"), 0.0) or 0.0),
            expected_net_profit_usd=float(_finite_float(econ.get("expected_net_profit_usd") or econ.get("expected_realized_pnl"), 0.0) or 0.0),
            gas_cost_usd=float(_finite_float(econ.get("gas_cost_usd"), 0.0) or 0.0),
            borrow_cost_usd=float(_finite_float(econ.get("borrow_cost_usd"), 0.0) or 0.0),
            slippage_cost_usd=float(_finite_float(econ.get("slippage_cost_usd"), 0.0) or 0.0),
            latency_cost_usd=float(_finite_float(econ.get("latency_cost_usd") or econ.get("latency_decay_cost_usd"), 0.0) or 0.0),
            failure_cost_usd=float(_finite_float(econ.get("failure_cost_usd"), 0.0) or 0.0),
            min_profit_usd=float(_finite_float(econ.get("min_profit_usd"), 0.0) or 0.0),
            min_profit_bps=float(_finite_float(econ.get("min_profit_bps"), 0.0) or 0.0),
            success_probability=float(_finite_float(econ.get("success_probability") or econ.get("p_success"), 0.0) or 0.0),
            margin_ratio=float(_finite_float(econ.get("margin_ratio"), 0.0) or 0.0),
        ),
        capital=CapitalAuthoritySizingContext(
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
            prime_family_exposure_usd=float(_finite_float(_dict(prime.get("familyExposure")).get(str(strategy_family)), 0.0) or 0.0),
            family_cap_usd=_finite_float(_dict(cap.get("family_caps_usd")).get(str(strategy_family))),
        ),
        wealth_goal=WealthGoalSizingContext(
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
        ),
        governance=GovernanceSizingContext(
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
        ),
        settlement=SettlementSizingContext(
            verified=bool(settled.get("verified", settled.get("settlement_verified", False))),
            outcome_id=str(settled.get("outcome_id") or settled.get("outcomeId") or ""),
            decision_id=str(settled.get("decision_id") or settled.get("decisionId") or ""),
            execution_id=str(settled.get("execution_id") or settled.get("executionId") or ""),
            receipt_id=str(settled.get("receipt_id") or settled.get("receiptId") or ""),
            realized_net_profit_usd=_finite_float(settled.get("realized_net_profit_usd") or settled.get("realizedNetProfitUsd")),
            expectation_error_usd=_finite_float(settled.get("expectation_error_usd") or settled.get("expectationErrorUsd")),
        ),
        metadata={
            "tier_candidates": [dict(x) for x in INSTITUTIONAL_V1_TIERS],
            "treasury_state_source": "capital_engine_state",
            "prime_state_source": "internal_prime_state",
            "settlement_source": "canonical_settlement",
            "behavior_change": "none",
        },
    )
    return contract
