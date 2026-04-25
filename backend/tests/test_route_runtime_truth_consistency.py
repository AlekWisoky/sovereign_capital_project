from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.capital_explanation_service import CapitalExplanationService
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.state_service import build_top_opportunity_view


class _Opp:
    def __init__(self, *, meta: dict | None = None, can_execute: bool = True) -> None:
        self.id = "opp-1"
        self.route_id = "route-1"
        self.strategy = "flashloan_atomic"
        self.expected_profit_raw = "1000"
        self.can_execute = can_execute
        self.route = SimpleNamespace(legs=[])
        self.min_outs = []
        self.meta = {
            "profit_after_costs": "700",
            "safety": {"profit_after_costs_wei": "700", "exec_ready": True},
        }
        if meta:
            self.meta.update(meta)

    def copy(self, deep: bool = False):
        return _Opp(meta=dict(self.meta), can_execute=self.can_execute)


class _SnapshotRuntime:
    async def snapshot(self):
        return {
            "metrics": {"auto_trading": True},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [
                {
                    "id": "opp-1",
                    "expected_profit_raw": "1000",
                    "can_execute": True,
                    "meta": {
                        "profit_after_costs": "700",
                        "safety": {"profit_after_costs_wei": "700", "exec_ready": True},
                        "execution_route_runtime": {
                            "degraded": False,
                            "reason_codes": ["execution_route_input_unavailable"],
                        },
                    },
                }
            ],
        }

    def drawdown_state(self):
        return {"drawdownPct": 0.0, "hardStop": {"active": False, "reason_codes": []}}

    def kill_switch_state(self):
        return {"suppressions": {}}


class _CapitalExplanationRuntime:
    def __init__(self, opp):
        self._opps = [opp]
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(chain_id=1, name="ethereum"),
            execution=SimpleNamespace(base_borrow_amount="0", gas_mode="fast", send_mode="private"),
        )
        self._market_regime = {"regime": "balanced"}
        self._cc = SimpleNamespace(controls=SimpleNamespace(force_send_mode="private"))
        self._wealth_goal_service = SimpleNamespace(
            state=lambda runtime: {"state": {"aggressivenessCap": 0.9}}
        )

    def drawdown_state(self):
        return {"drawdownPct": 1.0, "hardStop": {"active": False}}

    def kill_switch_state(self):
        return {"suppressions": {}}

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"flashloan_atomic": 0.4}}}

    def execution_live_state(self):
        return {"items": []}

    def wealth_goal_state(self):
        return {
            "state": {"goalStatus": "active", "aggressivenessCap": 0.9},
            "explanation": {"why_posture": "steady"},
        }


def _healthy_execution_route_plan(*, runtime: dict | None = None) -> dict:
    return {
        "selected_venues": ["uni", "curve"],
        "split": [
            {"venue": "uni", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
            {"venue": "curve", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
        ],
        "fallback_tree": [],
        "fallback_used": False,
        "executable": True,
        "require_fallback_tree": False,
        "provider_priority": ["aave"],
        "provider_fallback": "",
        "reserve_distortion": 0.0,
        "mutation_factor": 1.0,
        "route_invalid_causes": [],
        "runtime": runtime
        or {
            "input": {"ok": True, "code": "ok", "detail": ""},
            "legs": {"ok": True, "code": "ok", "detail": ""},
            "mutation": {"ok": True, "code": "ok", "detail": ""},
            "profit": {"ok": True, "code": "ok", "detail": ""},
            "degraded": False,
        },
        "leg_plan": [],
        "raw_route_plan": {},
    }


def test_execution_realism_gate_blocks_on_reason_codes_only_route_runtime_degradation():
    opp = _Opp()
    route_runtime = {
        "input": {"ok": True, "code": "ok", "detail": ""},
        "legs": {"ok": True, "code": "ok", "detail": ""},
        "mutation": {"ok": True, "code": "ok", "detail": ""},
        "profit": {"ok": True, "code": "ok", "detail": ""},
        "degraded": False,
        "reason_codes": ["execution_route_input_unavailable"],
    }
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(
            metadata={
                "execution_route_plan": _healthy_execution_route_plan(runtime=route_runtime),
            }
        ),
    )

    assert gate.allowed is False
    assert gate.reason == "execution_route_input_unavailable"
    assert gate.metadata["routeRuntimeDegraded"] is True
    assert gate.metadata["routeRuntimeReasonCodes"] == ["execution_route_input_unavailable"]


def test_operator_summary_and_state_view_treat_reason_codes_only_runtime_as_not_executable():
    runtime = _SnapshotRuntime()
    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    assert out["ok"] is True
    assert out["observability"]["oppsAfterCostPositive"] == 1
    assert out["observability"]["oppsExecutable"] == 0

    top = build_top_opportunity_view(
        [
            _Opp(
                meta={
                    "execution_route_runtime": {
                        "degraded": False,
                        "reason_codes": ["execution_route_input_unavailable"],
                    },
                }
            )
        ]
    )
    assert top is not None
    assert top["execution_ready"] is False
    assert top["execution_ready_reason"] == "execution_route_input_unavailable"


def test_capital_explanation_prefers_live_meta_route_runtime_and_normalizes_aliases():
    opp = _Opp(
        meta={
            "execution_route_plan": {"executable": True, "selected_venues": ["uni"]},
            "execution_route_runtime": {
                "degraded": False,
                "reason_codes": ["plan_profit_after_costs_invalid"],
            },
            "capture": {
                "expected_realized_value": 12.5,
                "lane": "PRIVATE",
                "metadata": {
                    "execution_route_plan": {"executable": True, "selected_venues": ["uni"]},
                    "execution_route_runtime": {"degraded": False, "reason_codes": []},
                    "route_plan": {"selected_venues": ["uni"]},
                    "endpoint_selection": {"endpoint": "rpc-fast", "reason": "quality_ranked"},
                    "adversarial_state": {
                        "stale_probability": 0.1,
                        "interference_probability": 0.05,
                        "post_ordering_realized_edge": 11.0,
                    },
                    "flashloan_resilience": {
                        "selected_provider": "aave",
                        "sizing": {"borrow_mult": 1.2, "provider_choice_reason": "depth_ok"},
                    },
                    "envelope": {"route_family": "flashloan_atomic", "venues": ["uni"]},
                },
            },
        }
    )
    rt = _CapitalExplanationRuntime(opp)
    out = CapitalExplanationService().explain(rt)

    assert out["ok"] is True
    assert out["facts"]["routeExecutable"] is False
    assert out["facts"]["routeRuntimeDegraded"] is True
    assert out["causal"]["routeRuntimeReasonCodes"] == ["profit_after_costs_invalid"]
