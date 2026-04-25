from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.outcomes import ExecutionOutcome

from .runtime_context import AdmissionContext, build_admission_context
from victor_ai_bot.capital_family_policy import resolve_family_capital_limit


@dataclass(frozen=True)
class AdmissionFailure:
    code: str
    reason: str


class AdmissionPreparationError(RuntimeError):
    """Raised when execution-capture admission cannot be prepared safely."""


@dataclass(frozen=True)
class AdmissionResult:
    opportunity: Any
    capture_decision: Any | None
    route_family: str
    strategy_family: str
    metadata: Dict[str, Any]
    failure: AdmissionFailure | None = None


class AdmissionService:
    def prepare_capture(
        self, runtime: Any, opp: Any, *, context: AdmissionContext | None = None
    ) -> AdmissionResult:
        ctx = context or build_admission_context(runtime, opp)
        if not isinstance(getattr(opp, "meta", None), dict):
            opp.meta = {}
        opp.meta["pending_state"] = ctx.pending_state
        opp.meta["pending_context"] = ctx.pending_context
        if ctx.wealth_goal:
            opp.meta["wealth_goal"] = ctx.wealth_goal
        if ctx.drawdown_state:
            opp.meta["drawdown_state"] = ctx.drawdown_state
        if ctx.kill_switch_state:
            opp.meta["kill_switch_state"] = ctx.kill_switch_state
        if ctx.treasury_state:
            opp.meta["treasury_state"] = ctx.treasury_state

        capture_decision = None
        capture_payload: Dict[str, Any] = {}
        if getattr(runtime, "_capture_engine", None) is not None:
            try:
                capture_decision = runtime._capture_engine.evaluate(
                    opp,
                    chain_id=ctx.chain_id,
                    regime=ctx.regime,
                    public_mode=ctx.public_mode,
                    force_send_mode=ctx.force_send_mode,
                )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise AdmissionPreparationError(f"capture_engine_evaluate_failed:{exc}") from exc
            capture_payload = (
                capture_decision.to_dict() if hasattr(capture_decision, "to_dict") else {}
            )
            opp.meta["capture"] = capture_payload
            opp.meta["route_family"] = str(
                ((capture_payload.get("metadata") or {}).get("envelope") or {}).get("route_family")
                or opp.meta.get("route_family")
                or ""
            )
            opp.meta["regime"] = str(ctx.regime or "balanced")
            opp.meta["execution_lane"] = str(
                capture_payload.get("lane") or opp.meta.get("execution_lane") or ""
            )
            if getattr(capture_decision, "action", "trade") == "drop":
                saf = (
                    dict(opp.meta.get("safety") or {})
                    if isinstance(opp.meta.get("safety"), dict)
                    else {}
                )
                saf["exec_ready"] = False
                opp.meta["safety"] = saf
        route_family = str(
            (((opp.meta.get("capture") or {}).get("metadata") or {}).get("envelope") or {}).get(
                "route_family"
            )
            or opp.meta.get("route_family")
            or ""
        )
        strategy_family = (
            str(opp.meta.get("strategy_family") or "flashloan_atomic") or "flashloan_atomic"
        )
        return AdmissionResult(
            opportunity=opp,
            capture_decision=capture_decision,
            route_family=route_family,
            strategy_family=strategy_family,
            metadata={
                "force_send_mode": ctx.force_send_mode,
                "admission_context": ctx,
                "capture_payload": capture_payload,
            },
        )

    def gate_capture_drop(
        self, runtime: Any, opp: Any, capture_decision: Any | None, *, force_dry_run: bool = False
    ) -> ExecResult | None:
        if capture_decision is None or getattr(capture_decision, "action", "trade") != "drop":
            return None
        try:
            if getattr(runtime, "_no_trade_analytics", None) is not None:
                runtime._no_trade_analytics.observe(
                    admitted=False,
                    projected_edge_usd=float(
                        getattr(capture_decision, "expected_realized_value", 0.0) or 0.0
                    ),
                    actual_edge_usd=0.0,
                )
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            if getattr(runtime, "_telemetry_service", None) is not None:
                runtime._telemetry_service.record_decision(
                    route_family=str(
                        (
                            (
                                (
                                    capture_decision.to_dict()
                                    if hasattr(capture_decision, "to_dict")
                                    else {}
                                ).get("metadata")
                                or {}
                            ).get("envelope")
                            or {}
                        ).get("route_family")
                        or ""
                    ),
                    strategy_family=str(
                        (getattr(opp, "meta", {}) or {}).get("strategy_family")
                        or "flashloan_atomic"
                    ),
                    projected_realized_edge_usd=float(
                        getattr(capture_decision, "expected_realized_value", 0.0) or 0.0
                    ),
                    actual_realized_edge_usd=0.0,
                    ok=False,
                    dropped=True,
                    false_drop=0.0,
                    reward_trace={"reward": 0.0},
                    chain=str(runtime.cfg.chain.name),
                    decision_reason=str(
                        getattr(capture_decision, "drop_reason", "dropped") or "dropped"
                    ),
                )
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        return ExecResult(
            False,
            bool(runtime.cfg.execution.dry_run or force_dry_run),
            f"capture:{getattr(capture_decision, 'drop_reason', 'dropped')}",
            attempted=False,
            plan={
                "capture": (
                    capture_decision.to_dict() if hasattr(capture_decision, "to_dict") else {}
                )
            },
        )

    def apply_family_budget(
        self, runtime: Any, opp: Any, capture_decision: Any | None, *, force_dry_run: bool = False
    ) -> tuple[Any, ExecResult | None]:
        if capture_decision is None:
            return opp, None
        try:
            fam = str((getattr(opp, "meta", {}) or {}).get("strategy_family") or "flashloan_atomic")
            cap_state = runtime.capital_engine_state()
            family_limit = resolve_family_capital_limit(
                capital_engine=(cap_state.get("capital_engine") or {}),
                family=fam,
            )
            fam_target = float(family_limit.get("family_target") or 0.0)
            size_mult = float(getattr(capture_decision, "size_mult", 1.0) or 1.0)
            if not bool(family_limit.get("target_known", False)):
                return opp, ExecResult(
                    False,
                    bool(runtime.cfg.execution.dry_run or force_dry_run),
                    "capital:family_target_unresolved",
                    attempted=False,
                    plan={
                        "capture": (
                            capture_decision.to_dict()
                            if hasattr(capture_decision, "to_dict")
                            else {}
                        ),
                        "family_limit": family_limit,
                    },
                )
            if fam_target <= 0.02:
                return opp, ExecResult(
                    False,
                    bool(runtime.cfg.execution.dry_run or force_dry_run),
                    "capital:family_target_zero",
                    attempted=False,
                    plan={
                        "capture": (
                            capture_decision.to_dict()
                            if hasattr(capture_decision, "to_dict")
                            else {}
                        ),
                        "family_limit": family_limit,
                    },
                )
            size_mult = min(1.0, size_mult * max(0.35, min(1.0, fam_target * 1.8)))
            wealth = dict(
                (((getattr(opp, "meta", {}) or {}).get("wealth_goal") or {}).get("state") or {})
                if isinstance(getattr(opp, "meta", None), dict)
                else {}
            )
            goal_cap = float(wealth.get("aggressivenessCap") or 1.0)
            size_mult *= max(0.35, min(1.25, goal_cap))
            if size_mult != 1.0:
                opp = runtime._scale_opportunity(opp, size_mult)
        except (AttributeError, KeyError, TypeError, ValueError):
            return opp, None
        return opp, None

    def apply_control_and_risk_gates(
        self, runtime: Any, opp: Any, capture_decision: Any | None, *, force_dry_run: bool = False
    ) -> tuple[Any, bool, ExecResult | None, Dict[str, Any]]:
        metadata: Dict[str, Any] = {}
        try:
            c = getattr(getattr(runtime, "_cc", None), "controls", None)
            if c is not None and bool(getattr(c, "paused", False)):
                return (
                    opp,
                    force_dry_run,
                    ExecResult(False, True, "cc_paused", attempted=False),
                    metadata,
                )
            if c is not None and bool(getattr(c, "sandbox_only", False)):
                force_dry_run = True
            if c is not None and (
                bool(getattr(c, "defensive_mode", False))
                or bool(getattr(c, "reduce_exposure_half", False))
            ):
                opp = runtime._scale_opportunity(opp, 0.5)
                metadata["defensiveClamp"] = True
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        try:
            route_family = str(
                (((getattr(opp, "meta", {}) or {}).get("capture") or {}).get("metadata") or {})
                .get("envelope", {})
                .get("route_family")
                if isinstance(getattr(opp, "meta", None), dict)
                else ""
            )
            if not route_family:
                route_family = str(
                    (getattr(opp, "meta", {}) or {}).get("route_family")
                    if isinstance(getattr(opp, "meta", None), dict)
                    else ""
                )
            strategy_family = str(
                (getattr(opp, "meta", {}) or {}).get("strategy_family")
                if isinstance(getattr(opp, "meta", None), dict)
                else "flashloan_atomic"
            )
            venue = str(
                (
                    list(getattr(getattr(opp, "route", None), "legs", []) or [None])[0].venue
                    if list(getattr(getattr(opp, "route", None), "legs", []) or [])
                    else ""
                )
            )
            endpoint_pressure = (
                float(
                    (((getattr(opp, "meta", {}) or {}).get("capture") or {}).get("metadata") or {})
                    .get("endpoint_selection", {})
                    .get("pressure", 0.0)
                )
                if isinstance(getattr(opp, "meta", None), dict)
                else 0.0
            )
            drawdown_gate = (
                getattr(runtime, "_drawdown_state", None).gate(family=strategy_family)
                if getattr(runtime, "_drawdown_state", None) is not None
                else {"allowed": True, "aggressiveness_cap": 1.0, "reason_codes": []}
            )
            metadata["drawdownGate"] = drawdown_gate
            if not bool(drawdown_gate.get("allowed", True)):
                return (
                    opp,
                    force_dry_run,
                    ExecResult(
                        False,
                        bool(runtime.cfg.execution.dry_run or force_dry_run),
                        f"drawdown_gate:{','.join(list(drawdown_gate.get('reason_codes') or []))}",
                        attempted=False,
                    ),
                    metadata,
                )
            if float(drawdown_gate.get("aggressiveness_cap", 1.0) or 1.0) < 0.999:
                opp = runtime._scale_opportunity(
                    opp, float(drawdown_gate.get("aggressiveness_cap", 1.0) or 1.0)
                )
            ks = (
                getattr(runtime, "_kill_switch", None).evaluate(
                    family=strategy_family,
                    route_family=route_family,
                    venue=venue,
                    chain=str(runtime.cfg.chain.name),
                    drawdown_gate=drawdown_gate,
                    endpoint_pressure=endpoint_pressure,
                )
                if getattr(runtime, "_kill_switch", None) is not None
                else {"allowed": True, "reason_codes": []}
            )
            metadata["killSwitch"] = ks
            if not bool(ks.get("allowed", True)):
                return (
                    opp,
                    force_dry_run,
                    ExecResult(
                        False,
                        bool(runtime.cfg.execution.dry_run or force_dry_run),
                        f"kill_switch:{','.join(list(ks.get('reason_codes') or []))}",
                        attempted=False,
                    ),
                    metadata,
                )
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
        return opp, force_dry_run, None, metadata

    def outcome_for_rejection(
        self, *, reason_code: str, retryable: bool = False, degraded_mode: str = ""
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            status="dropped",
            reason_code=str(reason_code),
            retryable=bool(retryable),
            degraded_mode=str(degraded_mode or ""),
            details={},
        )

    def summarize(self, runtime: Any) -> Dict[str, Any]:
        latest = (
            runtime.execution_live_state()
            if hasattr(runtime, "execution_live_state")
            else {"items": []}
        )
        items = list((latest.get("items") or []) if isinstance(latest, dict) else [])
        top = items[-1] if items else {}
        return {
            "ok": True,
            "lastRouteFamily": str(top.get("routeFamily") or ""),
            "lastLane": str(top.get("lane") or ""),
            "fallbackReady": bool(top.get("fallbackReady", False)),
            "routeExecutable": bool(top.get("routeExecutable", True)),
            "drawdownHardStop": bool(
                (
                    (runtime.drawdown_state() if hasattr(runtime, "drawdown_state") else {}).get(
                        "hardStop"
                    )
                    or {}
                ).get("active", False)
            ),
        }
