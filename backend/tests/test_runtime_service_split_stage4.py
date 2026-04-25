from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.runtime_services.admission_service import AdmissionService
from victor_ai_bot.runtime_services.capital_explanation_service import CapitalExplanationService
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.telemetry_service import TelemetryService
from victor_ai_bot.telemetry.store import TelemetryStore


class DummyCapture:
    def __init__(self, action="trade", drop_reason="", expected_realized_value=6.0, size_mult=1.0):
        self.action = action
        self.drop_reason = drop_reason
        self.expected_realized_value = expected_realized_value
        self.size_mult = size_mult
        self.metadata = {"envelope": {"route_family": "flashloan_atomic"}}

    def to_dict(self):
        return {
            "action": self.action,
            "drop_reason": self.drop_reason,
            "expected_realized_value": self.expected_realized_value,
            "size_mult": self.size_mult,
            "metadata": self.metadata,
        }


class DummyCaptureEngine:
    def __init__(self, action="trade"):
        self.action = action

    def evaluate(self, opp, **kwargs):
        return DummyCapture(
            action=self.action,
            drop_reason="too_fragile" if self.action == "drop" else "",
            expected_realized_value=8.5,
            size_mult=1.0,
        )


class DummyRuntime:
    def __init__(self, tmp_path, action="trade"):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum", chain_id=1),
            execution=SimpleNamespace(dry_run=False),
        )
        self._capture_engine = DummyCaptureEngine(action=action)
        self._cc = None
        self._no_trade_analytics = None
        self._drawdown_state = SimpleNamespace(
            gate=lambda family: {"allowed": True, "aggressiveness_cap": 1.0, "reason_codes": []}
        )
        self._kill_switch = SimpleNamespace(
            evaluate=lambda **kwargs: {"allowed": True, "reason_codes": []}
        )
        self._telemetry_service = TelemetryService(
            store=TelemetryStore(data_dir=str(tmp_path), chain="ethereum")
        )
        self._pending = {
            "0x1": {
                "capture_meta": {
                    "lane": "PRIVATE",
                    "endpoint_hint": "rpc-fast",
                    "metadata": {
                        "endpoint_selection": {
                            "endpoint": "rpc-fast",
                            "reason": "quality_ranked",
                            "universe": {"reason": "operator_preferences"},
                        },
                        "route_plan": {
                            "selected_venues": ["uni", "curve"],
                            "fallback_tree": [{"selected_venues": ["uni"], "expected_value": 2.0}],
                        },
                        "execution_route_plan": {
                            "selected_venues": ["uni", "curve"],
                            "fallback_tree": [{"selected_venues": ["uni"]}],
                            "executable": True,
                            "route_invalid_causes": [],
                        },
                        "adversarial_state": {
                            "stale_probability": 0.1,
                            "interference_probability": 0.2,
                            "post_ordering_realized_edge": 6.1,
                            "copy_risk": 0.3,
                            "relay_necessity": True,
                            "requires_private_lane": True,
                        },
                        "flashloan_resilience": {
                            "selected_provider": "aave",
                            "fallback_provider": "balancer",
                            "reserve_distortion": 0.12,
                            "reason_codes": ["reserve_distortion"],
                        },
                        "envelope": {"route_family": "flashloan_atomic"},
                    },
                },
                "route_family": "flashloan_atomic",
                "strategy_family": "flashloan_atomic",
                "created_at_ms": 123,
            }
        }
        self._opps = []

    def _pending_state_for_opp(self, opp):
        return []

    def _pending_state_context_for_opp(self, opp):
        return {"summary": {"count": 2}}

    def _public_mode_for_capture(self):
        return False

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"flashloan_atomic": 0.35}}}

    def _scale_opportunity(self, opp, mult):
        opp.scaled_by = mult
        return opp

    def execution_live_state(self):
        from victor_ai_bot.runtime_legacy import (
            RuntimeBundle,
        )  # only for method behavior parity not instance use

        # emulate the runtime method shape we rely on in services
        return {
            "items": [
                {
                    "txHash": "0x1",
                    "routeFamily": "flashloan_atomic",
                    "family": "flashloan_atomic",
                    "lane": "PRIVATE",
                    "endpoint": "rpc-fast",
                    "relay": "relay-a",
                    "fallbackReady": True,
                    "routeExecutable": True,
                    "routeInvalidCauses": [],
                    "flashloan": {"selectedProvider": "aave"},
                }
            ]
        }

    def drawdown_state(self):
        return {"hardStop": {"active": False}}

    def service_health_state(self):
        return {"execution": {"ok": True}}


def test_admission_service_prepares_capture_and_pending_context(tmp_path):
    rt = DummyRuntime(tmp_path)
    opp = SimpleNamespace(meta={"strategy_family": "flashloan_atomic"})
    svc = AdmissionService()
    result = svc.prepare_capture(rt, opp)
    assert result.capture_decision is not None
    assert opp.meta["pending_context"]["summary"]["count"] == 2


def test_execution_service_summarizes_live_execution():
    svc = ExecutionService()
    rt = DummyRuntime("/tmp")
    summary = svc.summarize(rt)
    assert summary["lastEndpoint"] == "rpc-fast"
    assert summary["fallbackReady"] is True


def test_telemetry_service_records_decision_and_outcome(tmp_path):
    svc = TelemetryService(store=TelemetryStore(data_dir=str(tmp_path), chain="ethereum"))
    svc.record_decision(
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        projected_realized_edge_usd=5.0,
        actual_realized_edge_usd=0.0,
        ok=False,
        dropped=True,
        chain="ethereum",
        reward_trace={"reward": -1.0},
        decision_reason="fragile",
    )
    svc.record_outcome(
        route_family="flashloan_atomic",
        strategy_family="flashloan_atomic",
        projected_realized_edge_usd=5.0,
        actual_realized_edge_usd=4.2,
        projected_gross_edge_usd=5.3,
        ok=True,
        lane="PRIVATE",
        chain="ethereum",
        reward_trace={"reward": 0.7},
    )
    summary = svc.service_summary(SimpleNamespace(execution_live_state=lambda: {"items": []}))
    assert summary["tailCount"] == 2
    assert summary["ok"] is True


def test_receipt_service_metrics_and_persistence(tmp_path):
    rt = DummyRuntime(tmp_path)
    rt._route_quality = SimpleNamespace(observe=lambda **kwargs: kwargs)
    rt._venue_scorecards = SimpleNamespace(observe=lambda **kwargs: kwargs)
    rt._endpoint_quality = SimpleNamespace(observe=lambda **kwargs: kwargs)
    svc = ReceiptService()
    metrics = svc.outcome_metrics(
        expected_after_usd=5.0, realized_after_usd=4.0, gross_edge_usd=6.0
    )
    assert metrics["actual_realized_edge_usd"] == 4.0
    out = svc.persist_execution_outcome(
        rt,
        pending={
            "capture_meta": {
                "metadata": {
                    "envelope": {"venues": ["uni"], "token_path": ["WETH", "USDC"]},
                    "route_plan": {
                        "selected_venues": ["uni"],
                        "split": [{"venue": "uni", "share": 1.0}],
                    },
                    "endpoint_selection": {"endpoint": "rpc-fast"},
                }
            },
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
        },
        status=1,
        submit_to_receipt_ms=500,
        realized_usd=4.0,
        expected_usd=5.0,
        reward_trace={"reward": 0.2},
        capture_lane_pending="PRIVATE",
    )
    assert out["route_family"] == "flashloan_atomic"


def test_receipt_service_persists_receipt_outcome_truth_health(tmp_path):
    rt = DummyRuntime(tmp_path)
    rt._db = PersistenceDB(str(tmp_path / "runtime.sqlite3"))
    svc = ReceiptService()

    svc.observe_outcome_truth_health(
        rt, verified=False, reason_code="settled_profit_truth_unavailable", ts_ms=1000
    )
    degraded = rt._capital_recovery_repo.load("receipt_outcome_truth")
    assert degraded["is_degraded"] is True
    assert degraded["last_reason_code"] == "settled_profit_truth_unavailable"

    svc.observe_outcome_truth_health(rt, verified=True, reason_code="ok", ts_ms=2000)
    recovered = rt._capital_recovery_repo.load("receipt_outcome_truth")
    assert recovered["is_degraded"] is False
    assert recovered["last_reason_code"] == "ok"
    assert recovered["last_recovered_ts_ms"] == 2000


def test_capital_explanation_service_is_causal(tmp_path):
    rt = DummyRuntime(tmp_path)
    svc = CapitalExplanationService()
    out = svc.explain(rt)
    assert out["ok"] is True
    assert "whyRoute" in out["causal"]
    assert "whyLane" in out["causal"]
    assert isinstance(out["causal"]["whyNot"], list)


def test_execution_live_state_delegates_to_execution_service(tmp_path):
    rt = DummyRuntime(tmp_path)
    svc = ExecutionService()
    live = svc.build_live_state(rt)
    assert live["items"][0]["endpoint"] == "rpc-fast"
    assert live["items"][0]["flashloan"]["selectedProvider"] == "aave"


def test_telemetry_service_aggregates_service_health(tmp_path):
    rt = DummyRuntime(tmp_path)
    telemetry = rt._telemetry_service
    rt._admission_service = AdmissionService()
    rt._execution_service = ExecutionService()
    rt._receipt_service = ReceiptService()
    summary = telemetry.service_health(rt)
    assert summary["admission"]["ok"] is True
    assert summary["execution"]["lastEndpoint"] == "rpc-fast"
    assert summary["receipt"]["lastProvider"] == "aave"


def test_execution_service_scales_opportunity():
    svc = ExecutionService()
    opp = SimpleNamespace(
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(amount_in="100", min_out="120"),
                SimpleNamespace(amount_in="120", min_out="140"),
            ]
        ),
        expected_profit_raw="20",
        min_outs=["120", "140"],
        meta={"out1": "120"},
        model_copy=lambda deep=True: SimpleNamespace(
            route=SimpleNamespace(
                legs=[
                    SimpleNamespace(amount_in="100", min_out="120"),
                    SimpleNamespace(amount_in="120", min_out="140"),
                ]
            ),
            expected_profit_raw="20",
            min_outs=["120", "140"],
            meta={"out1": "120"},
        ),
    )
    out = svc.scale_opportunity(opp, 0.5)
    assert out.route.legs[0].amount_in == "50"
    assert out.route.legs[1].amount_in == "60"
    assert out.expected_profit_raw == "10"


def test_execution_service_resolves_amount_in(tmp_path):
    svc = ExecutionService()
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(
            execution=SimpleNamespace(base_borrow_amount="0"),
            chain=SimpleNamespace(
                v3_pairs=[{"amount_in": "150"}], curve_pools=[], balancer_pools=[]
            ),
        ),
        _bankroll=SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=0),
            apply_overrides=lambda **kwargs: None,
            next_amount_in=lambda: 150,
        ),
        _cc=None,
    )
    assert svc.resolve_amount_in(runtime) == 150
    assert runtime._bankroll.cfg.base_borrow_amount_wei == 150


def test_telemetry_service_preserves_canonical_unavailable_semantics_when_subservices_missing(
    tmp_path,
):
    rt = DummyRuntime(tmp_path)
    telemetry = rt._telemetry_service

    summary = telemetry.service_health(rt)

    assert summary["admission"]["status"] == "unavailable"
    assert summary["admission"]["reason_code"] == "admission_service_unavailable"
    assert summary["execution"]["status"] == "unavailable"
    assert summary["receipt"]["reason_code"] == "receipt_service_unavailable"
    assert summary["wealthGoal"]["reason_code"] == "wealth_goal_service_unavailable"


def test_telemetry_service_handles_wealth_goal_error_payload_without_collapsing_to_none(tmp_path):
    rt = DummyRuntime(tmp_path)
    telemetry = rt._telemetry_service
    rt._wealth_goal_service = SimpleNamespace(
        state=lambda runtime: {"ok": False, "error": "treasury_goal_unavailable"}
    )

    summary = telemetry.service_health(rt)

    assert summary["wealthGoal"]["status"] == "unavailable"
    assert summary["wealthGoal"]["reason_code"] == "treasury_goal_unavailable"
    assert summary["wealthGoal"]["error"] == "treasury_goal_unavailable"


def _scaled_opp(meta: dict | None = None):
    return SimpleNamespace(
        expected_profit_raw="1000",
        meta=meta if meta is not None else {},
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(amount_in="100", min_out="200"),
                SimpleNamespace(amount_in="200", min_out="300"),
            ]
        ),
        min_outs=["200", "300"],
        model_copy=lambda deep=True: SimpleNamespace(
            expected_profit_raw="1000",
            meta=(meta.copy() if isinstance(meta, dict) else {}),
            route=SimpleNamespace(
                legs=[
                    SimpleNamespace(amount_in="100", min_out="200"),
                    SimpleNamespace(amount_in="200", min_out="300"),
                ]
            ),
            min_outs=["200", "300"],
        ),
    )


def test_execution_service_scale_opportunity_scales_after_cost_profit_fields():
    svc = ExecutionService()
    meta = {
        "out1": "200",
        "profit_after_costs": "600",
        "safety": {
            "profit_after_costs_wei": "600",
            "profit_after_costs_usd_micro": "3000000",
        },
    }
    opp = _scaled_opp(meta=meta)

    scaled = svc.scale_opportunity(opp, 0.5)

    assert scaled.expected_profit_raw == "500"
    assert scaled.meta["profit_after_costs"] == "300"
    assert scaled.meta["safety"]["profit_after_costs_wei"] == "300"
    assert scaled.meta["safety"]["profit_after_costs_usd_micro"] == "1500000"
    assert scaled.meta["brain"]["profit_after_costs_sync"] == "scaled"


def test_execution_service_scale_opportunity_zeroes_invalid_after_cost_profit_fields():
    svc = ExecutionService()
    meta = {
        "profit_after_costs": "invalid",
        "safety": {"profit_after_costs_wei": "invalid"},
    }
    opp = _scaled_opp(meta=meta)

    scaled = svc.scale_opportunity(opp, 0.5)

    assert scaled.expected_profit_raw == "500"
    assert scaled.meta["profit_after_costs"] == "0"
    assert scaled.meta["safety"]["profit_after_costs_wei"] == "0"
    assert scaled.meta["brain"]["profit_after_costs_sync"] == "invalid_input_zeroed"


def test_receipt_service_skips_bankroll_and_efficiency_when_settled_profit_truth_missing(tmp_path):
    recorded = []
    eff_points = []
    runtime = SimpleNamespace(
        metrics=SimpleNamespace(succeeded=0, failed=0),
        _bankroll=SimpleNamespace(record_trade=lambda **kwargs: recorded.append(kwargs)),
        _eff=SimpleNamespace(add=lambda point: eff_points.append(point)),
        _cb=SimpleNamespace(record_result=lambda **kwargs: None),
    )
    svc = ReceiptService()

    truth = svc.settled_outcome_truth(status=1, decoded={})
    assert truth["ok"] is False
    assert truth["reason_code"] == "settled_profit_truth_unavailable"

    svc.record_trade_outcome(
        runtime,
        status=1,
        realized_after=25,
        expected_after=30,
        amount_in=100,
        latency_ms=50,
        mode="auto",
        outcome_truth_ok=False,
        outcome_truth_reason_code=truth["reason_code"],
    )

    assert runtime.metrics.succeeded == 1
    assert runtime.metrics.failed == 0
    assert recorded == []
    assert eff_points == []


def test_capital_explanation_service_holds_route_invalid_candidate(tmp_path):
    rt = DummyRuntime(tmp_path)
    rt.execution_live_state = lambda: {
        'items': [
            {
                'routeFamily': 'flashloan_atomic',
                'family': 'flashloan_atomic',
                'lane': 'PRIVATE',
                'endpoint': 'rpc-fast',
                'selectedVenues': ['uni', 'curve'],
                'sizeMult': 1.0,
                'expectedValue': 8.5,
                'routeExecutable': False,
                'routeInvalidCauses': ['route_plan_not_executable'],
                'routeRuntimeDegraded': False,
                'routeRuntimeReasonCodes': [],
                'metadata': {
                    'pipeline_latency_ms': 120,
                    'execution_route_plan': {
                        'selected_venues': ['uni', 'curve'],
                        'executable': False,
                        'route_invalid_causes': ['route_plan_not_executable'],
                    },
                    'endpoint_selection': {'endpoint': 'rpc-fast', 'reason': 'quality_ranked'},
                    'adversarial_state': {'post_ordering_realized_edge': 6.1},
                    'envelope': {'route_family': 'flashloan_atomic'},
                },
            }
        ]
    }
    svc = CapitalExplanationService()
    out = svc.explain(rt)
    assert out['ok'] is True
    assert out['facts']['routeExecutable'] is False
    assert 'route_plan_not_executable' in out['causal']['whyRoute']
    assert out['causal']['whyNot'][0]['candidate'] == 'no_trade'
