from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from .adversarial_state import evaluate_adversarial_state
from .aging import aging_factor
from .envelope import build_opportunity_envelope
from .flashloan_hardening import evaluate_flashloan_resilience
from .flashloan_sizing import choose_flashloan_size
from .route_execution_plan import build_execution_route_plan
from .lane_priors import default_lane_priors
from .lanes import select_lane
from .models import ExecutionDecision, ExecutionLane
from .policies import ExecutionCapturePolicy
from .route_family_priors import default_route_family_priors
from .scoring import compute_capture_score
from .simulation_realism import simulate_execution_realism
from .sizing import choose_size
from .smart_order_router import plan_route
from .telemetry import ExecutionTelemetryStore
from .template_cache import RouteTemplateCache
from ..regime_engine import regime_adjustments


class ExecutionDecisionEngine:
    def __init__(
        self,
        *,
        telemetry: ExecutionTelemetryStore,
        template_cache: RouteTemplateCache,
        policy: Optional[ExecutionCapturePolicy] = None,
    ):
        self.telemetry = telemetry
        self.template_cache = template_cache
        self.policy = policy or ExecutionCapturePolicy()
        self.calibration_store = None
        self.venue_profiles = None
        self.risk_memory = None
        self.path_diversity = None
        self.edge_learning = None
        self.endpoint_quality = None
        self.endpoint_universe = None
        self.venue_scorecards = None
        self.route_quality = None

    def evaluate(
        self,
        opp: Any,
        *,
        chain_id: int,
        regime: str = "unknown",
        public_mode: bool = False,
        force_send_mode: str = "",
    ) -> ExecutionDecision:
        envelope = build_opportunity_envelope(opp, chain_id=chain_id, regime=regime)
        template = self.template_cache.get(str(envelope.route_id or envelope.route_family))
        template_hit = bool(template)
        age_ms = int(
            (
                (
                    (getattr(opp, "meta", {}) or {}).get("age_ms")
                    if isinstance(getattr(opp, "meta", None), dict)
                    else 0
                )
                or 0
            )
        )
        age_factor = aging_factor(route_family=str(envelope.route_family), age_ms=age_ms)
        envelope = replace(
            envelope,
            expected_profit_usd=float(envelope.expected_profit_usd) * age_factor,
            freshness_score=max(
                0.05,
                min(1.0, float(envelope.freshness_score) * age_factor + (1.0 - age_factor) * 0.25),
            ),
        )
        if getattr(self, "venue_profiles", None) is not None:
            vp = self.venue_profiles.combined_profile(envelope.venues)
            envelope = replace(
                envelope,
                venue_reliability_score=max(
                    0.2,
                    min(
                        1.2,
                        (
                            float(envelope.venue_reliability_score)
                            + float(
                                vp.get("venue_reliability_score", envelope.venue_reliability_score)
                            )
                        )
                        / 2.0,
                    ),
                ),
            )
        priors = default_route_family_priors(envelope.route_family)
        reg_adj = regime_adjustments(
            route_family=str(envelope.route_family), regime=str(regime or "balanced")
        )
        preferred_lane = str(reg_adj.get("preferred_lane") or "")
        lane_hint = str(
            force_send_mode or preferred_lane or priors.get("best_lane") or "PUBLIC"
        ).upper()
        telemetry = self.telemetry.combined_feedback(
            route_family=envelope.route_family, venues=envelope.venues, lane=lane_hint
        )

        lane_endpoints: List[str] = []
        lane_relays: List[str] = []
        endpoint_choice = {
            "endpoint": "",
            "relay": "",
            "endpoint_quality": 0.55,
            "pressure": 0.15,
            "pressure_class": "unknown",
            "measured_latency_ms": 850.0,
            "candidates": [],
            "relay_candidates": [],
            "universe": {},
        }
        if getattr(self, "endpoint_quality", None) is not None:
            universe = (
                getattr(self, "endpoint_universe", None).candidates(lane=lane_hint)
                if getattr(self, "endpoint_universe", None) is not None
                else {"candidates": [], "relays": [], "reason": "unknown"}
            )
            lane_endpoints = [
                str(x.get("url") or x.get("endpoint") or "")
                for x in list(universe.get("candidates") or [])
                if str(x.get("url") or x.get("endpoint") or "")
            ]
            lane_relays = [
                str(x.get("url") or x.get("endpoint") or "")
                for x in list(universe.get("relays") or [])
                if str(x.get("url") or x.get("endpoint") or "")
            ]
            if not lane_endpoints:
                lane_endpoints = list(
                    ((template.get("metadata") or {}).get("candidate_endpoints") or [])
                )
            if not lane_endpoints:
                lane_endpoints = list(
                    (
                        (
                            (getattr(opp, "meta", {}) or {}).get("candidate_endpoints")
                            if isinstance(getattr(opp, "meta", None), dict)
                            else []
                        )
                        or []
                    )
                )
            if not lane_relays:
                lane_relays = list(
                    (
                        (
                            (getattr(opp, "meta", {}) or {}).get("candidate_relays")
                            if isinstance(getattr(opp, "meta", None), dict)
                            else []
                        )
                        or []
                    )
                )
            endpoint_choice = self.endpoint_quality.choose(
                lane=lane_hint, endpoints=lane_endpoints or ["default_rpc"], relays=lane_relays
            )
            endpoint_choice["universe"] = universe
            endpoint_choice["reason"] = str(
                universe.get("reason") or endpoint_choice.get("pressure_class") or "quality_ranked"
            )
            telemetry = dict(telemetry or {})
            telemetry["lane_avg_latency_ms"] = float(
                endpoint_choice.get("measured_latency_ms") or 0.0
            )
            telemetry["endpoint_quality"] = float(endpoint_choice.get("endpoint_quality") or 0.55)
            telemetry["latency_pressure"] = float(endpoint_choice.get("pressure") or 0.0)

        calibration = {}
        if getattr(self, "calibration_store", None) is not None:
            calibration = self.calibration_store.priors(
                route_family=envelope.route_family,
                lane=str(force_send_mode or priors.get("best_lane") or "PUBLIC").upper(),
                regime=str(regime or ""),
            )
        capture = compute_capture_score(envelope, telemetry)
        edge_pred = None
        if getattr(self, "edge_learning", None) is not None:
            try:
                edge_pred = self.edge_learning.predict(
                    envelope=envelope,
                    regime=str(regime or "balanced"),
                    lane_hint=str(force_send_mode or priors.get("best_lane") or "PUBLIC").upper(),
                    telemetry=telemetry,
                )
                capture = replace(
                    capture,
                    success_probability=max(
                        0.05,
                        min(
                            0.995,
                            float(capture.success_probability)
                            * float(edge_pred.success_probability),
                        ),
                    ),
                    freshness_probability=max(
                        0.05,
                        min(
                            0.995,
                            float(capture.freshness_probability)
                            * float(edge_pred.freshness_decay_factor),
                        ),
                    ),
                    expected_realized_pnl=float(capture.expected_realized_pnl)
                    * float(edge_pred.quality_adjustment_factor)
                    * float(edge_pred.reliability_factor)
                    * (1.0 - float(edge_pred.competition_probability)),
                    expected_realized_value=float(capture.expected_realized_value)
                    * float(edge_pred.quality_adjustment_factor)
                    * float(edge_pred.reliability_factor)
                    * (1.0 - float(edge_pred.competition_probability)),
                    capture_score=float(capture.capture_score)
                    * float(edge_pred.quality_adjustment_factor)
                    * float(edge_pred.reliability_factor)
                    * (1.0 - float(edge_pred.competition_probability)),
                    slippage_cost_estimate=float(capture.slippage_cost_estimate)
                    + max(0.0, float(edge_pred.expected_slippage_bias)),
                    telemetry_adjustments=dict(capture.telemetry_adjustments or {})
                    | {
                        "edge_success_probability": float(edge_pred.success_probability),
                        "edge_competition_probability": float(edge_pred.competition_probability),
                        "edge_quality_adjustment_factor": float(
                            edge_pred.quality_adjustment_factor
                        ),
                        "edge_freshness_decay_factor": float(edge_pred.freshness_decay_factor),
                        "edge_reliability_factor": float(edge_pred.reliability_factor),
                        "edge_data_sufficiency": float(edge_pred.data_sufficiency),
                    },
                )
            except (AttributeError, TypeError, ValueError):
                edge_pred = None
        realism = simulate_execution_realism(
            envelope=envelope,
            telemetry=telemetry,
            regime=str(regime or "balanced"),
            lane_hint=(force_send_mode or preferred_lane),
        )
        realism_mult = max(
            0.30,
            min(
                1.10,
                float(realism.get("success_multiplier", 1.0))
                * float(realism.get("freshness_multiplier", 1.0))
                * float(realism.get("non_interference_multiplier", 1.0))
                * float(reg_adj.get("value_multiplier", 1.0)),
            ),
        )
        capture = replace(
            capture,
            success_probability=max(
                0.05,
                min(
                    0.995,
                    float(capture.success_probability)
                    * float(realism.get("success_multiplier", 1.0))
                    * float(reg_adj.get("confidence_multiplier", 1.0)),
                ),
            ),
            freshness_probability=max(
                0.05,
                min(
                    0.995,
                    float(capture.freshness_probability)
                    * float(realism.get("freshness_multiplier", 1.0)),
                ),
            ),
            expected_realized_pnl=float(capture.expected_realized_pnl) * realism_mult
            - float(realism.get("added_gas_cost", 0.0))
            - float(realism.get("added_slippage_cost", 0.0))
            - float(realism.get("added_failure_cost", 0.0)),
            expected_realized_value=float(capture.expected_realized_value) * realism_mult
            - float(realism.get("added_gas_cost", 0.0))
            - float(realism.get("added_slippage_cost", 0.0))
            - float(realism.get("added_failure_cost", 0.0)),
            capture_score=float(capture.capture_score) * realism_mult
            - float(realism.get("added_gas_cost", 0.0))
            - float(realism.get("added_slippage_cost", 0.0))
            - float(realism.get("added_failure_cost", 0.0)),
            slippage_cost_estimate=float(capture.slippage_cost_estimate)
            + float(realism.get("added_slippage_cost", 0.0)),
            failure_cost_estimate=float(capture.failure_cost_estimate)
            + float(realism.get("added_failure_cost", 0.0)),
            telemetry_adjustments=dict(capture.telemetry_adjustments or {})
            | {f"realism_{k}": float(v) for k, v in realism.items() if isinstance(v, (int, float))}
            | {f"regime_{k}": float(v) for k, v in reg_adj.items() if isinstance(v, (int, float))},
        )
        risk_penalty = {}
        if getattr(self, "risk_memory", None) is not None:
            token_pair = "/".join(list(envelope.token_path[:2])) if envelope.token_path else ""
            risk_penalty = self.risk_memory.penalty(
                route_family=str(envelope.route_family),
                venue=str(envelope.venues[0] if envelope.venues else ""),
                token_pair=token_pair,
                strategy_family=str(envelope.metadata.get("strategy_family") or ""),
                chain=str(chain_id),
                pool_path=str("|".join(envelope.venues)),
            )
            rp = float(risk_penalty.get("penalty") or 0.0)
            if rp > 0:
                capture = replace(
                    capture,
                    expected_realized_pnl=float(capture.expected_realized_pnl)
                    * max(0.35, 1.0 - rp),
                    expected_realized_value=float(capture.expected_realized_value)
                    * max(0.35, 1.0 - rp),
                    capture_score=float(capture.capture_score) * max(0.35, 1.0 - rp),
                    telemetry_adjustments=dict(capture.telemetry_adjustments or {})
                    | {"risk_memory_penalty": rp},
                )
        if calibration:
            lane_priors = default_lane_priors(
                lane=str(force_send_mode or priors.get("best_lane") or "PUBLIC").upper(),
                regime=str(regime or ""),
            )
            ratio_adj = max(
                0.45,
                min(
                    1.60,
                    float(calibration.get("realization_ratio", 1.0) or 1.0)
                    + float(lane_priors.get("realization_bias", 0.0) or 0.0),
                ),
            )
            cap_pnl = float(capture.expected_realized_pnl * ratio_adj)
            adj = dict(capture.telemetry_adjustments or {})
            adj.update({f"calibration_{k}": float(v) for k, v in calibration.items()})
            capture = replace(
                capture,
                expected_realized_pnl=cap_pnl,
                expected_realized_value=cap_pnl,
                capture_score=cap_pnl,
                telemetry_adjustments=adj,
            )

        lane = select_lane(
            envelope,
            capture,
            public_mode=public_mode,
            force_send_mode=(force_send_mode or preferred_lane),
        )
        size_mult, expected_value = choose_size(envelope, capture)
        if edge_pred is not None and getattr(self, "edge_learning", None) is not None:
            size_mult = float(size_mult) * float(
                self.edge_learning.confidence_to_size_scale(edge_pred)
            )
        path_pen = 0.0
        if getattr(self, "path_diversity", None) is not None:
            path_id = "|".join(
                [
                    str(envelope.route_family),
                    str(envelope.route_id),
                    ",".join(envelope.venues),
                    ",".join(envelope.token_path),
                    str(chain_id),
                    str(lane.value),
                ]
            )
            path_pen = float(self.path_diversity.penalty(path_id))
            expected_value = float(expected_value) * max(0.50, 1.0 - path_pen)

        route_plan = plan_route(
            envelope=envelope,
            capture=capture,
            telemetry=telemetry,
            latency_pressure=float(endpoint_choice.get("pressure") or 0.0),
            scorecards=getattr(self, "venue_scorecards", None),
            route_quality=getattr(self, "route_quality", None),
        )
        if float(route_plan.expected_value) > float(expected_value):
            expected_value = float(route_plan.expected_value)
            size_mult = float(route_plan.size_mult)

        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        pending_source = (
            meta.get("pending_context")
            or meta.get("pending_state_context")
            or meta.get("pending_state")
            or meta.get("pending_transactions")
            or (
                ((meta.get("aqe") or {}) if isinstance(meta.get("aqe"), dict) else {}).get(
                    "pending_conflicts"
                )
            )
            or []
        )
        adversarial = evaluate_adversarial_state(
            envelope=envelope,
            pending_source=pending_source,
            base_expected_value=float(expected_value),
            lane_hint=str(force_send_mode or lane.value),
        )
        expected_value = min(
            float(expected_value),
            float(adversarial.get("post_ordering_realized_edge") or expected_value),
        )
        capture = replace(
            capture,
            interference_probability=max(
                float(capture.interference_probability),
                float(
                    adversarial.get("interference_probability") or capture.interference_probability
                ),
            ),
            expected_realized_value=float(expected_value),
            expected_realized_pnl=min(float(capture.expected_realized_pnl), float(expected_value)),
            telemetry_adjustments=dict(capture.telemetry_adjustments or {})
            | {
                "adversarial_stale_probability": float(adversarial.get("stale_probability") or 0.0),
                "adversarial_copy_risk": float(adversarial.get("copy_risk") or 0.0),
            },
        )

        flashloan = {}
        if (
            "flash" in str(envelope.route_family)
            or str(meta.get("strategy_family") or "") == "flashloan_atomic"
        ):
            providers = list(meta.get("flash_providers") or ["aave", "balancer"])
            flashloan = evaluate_flashloan_resilience(
                envelope=envelope,
                pending_metrics=adversarial,
                route_plan=route_plan.to_dict(),
                available_providers=providers,
            )
            flashloan_size = choose_flashloan_size(
                envelope=envelope,
                requested_size_mult=float(size_mult),
                route_plan=route_plan.to_dict(),
                flashloan_resilience=flashloan,
                adversarial_state=adversarial,
                treasury_state=dict(
                    (meta.get("treasury_state") or {})
                    if isinstance(meta.get("treasury_state"), dict)
                    else {}
                ),
                wealth_goal_state=dict(
                    (meta.get("wealth_goal") or {})
                    if isinstance(meta.get("wealth_goal"), dict)
                    else {}
                ),
                drawdown_state=dict(
                    (meta.get("drawdown_state") or {})
                    if isinstance(meta.get("drawdown_state"), dict)
                    else {}
                ),
                kill_switch_state=dict(
                    (meta.get("kill_switch_state") or {})
                    if isinstance(meta.get("kill_switch_state"), dict)
                    else {}
                ),
            )
            flashloan["sizing"] = flashloan_size
            if not bool(flashloan_size.get("allowed", True)):
                adversarial = dict(adversarial or {})
                adversarial.setdefault("route_invalid_causes", [])
                adversarial["route_invalid_causes"] = list(
                    adversarial.get("route_invalid_causes") or []
                ) + list(flashloan_size.get("reason_codes") or [])
            size_mult = float(flashloan_size.get("size_mult") or size_mult)

        execution_route_plan = build_execution_route_plan(
            opp=opp,
            decision=type(
                "DecisionProxy",
                (),
                {
                    "metadata": {
                        "route_plan": route_plan.to_dict(),
                        "flashloan_resilience": flashloan,
                    }
                },
            )(),
        )

        assembly_ms = 35.0 if template_hit else 120.0
        pipeline_latency_ms = (
            float(endpoint_choice.get("measured_latency_ms") or 850.0)
            + assembly_ms
            + float(realism.get("added_latency_ms", 0.0) or 0.0)
        )
        latency_pressure = float(endpoint_choice.get("pressure") or 0.0)
        if latency_pressure >= 0.50 and envelope.liquidity_fragility >= 0.70:
            size_mult = float(size_mult) * 0.70
            expected_value = float(expected_value) * 0.82
        effective_min_value = float(self.policy.min_expected_realized_value_usd)
        if (
            lane in {ExecutionLane.PRIVATE, ExecutionLane.PROTECTED}
            and float(expected_value) > 0.0
            and (
                float(envelope.mempool_copy_risk) >= 0.75
                or bool(preferred_lane)
                or bool(adversarial.get("relay_necessity"))
            )
        ):
            effective_min_value = 0.0
        if (
            edge_pred is not None
            and float(edge_pred.competition_probability) >= 0.82
            and float(expected_value) < max(2.0, effective_min_value * 1.10)
        ):
            drop_reason = "competition_likely_competed_out"
        elif float(pipeline_latency_ms) >= float(envelope.latency_half_life_ms) and (
            bool(public_mode)
            or not (
                lane in {ExecutionLane.PRIVATE, ExecutionLane.PROTECTED}
                and (
                    bool(envelope.private_send_preference)
                    or bool(adversarial.get("relay_necessity"))
                )
            )
        ):
            drop_reason = "edge_half_life_below_pipeline_latency"
        elif float(adversarial.get("post_ordering_realized_edge") or 0.0) <= 0.0:
            drop_reason = "adversarial_negative_ev"
        elif bool(flashloan.get("searcher_invalidation")):
            drop_reason = "flashloan_race_invalidated"
        elif bool((flashloan.get("sizing") or {}).get("allowed") is False):
            drop_reason = "flashloan_size_not_viable"
        elif (
            getattr(self, "endpoint_quality", None) is not None
            and not lane_endpoints
            and lane != ExecutionLane.DROP
        ):
            drop_reason = "no_endpoint_universe_candidates"
        elif (
            getattr(self, "endpoint_quality", None) is not None
            and float(endpoint_choice.get("endpoint_quality") or 0.0) < 0.20
            and float(endpoint_choice.get("pressure") or 0.0) >= 0.70
        ):
            drop_reason = "endpoint_universe_below_reliability_requirements"
        elif float(capture.success_probability) < float(self.policy.min_success_probability):
            drop_reason = "low_success_probability"
        elif float(capture.freshness_probability) < float(self.policy.min_freshness_probability):
            drop_reason = "stale_or_decayed_edge"
        elif float(expected_value) < effective_min_value:
            drop_reason = "expected_realized_value_below_threshold"
        elif (
            latency_pressure >= 0.78
            and envelope.liquidity_fragility >= 0.65
            and float(expected_value) < max(1.0, effective_min_value * 1.2)
        ):
            drop_reason = "latency_pressure_fragile_route"
        else:
            drop_reason = ""

        if adversarial.get("requires_private_lane") and lane == ExecutionLane.PUBLIC:
            lane = ExecutionLane.PRIVATE
        if lane == ExecutionLane.DROP and not drop_reason:
            drop_reason = "lane_router_drop"
        if drop_reason:
            lane = ExecutionLane.DROP
        send_mode = "public"
        relay_hint = str(endpoint_choice.get("relay") or "rpc_public")
        if lane == ExecutionLane.PROTECTED:
            send_mode = "protected_rpc"
            relay_hint = relay_hint if relay_hint else "rpc_protected"
        elif lane == ExecutionLane.PRIVATE:
            send_mode = "private"
            relay_hint = relay_hint if relay_hint else "private_relay"
        elif lane == ExecutionLane.DROP:
            send_mode = "public"
            relay_hint = "drop"

        self.template_cache.remember(
            route_family=envelope.route_family,
            route_id=envelope.route_id,
            metadata={
                "venues": envelope.venues,
                "token_path": envelope.token_path,
                "fallback_tree": route_plan.fallback_tree,
                "hot_path": True,
                "candidate_endpoints": [
                    c.get("endpoint")
                    for c in list(endpoint_choice.get("candidates") or [])
                    if c.get("endpoint")
                ],
                "candidate_relays": [
                    c.get("endpoint")
                    for c in list(endpoint_choice.get("relay_candidates") or [])
                    if c.get("endpoint")
                ],
                "execution_route_plan": execution_route_plan,
            },
        )
        provider_hint = (
            str(
                (
                    (flashloan.get("sizing") or {}).get("selected_provider")
                    or (flashloan.get("provider_priority") or [""])[0]
                )
            )
            if flashloan
            else ""
        )
        decision = ExecutionDecision(
            action=("drop" if lane == ExecutionLane.DROP else "trade"),
            lane=lane,
            route_id=str(envelope.route_id),
            opportunity_id=str(envelope.opportunity_id),
            size_mult=float(size_mult),
            expected_realized_value=float(expected_value),
            expected_realized_pnl=float(capture.expected_realized_pnl),
            success_probability=float(capture.success_probability),
            freshness_probability=float(capture.freshness_probability),
            interference_probability=float(capture.interference_probability),
            send_mode=send_mode,
            relay_hint=relay_hint,
            reason=("capture_trade" if lane != ExecutionLane.DROP else "capture_drop"),
            drop_reason=str(drop_reason),
            retryable=bool(
                lane in {ExecutionLane.PROTECTED, ExecutionLane.PRIVATE}
                and float(expected_value) > 0.0
            ),
            endpoint_hint=str(endpoint_choice.get("endpoint") or relay_hint),
            capture_score=capture,
            metadata={
                "envelope": envelope.to_dict(),
                "aging_factor": age_factor,
                "path_diversity_penalty": path_pen,
                "risk_memory": risk_penalty,
                "simulation_realism": realism,
                "regime_adjustments": reg_adj,
                "edge_prediction": (edge_pred.to_dict() if edge_pred is not None else {}),
                "template_hit": template_hit,
                "route_plan": route_plan.to_dict(),
                "execution_route_plan": execution_route_plan,
                "adversarial_state": adversarial,
                "endpoint_selection": endpoint_choice,
                "pipeline_latency_ms": round(float(pipeline_latency_ms), 6),
                "flashloan_resilience": flashloan,
                "provider_hint": provider_hint,
                "route_invalid_causes": list(adversarial.get("route_invalid_causes") or [])
                + list(execution_route_plan.get("route_invalid_causes") or []),
            },
        )
        try:
            borrow_mult = (
                float(((flashloan.get("sizing") or {}).get("borrow_mult") or 1.0))
                if flashloan
                else 1.0
            )
            object.__setattr__(decision, "borrow_mult", borrow_mult)
        except (AttributeError, TypeError, ValueError):
            pass
        return decision
