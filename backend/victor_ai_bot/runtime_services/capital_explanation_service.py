from __future__ import annotations

from typing import Any, Dict, List

from .runtime_context import (
    build_runtime_access_snapshot,
    build_runtime_decision_context_from_snapshot,
)
from .summary_read_contract import build_summary_read_contract
from .route_runtime_truth import execution_route_truth
from ..capital_family_policy import resolve_family_capital_limit


def _pct(x: float) -> str:
    return f"{x * 100.0:.1f}%"


class CapitalExplanationService:
    def _best_subject(self, runtime: Any) -> Dict[str, Any]:
        live = (
            runtime.execution_live_state()
            if hasattr(runtime, "execution_live_state")
            else {"items": []}
        )
        items = list((live or {}).get("items") or [])
        if items:
            return dict(items[-1])
        opp = None
        try:
            opps = list(getattr(runtime, "_opps", []) or [])
            scored = []
            for o in opps[:20]:
                cap = (
                    dict((getattr(o, "meta", {}) or {}).get("capture") or {})
                    if isinstance(getattr(o, "meta", None), dict)
                    else {}
                )
                scored.append((float(cap.get("expected_realized_value") or 0.0), o))
            scored.sort(key=lambda x: (-x[0], str(getattr(x[1], "route_id", "") or "")))
            opp = scored[0][1] if scored else None
        except (AttributeError, KeyError, TypeError, ValueError):
            opp = None
        if opp is None:
            return {}
        meta = (
            dict(getattr(opp, "meta", {}) or {})
            if isinstance(getattr(opp, "meta", None), dict)
            else {}
        )
        cap = dict(meta.get("capture") or {})
        md = dict(cap.get("metadata") or {})
        route_plan = dict(md.get("route_plan") or {})
        live_exec_plan = dict(meta.get("execution_route_plan") or {})
        live_route_runtime = dict(meta.get("execution_route_runtime") or {})
        exec_plan = dict(live_exec_plan or md.get("execution_route_plan") or {})
        route_runtime = dict(live_route_runtime or md.get("execution_route_runtime") or {})
        adv = dict(md.get("adversarial_state") or {})
        endpoint = dict(md.get("endpoint_selection") or {})
        flash = dict(md.get("flashloan_resilience") or {})
        flash_sizing = dict(
            (flash.get("sizing") or {}) if isinstance(flash.get("sizing"), dict) else {}
        )
        env = dict(md.get("envelope") or {})
        route_truth = execution_route_truth(
            {
                "execution_route_plan": exec_plan,
                "route_invalid_causes": list(
                    meta.get("route_invalid_causes") or md.get("route_invalid_causes") or []
                ),
                "execution_route_runtime": route_runtime,
            }
        )
        route_runtime_reason_codes = list(route_truth.get("runtime_reason_codes") or [])
        route_runtime_degraded = bool(route_truth.get("runtime_degraded", False))
        route_invalid_causes = list(
            exec_plan.get("route_invalid_causes") or md.get("route_invalid_causes") or []
        )
        route_executable = bool(route_truth.get("ready", False))
        return {
            "routeFamily": str(env.get("route_family") or meta.get("route_family") or ""),
            "family": str(meta.get("strategy_family") or "flashloan_atomic"),
            "lane": str(cap.get("lane") or meta.get("execution_lane") or ""),
            "endpoint": str(cap.get("endpoint_hint") or endpoint.get("endpoint") or ""),
            "relay": str(cap.get("relay_hint") or endpoint.get("relay") or ""),
            "selectedVenues": list(
                route_plan.get("selected_venues")
                or exec_plan.get("selected_venues")
                or env.get("venues")
                or []
            ),
            "routeExecutable": route_executable,
            "fallbackReady": bool(
                exec_plan.get("fallback_tree") or route_plan.get("fallback_tree")
            ),
            "routeInvalidCauses": route_invalid_causes,
            "routeRuntimeDegraded": route_runtime_degraded,
            "routeRuntimeReasonCodes": route_runtime_reason_codes,
            "adversarial": {
                "staleProbability": float(adv.get("stale_probability") or 0.0),
                "interferenceProbability": float(adv.get("interference_probability") or 0.0),
                "postOrderingRealizedEdge": float(
                    adv.get("post_ordering_realized_edge")
                    or cap.get("expected_realized_value")
                    or 0.0
                ),
                "copyRisk": float(adv.get("copy_risk") or 0.0),
                "relayNecessity": bool(adv.get("relay_necessity")),
            },
            "flashloan": {
                "selectedProvider": str(flash.get("selected_provider") or ""),
                "fallbackProvider": str(flash.get("fallback_provider") or ""),
                "reserveDistortion": float(flash.get("reserve_distortion") or 0.0),
                "reasonCodes": list(flash.get("reason_codes") or []),
                "sizing": flash_sizing,
            },
            "endpointReason": str(endpoint.get("reason") or endpoint.get("pressure_class") or ""),
            "endpointUniverseReason": str(
                (
                    (endpoint.get("universe") or {})
                    if isinstance(endpoint.get("universe"), dict)
                    else {}
                ).get("reason")
                or ""
            ),
            "sizeMult": float(cap.get("size_mult") or 1.0),
            "expectedValue": float(cap.get("expected_realized_value") or 0.0),
            "metadata": md,
        }

    def explain(self, runtime: Any, *, snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
        subject = self._best_subject(runtime)
        snap = snapshot or {}
        if not subject:
            payload = {
                "ok": True,
                "text": "No active capital decision is available yet. Connect live routing or wait for a scored opportunity.",
                "facts": {},
                "causal": {
                    "whyRoute": "",
                    "whySize": "",
                    "whyLane": "",
                    "whyNow": "",
                    "whyNot": [],
                },
            }
            payload["summaryContract"] = build_summary_read_contract(
                family="capital_explain",
                payload=payload,
                phase="capital_explain_summary",
                read_model="capital_explanation_projection_v1",
            )
            return payload
        md = dict(subject.get("metadata") or {})
        env = dict(md.get("envelope") or {})
        route_plan = dict(md.get("route_plan") or {})
        exec_plan = dict(md.get("execution_route_plan") or {})
        endpoint = dict(md.get("endpoint_selection") or {})
        adv = dict(md.get("adversarial_state") or {})
        flash_sizing = dict(
            (
                (
                    (subject.get("flashloan") or {})
                    if isinstance(subject.get("flashloan"), dict)
                    else {}
                ).get("sizing")
                or {}
            )
            if isinstance(subject.get("flashloan"), dict)
            else {}
        )
        runtime_snapshot = build_runtime_access_snapshot(runtime)
        decision_ctx = build_runtime_decision_context_from_snapshot(runtime_snapshot)
        drawdown = dict(decision_ctx.drawdown_state)
        kill_switch = dict(decision_ctx.kill_switch_state)
        capital = dict(decision_ctx.treasury_state)
        wealth = (
            runtime.wealth_goal_state()
            if hasattr(runtime, "wealth_goal_state")
            else {"state": dict(decision_ctx.wealth_goal)}
        )
        family = str(subject.get("family") or "flashloan_atomic")
        route_family = str(subject.get("routeFamily") or "")
        lane = str(subject.get("lane") or "")
        size_mult = float(subject.get("sizeMult") or 1.0)
        expected_value = float(subject.get("expectedValue") or 0.0)
        selected_venues = [str(v) for v in list(subject.get("selectedVenues") or []) if str(v)]
        pipeline_ms = float(md.get("pipeline_latency_ms") or 0.0)
        half_life_ms = float(env.get("latency_half_life_ms") or 0.0)
        family_limit = resolve_family_capital_limit(
            capital_engine=(capital.get("capital_engine") or {}),
            family=family,
        )
        family_budget = float(family_limit.get("family_target") or 0.0)
        wealth_state = dict((wealth.get("state") or {}) if isinstance(wealth, dict) else {})
        wealth_explanation = dict(
            (wealth.get("explanation") or {}) if isinstance(wealth, dict) else {}
        )
        safe_curve = list(env.get("safe_size_curve") or [])
        size_alternatives = []
        for row in safe_curve[:4]:
            if not isinstance(row, dict):
                continue
            size_alternatives.append(
                {
                    "sizeMult": float(row.get("size_mult") or 0.0),
                    "expectedProfitUsd": float(row.get("expected_profit_usd") or 0.0),
                    "reason": "curve_candidate",
                }
            )
        route_invalid_causes = [
            str(x) for x in list(subject.get("routeInvalidCauses") or []) if str(x)
        ]
        route_runtime_reason_codes = [
            str(x) for x in list(subject.get("routeRuntimeReasonCodes") or []) if str(x)
        ]
        route_runtime_degraded = bool(subject.get("routeRuntimeDegraded")) or bool(
            route_runtime_reason_codes
        )
        route_executable = bool(subject.get("routeExecutable"))
        if route_executable:
            why_route = f"Selected {route_family or 'route'} across {', '.join(selected_venues) or 'default venues'} because persisted route quality, venue quality, and fallback readiness produced the best bounded expected value (${expected_value:.2f})."
        else:
            route_blockers = (
                route_invalid_causes or route_runtime_reason_codes or ["execution_route_not_ready"]
            )
            why_route = f"No route is currently executable. The best recent candidate {route_family or 'route'} across {', '.join(selected_venues) or 'default venues'} is blocked by {', '.join(route_blockers)} and should not be deployed until route realism is restored."
        next_goal_blockers = list(wealth_state.get("nextGoalBlockedReasons") or [])
        why_size = f"Size multiplier {size_mult:.2f} was chosen from the safe size curve and then clamped by family budget {family_budget:.3f}, wealth-goal aggressiveness cap {float(wealth_state.get('aggressivenessCap') or 1.0):.2f}, and any drawdown aggressiveness caps."
        why_lane = f"Lane {lane or 'unknown'} was chosen because endpoint universe reason was '{subject.get('endpointUniverseReason') or 'quality_ranked'}' and endpoint pressure reason was '{subject.get('endpointReason') or 'quality_ranked'}'."
        why_now = f"Route timing is allowed because pipeline latency ({pipeline_ms:.0f} ms) is compared against edge half-life ({half_life_ms:.0f} ms), adversarial post-ordering edge remains ${float(subject.get('adversarial', {}).get('postOrderingRealizedEdge') or 0.0):.2f}, wealth pacing is {str(wealth_state.get('pacing') or 'steady')}, and hard stop is {'active' if bool(((drawdown.get('hardStop') or {}).get('active'))) else 'clear'}."
        alternatives: List[Dict[str, Any]] = []
        for fb in list(route_plan.get("fallback_tree") or [])[:3]:
            if not isinstance(fb, dict):
                continue
            alternatives.append(
                {
                    "kind": "route",
                    "candidate": ",".join(list(fb.get("selected_venues") or [])) or "default",
                    "reason": f"lower score {float(fb.get('score') or 0.0):.3f} or lower EV ${float(fb.get('expected_value') or 0.0):.2f}",
                }
            )
        for cand in list((endpoint.get("candidates") or []))[:2]:
            if not isinstance(cand, dict):
                continue
            ep = str(cand.get("endpoint") or cand.get("url") or "")
            if ep and ep != str(subject.get("endpoint") or ""):
                alternatives.append(
                    {
                        "kind": "endpoint",
                        "candidate": ep,
                        "reason": "lower endpoint quality or operator preference rank",
                    }
                )
        for row in size_alternatives[:2]:
            if abs(float(row.get("sizeMult") or 0.0) - size_mult) > 1e-6:
                alternatives.append(
                    {
                        "kind": "size",
                        "candidate": f"{float(row.get('sizeMult') or 0.0):.2f}",
                        "reason": f"lower post-cost expected profit ${float(row.get('expectedProfitUsd') or 0.0):.2f} or more fragile",
                    }
                )
        suppressions = []
        for scope, payload in sorted(
            (
                (kill_switch.get("suppressions") or {}) if isinstance(kill_switch, dict) else {}
            ).items()
        ):
            if isinstance(payload, dict):
                raw_reason_codes = payload.get("reason_codes")
                if isinstance(raw_reason_codes, list):
                    for reason in raw_reason_codes[:2]:
                        suppressions.append(f"{scope}: {reason}")
        if flash_sizing:
            why_size += f" Flash-loan borrow multiplier {float(flash_sizing.get('borrow_mult') or 1.0):.2f} with provider cap {float(flash_sizing.get('provider_limit') or 0.0):.2f}, route viability cap {float(flash_sizing.get('route_viability_cap') or 0.0):.2f}, pool-depth cap {float(flash_sizing.get('pool_depth_cap') or 0.0):.2f}, and family budget cap {float(flash_sizing.get('family_budget_cap') or 0.0):.2f} was used to protect net EV. Provider choice reason: {str(flash_sizing.get('provider_choice_reason') or 'preferred_provider_selected')}."
        if next_goal_blockers:
            why_now += (
                f" Next-goal escalation is currently blocked by {', '.join(next_goal_blockers)}."
            )
        if not route_executable:
            why_now += " Route realism is not currently healthy, so the correct action is to hold auto-deployment until the execution route is refreshed."
            alternatives.insert(
                0,
                {
                    "kind": "hold",
                    "candidate": "no_trade",
                    "reason": ", ".join(
                        route_invalid_causes
                        or route_runtime_reason_codes
                        or ["execution_route_not_ready"]
                    ),
                },
            )
        text = (
            f"Why this route: {why_route} Why this size: {why_size} Why this lane: {why_lane} Why now: {why_now} "
            f"Why not alternatives: {', '.join(a['candidate'] + ' (' + a['reason'] + ')' for a in alternatives[:5]) or 'No better bounded alternative remained positive.'}"
        )
        payload = {
            "ok": True,
            "text": text,
            "facts": {
                "routeFamily": route_family,
                "family": family,
                "lane": lane,
                "endpoint": subject.get("endpoint"),
                "selectedVenues": selected_venues,
                "sizeMult": size_mult,
                "familyBudget": family_budget,
                "pipelineLatencyMs": pipeline_ms,
                "halfLifeMs": half_life_ms,
                "routeExecutable": bool(subject.get("routeExecutable")),
                "routeRuntimeDegraded": bool(subject.get("routeRuntimeDegraded")),
                "fallbackReady": bool(subject.get("fallbackReady")),
                "drawdownHardStop": bool(((drawdown.get("hardStop") or {}).get("active"))),
                "wealthGoalPacing": str(wealth_state.get("pacing") or ""),
                "wealthGoalAggressivenessCap": float(wealth_state.get("aggressivenessCap") or 1.0),
                "wealthGoalCapitalBaseUsd": float(wealth_state.get("capitalBaseUsd") or 0.0),
                "wealthGoalExecutionRealismScore": float(
                    wealth_state.get("executionRealismScore") or 0.0
                ),
            },
            "causal": {
                "whyRoute": why_route,
                "whySize": why_size,
                "whyLane": why_lane,
                "whyNow": why_now,
                "whyNot": alternatives[:5],
                "suppressionReasons": suppressions[:8],
                "routeInvalidCauses": list(subject.get("routeInvalidCauses") or []),
                "routeRuntimeReasonCodes": list(subject.get("routeRuntimeReasonCodes") or []),
                "goalBlockedReasons": list(
                    wealth_state.get("blockedGoalReasonCodes")
                    or wealth_state.get("nextGoalBlockedReasons")
                    or []
                ),
                "adversarialFragility": {
                    "staleProbability": float(
                        subject.get("adversarial", {}).get("staleProbability") or 0.0
                    ),
                    "interferenceProbability": float(
                        subject.get("adversarial", {}).get("interferenceProbability") or 0.0
                    ),
                    "copyRisk": float(subject.get("adversarial", {}).get("copyRisk") or 0.0),
                    "relayNecessity": bool(subject.get("adversarial", {}).get("relayNecessity")),
                },
                "flashloan": dict(subject.get("flashloan") or {}),
                "wealthGoalExplanation": wealth_explanation,
                "serviceSummary": (
                    runtime.service_health_state()
                    if hasattr(runtime, "service_health_state")
                    else {}
                ),
            },
        }
        causal_payload: Dict[str, Any]
        raw_causal = payload.get("causal")
        if isinstance(raw_causal, dict):
            causal_payload = dict(raw_causal)
        else:
            causal_payload = {}
        payload["summaryContract"] = build_summary_read_contract(
            family="capital_explain",
            payload=payload,
            source_contracts={
                "serviceSummary": dict(causal_payload.get("serviceSummary") or {}),
            },
            phase="capital_explain_summary",
            read_model="capital_explanation_projection_v1",
        )
        return payload
