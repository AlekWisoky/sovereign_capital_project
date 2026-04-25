from __future__ import annotations

from typing import Any, Dict

from .capability_registry import EngineCapabilityRegistry
from .degradation_policy import degradation_mode_for
from .models import EngineAdmissionDecision, EngineOpportunity


class EngineAdmissionGovernor:
    def __init__(self, registry: EngineCapabilityRegistry):
        self.registry = registry

    def decide(
        self,
        *,
        opportunity: EngineOpportunity,
        env_mode: str,
        telemetry_points: int,
        calibration_points: int,
        treasury_state: Dict[str, Any] | None = None,
    ) -> EngineAdmissionDecision:
        cap = self.registry.get(opportunity.engine_type)
        degradation = degradation_mode_for(
            confidence=float(opportunity.confidence),
            telemetry_points=int(telemetry_points),
            calibration_points=int(calibration_points),
            risk_flags=list(opportunity.risk_flags or []),
        )
        allowed_stage = str(opportunity.lifecycle_eligibility or "sandbox")
        if env_mode not in set(cap.allowed_envs):
            return EngineAdmissionDecision(
                False,
                "disabled",
                "environment_disallowed",
                0.0,
                0.0,
                telemetry_points >= cap.required_telemetry_points,
                calibration_points >= 10,
                cap.maturity,
            )
        if allowed_stage not in set(cap.allowed_lifecycle_stages):
            return EngineAdmissionDecision(
                False,
                "disabled",
                "lifecycle_stage_disallowed",
                0.0,
                0.0,
                telemetry_points >= cap.required_telemetry_points,
                calibration_points >= 10,
                cap.maturity,
            )
        if float(opportunity.confidence) < float(cap.required_confidence):
            return EngineAdmissionDecision(
                False,
                "observe_only",
                "confidence_below_threshold",
                0.0,
                0.0,
                telemetry_points >= cap.required_telemetry_points,
                calibration_points >= 10,
                cap.maturity,
            )
        treasury_state = dict(treasury_state or {})
        capital_engine = dict(treasury_state.get("capital_engine") or {})
        deployable_usd = float(capital_engine.get("deployable_bankroll_wei") or 0.0) / 1e18
        if deployable_usd <= 0.0:
            deployable_usd = float(treasury_state.get("estimated_capital_usd") or 0.0)
        max_capital = max(0.0, deployable_usd * float(cap.max_capital_pct))
        mode = opportunity.policy_eligibility or degradation
        if degradation == "disabled":
            return EngineAdmissionDecision(
                False,
                "disabled",
                "degradation_disabled",
                max_capital,
                0.0,
                telemetry_points >= cap.required_telemetry_points,
                calibration_points >= 10,
                cap.maturity,
            )
        if mode == "live" and degradation != "live":
            mode = degradation
        if float(opportunity.capital_required_usd) > max_capital and max_capital > 0.0:
            mode = "capped_live" if mode == "live" else mode
        if opportunity.engine_type == "cross_chain_arb" and mode == "live":
            mode = "capped_live"
        if opportunity.engine_type == "mev_search" and "public_send" in set(
            opportunity.risk_flags or []
        ):
            return EngineAdmissionDecision(
                False,
                "disabled",
                "public_send_disallowed_for_mev",
                max_capital,
                0.0,
                telemetry_points >= cap.required_telemetry_points,
                calibration_points >= 10,
                cap.maturity,
            )
        allowed = mode not in {"disabled"}
        return EngineAdmissionDecision(
            allowed,
            mode,
            "ok" if allowed else "disabled",
            max_capital,
            (
                min(
                    float(cap.max_size_mult),
                    max(0.10, max_capital / max(1.0, float(opportunity.capital_required_usd))),
                )
                if allowed
                else 0.0
            ),
            telemetry_points >= cap.required_telemetry_points,
            calibration_points >= 10,
            cap.maturity,
            {"degradation": degradation, "execution_permission": cap.execution_permission},
        )
