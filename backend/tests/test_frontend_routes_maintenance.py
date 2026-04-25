import asyncio
from collections import Counter
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.api_legacy import router as legacy_router
from victor_ai_bot.api_routes.frontend_routes import router as frontend_router
from victor_ai_bot.server import app


class _FrontendRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
        self._subscribe_payloads = [
            {"type": "tick", "chain": "should-hide", "profit": "1"},
            {"type": "tick", "profit": "2"},
            {
                "data": {
                    "chain": "ethereum",
                    "metrics": {
                        "last_block": 321,
                        "scan_ms": 9,
                        "attempted": 1,
                        "succeeded": 1,
                        "failed": 0,
                        "flashLoans": 1,
                        "realized_profit_raw": "7",
                        "efficiency_pct": 50.0,
                        "success_rate_pct": 100.0,
                        "gas_mode": "fast",
                        "send_mode": "private",
                    },
                    "opportunities": [
                        {
                            "id": "opp-gross-only",
                            "strategy": "flash_arb",
                            "expected_profit_raw": "12000",
                            "can_execute": True,
                            "route_id": "route-gross",
                            "meta": {"profit_after_gas_estimate_wei": "9"},
                        },
                        {
                            "id": "opp-after-cost",
                            "strategy": "flash_arb",
                            "expected_profit_raw": "100",
                            "can_execute": True,
                            "route_id": "route-after",
                            "meta": {
                                "profit_after_costs": "250",
                                "profit_after_gas_estimate_wei": "9",
                                "safety": {"exec_ready": True},
                            },
                        },
                    ],
                }
            },
        ]
        self.unsubscribed = 0

    def subscribe(self):
        q = asyncio.Queue()
        payload = self._subscribe_payloads.pop(0)
        q.put_nowait(payload)
        return q

    def unsubscribe(self, q):
        self.unsubscribed += 1

    def drawdown_state(self):
        return {"drawdownPct": 0.0, "hardStop": {"active": False, "reason_codes": []}}

    def kill_switch_state(self):
        return {"metrics": {}, "suppressions": {}, "history": []}


def _route_paths(router):
    return {getattr(route, "path", "") for route in getattr(router, "routes", [])}


def test_frontend_routes_live_in_canonical_router_not_legacy():
    expected = {"/admin", "/ws", "/ws/multichain", "/ws/summary", "/ws/narrative"}
    assert expected.issubset(_route_paths(frontend_router))
    assert expected.isdisjoint(_route_paths(legacy_router))


def test_frontend_routes_mounted_once_on_app():
    counts = Counter(getattr(route, "path", "") for route in app.routes)
    for path in ("/admin", "/ws", "/ws/multichain", "/ws/summary", "/ws/narrative"):
        assert counts[path] == 1


def test_frontend_routes_admin_and_websocket_smoke(monkeypatch):
    runtime = _FrontendRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    admin = client.get("/admin")
    assert admin.status_code == 200
    assert "x∆v Admin" in admin.text

    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "tick"
        assert "chain" not in msg
        assert msg["profit"] == "1"

    with client.websocket_connect("/ws/multichain") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "tick"
        assert msg["chain"] == "ethereum"
        assert msg["profit"] == "2"

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["summaryContract"]["truthFamily"] == "frontend_runtime"
        assert (
            msg["data"]["summaryContract"]["readModel"] == "frontend_runtime_summary_projection_v1"
        )
        assert msg["data"]["block"] == 321
        assert msg["data"]["top_opportunity"]["strategy"] == "flash_arb"
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["expected_profit_after_costs_wei"] == "250"
        assert msg["data"]["top_opportunity"]["profit_after_costs_verified"] is True
        assert msg["data"]["top_opportunity"]["execution_ready"] is True
        assert msg["data"]["top_opportunity"]["execution_ready_reason"] == "ok"
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is True
        assert msg["data"]["top_opportunity"]["selected_on_after_costs"] is True
        assert msg["data"]["top_opportunity"]["selected_on_execution_eligibility"] is True

    assert runtime.unsubscribed == 3


class _FrontendBlockedRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [self._subscribe_payloads[-1]]

    def drawdown_state(self):
        return {
            "drawdownPct": 9.0,
            "hardStop": {"active": True, "reason_codes": ["drawdown_hard_stop"]},
        }


class _FrontendAutoTradeRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 3,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "capital_truth",
            "history_stage": "fund_hold",
            "history_reason_code": "capital_truth_unavailable",
            "history_reason_codes": ["capital_truth_unavailable"],
            "history_next_action": "restore_capital_truth",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "capital_truth_unavailable",
            "component_reliability_reason_codes": ["capital_truth_unavailable"],
            "component_reliability_next_action": "restore_capital_truth",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return [
            {
                "component": "auto_trade_admission",
                "reason_code": "capital_truth_unavailable",
                "stage": "fund_hold",
            }
        ]


class _FrontendAutoTradeRecoveryRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [self._subscribe_payloads[-1]]
        self._auto_trade_recovery_repo = _FrontendAutoTradeRecoveryRepo()


class _FrontendRouteInvalidRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [
            {
                "data": {
                    "chain": "ethereum",
                    "metrics": {
                        "last_block": 333,
                        "scan_ms": 5,
                        "attempted": 1,
                        "succeeded": 0,
                        "failed": 0,
                        "flashLoans": 0,
                        "realized_profit_raw": "0",
                        "efficiency_pct": 0.0,
                        "success_rate_pct": 0.0,
                        "gas_mode": "fast",
                        "send_mode": "private",
                    },
                    "opportunities": [
                        {
                            "id": "opp-route-invalid",
                            "strategy": "flash_arb",
                            "expected_profit_raw": "1000",
                            "can_execute": True,
                            "route_id": "route-invalid",
                            "meta": {
                                "profit_after_costs": "500",
                                "safety": {"exec_ready": True},
                                "execution_route_plan": {
                                    "executable": False,
                                    "route_invalid_causes": ["leg:0:venue-a:invalid"],
                                },
                                "route_invalid_causes": ["leg:0:venue-a:invalid"],
                            },
                        },
                        {
                            "id": "opp-route-ready",
                            "strategy": "flash_arb",
                            "expected_profit_raw": "100",
                            "can_execute": True,
                            "route_id": "route-ready",
                            "meta": {
                                "profit_after_costs": "250",
                                "safety": {"exec_ready": True},
                                "execution_route_plan": {"executable": True},
                            },
                        },
                    ],
                }
            }
        ]


def test_frontend_summary_websocket_prefers_route_ready_after_cost_opportunity(monkeypatch):
    runtime = _FrontendRouteInvalidRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["top_opportunity"]["id"] == "opp-route-ready"
        assert msg["data"]["top_opportunity"]["execution_ready"] is True
        assert msg["data"]["top_opportunity"]["meta"]["route_plan_executable"] is True


class _FrontendLiveAdmissionBlockRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [self._subscribe_payloads[-1]]
        self._execution_service = SimpleNamespace(
            auto_trade_admission_gate=lambda runtime, opportunity, override: SimpleNamespace(
                allowed=False,
                stage="treasury_hold",
                reason="maximum_disabled",
                gate={
                    "blocked": True,
                    "reason_code": "maximum_disabled",
                    "reason_codes": ["maximum_disabled"],
                    "suggested_next_action": "enable_maximum_or_reduce_aggressiveness",
                },
            )
        )


def test_frontend_summary_websocket_surfaces_live_auto_trade_admission_gate(monkeypatch):
    runtime = _FrontendLiveAdmissionBlockRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["auto_trade_gate"]["allowed"] is False
        assert msg["data"]["auto_trade_gate"]["stage"] == "treasury_hold"
        assert msg["data"]["auto_trade_gate"]["reason_code"] == "maximum_disabled"
        assert (
            msg["data"]["auto_trade_gate"]["next_action"]
            == "enable_maximum_or_reduce_aggressiveness"
        )
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["auto_trade_allowed"] is False
        assert msg["data"]["top_opportunity"]["auto_trade_gate_reason_code"] == "maximum_disabled"
        assert (
            msg["data"]["top_opportunity"]["auto_trade_recovery_status"]
            == "treasury_alignment_required"
        )
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False


def test_frontend_summary_websocket_surfaces_auto_trade_recovery_gate(monkeypatch):
    runtime = _FrontendAutoTradeRecoveryRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["auto_trade_gate"]["allowed"] is False
        assert msg["data"]["auto_trade_gate"]["stage"] == "fund_hold"
        assert msg["data"]["auto_trade_gate"]["reason_code"] == "capital_truth_unavailable"
        assert msg["data"]["auto_trade_gate"]["next_action"] == "restore_capital_truth"
        assert msg["data"]["auto_trade_recovery"]["blocked"] is True
        assert msg["data"]["auto_trade_recovery"]["ready"] is False
        assert msg["data"]["auto_trade_recovery"]["status"] == "fund_hold_active"
        assert msg["data"]["auto_trade_recovery"]["history_stage"] == "fund_hold"
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["auto_trade_allowed"] is False
        assert (
            msg["data"]["top_opportunity"]["auto_trade_gate_reason_code"]
            == "capital_truth_unavailable"
        )
        assert msg["data"]["top_opportunity"]["auto_trade_recovery_status"] == "fund_hold_active"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is False
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False


def test_frontend_summary_websocket_surfaces_global_execution_gate(monkeypatch):
    runtime = _FrontendBlockedRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["execution_gate"]["blocked"] is True
        assert msg["data"]["execution_gate"]["reason_code"] == "drawdown_hard_stop"
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is False
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False
        assert msg["data"]["top_opportunity"]["execution_gate_reason_code"] == "drawdown_hard_stop"


class _FrontendCapitalHoldRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [self._subscribe_payloads[-1]]
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "holdReasonCode": "capital_truth_degraded",
                    "holdReasonCodes": ["capital_truth_degraded"],
                    "capitalTruthReasonCodes": ["capital_truth_degraded"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


def test_frontend_summary_websocket_surfaces_capital_truth_hold(monkeypatch):
    runtime = _FrontendCapitalHoldRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["execution_gate"]["blocked"] is False
        assert msg["data"]["hold"]["blocked"] is True
        assert msg["data"]["hold"]["reason_code"] == "capital_truth_degraded"
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is False
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False
        assert msg["data"]["top_opportunity"]["hold_reason_code"] == "capital_truth_degraded"


class _FrontendCapitalUnavailableRuntime(_FrontendRuntime):
    def __init__(self):
        super().__init__()
        self._subscribe_payloads = [self._subscribe_payloads[-1]]
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "holdReasonCode": "capital_truth_unavailable",
                    "holdReasonCodes": ["capital_truth_unavailable"],
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


def test_frontend_summary_websocket_surfaces_capital_truth_unavailable_hold(monkeypatch):
    runtime = _FrontendCapitalUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["execution_gate"]["blocked"] is False
        assert msg["data"]["hold"]["blocked"] is True
        assert msg["data"]["hold"]["reason_code"] == "capital_truth_unavailable"
        assert msg["data"]["hold"]["recovery_status"] == "capital_truth_restore_required"
        assert msg["data"]["hold"]["recovery_reason_code"] == "capital_truth_unavailable"
        assert msg["data"]["hold"]["recovery_reason_codes"] == ["capital_truth_unavailable"]
        assert msg["data"]["hold"]["recovery_next_action"] == "restore_capital_truth"
        assert msg["data"]["hold"]["recovery_ready"] is False
        assert msg["data"]["top_opportunity"]["id"] == "opp-after-cost"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is False
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False
        assert msg["data"]["top_opportunity"]["hold_reason_code"] == "capital_truth_unavailable"


def test_frontend_summary_websocket_surfaces_family_hardening_service_hold(monkeypatch):
    runtime = _FrontendCapitalUnavailableRuntime()
    runtime._fund_service = SimpleNamespace(
        summary=lambda runtime: {
            "ok": True,
            "health": {
                "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                "recoveryReady": True,
                "recoveryStatus": "ready",
                "recoveryReasonCode": "ok",
                "recoveryReasonCodes": [],
            },
        }
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "summary"
        assert msg["data"]["hold"]["blocked"] is True
        assert msg["data"]["hold"]["reason_code"] == "family_hardening_service_unavailable"
        assert msg["data"]["hold"]["reason_codes"] == ["family_hardening_service_unavailable"]
        assert msg["data"]["hold"]["family_hardening_reason_codes"] == [
            "family_hardening_service_unavailable"
        ]
        assert msg["data"]["hold"]["recovery_status"] == "family_hardening_restore_required"
        assert msg["data"]["hold"]["recovery_reason_code"] == "family_hardening_service_unavailable"
        assert msg["data"]["hold"]["recovery_reason_codes"] == [
            "family_hardening_service_unavailable"
        ]
        assert msg["data"]["hold"]["recovery_reliability_class"] == "unavailable"
        assert (
            msg["data"]["hold"]["recovery_reliability_reason_code"]
            == "recovery_reliability_unavailable"
        )
        assert msg["data"]["hold"]["recovery_next_action"] == "restore_family_hardening"
        assert msg["data"]["hold"]["recovery_ready"] is False
        assert msg["data"]["execution_advisory"]["active"] is True
        assert msg["data"]["execution_advisory"]["class"] == "unavailable"
        assert (
            msg["data"]["execution_advisory"]["reason_code"] == "recovery_reliability_unavailable"
        )
        assert msg["data"]["execution_advisory"]["next_action"] == "restore_family_hardening"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is False
        assert msg["data"]["top_opportunity"]["can_execute_after_costs"] is False
        assert (
            msg["data"]["top_opportunity"]["hold_reason_code"]
            == "family_hardening_service_unavailable"
        )


def test_ws_summary_surfaces_recovery_freshness_when_capital_truth_is_unavailable(monkeypatch):
    runtime = _FrontendCapitalUnavailableRuntime()
    runtime._fund_service = SimpleNamespace(
        summary=lambda runtime: {
            "ok": True,
            "health": {
                "holdReasonCode": "capital_truth_unavailable",
                "holdReasonCodes": ["capital_truth_unavailable"],
                "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                "suggestedNextAction": "restore_capital_truth",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_unavailable",
                "recoveryReasonCodes": ["capital_truth_unavailable"],
                "recoveryNextAction": "restore_capital_truth",
                "recoveryFreshnessClass": "unavailable",
                "recoveryFreshnessReasonCode": "capital_truth_freshness_unavailable",
                "recoveryFreshnessReasonCodes": ["capital_truth_freshness_unavailable"],
                "recoveryFreshnessNextAction": "refresh_capital_truth_snapshot",
            },
        }
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["data"]["hold"]["recovery_freshness_class"] == "unavailable"
        assert (
            msg["data"]["hold"]["recovery_freshness_reason_code"]
            == "capital_truth_freshness_unavailable"
        )
        assert msg["data"]["hold"]["recovery_freshness_reason_codes"] == [
            "capital_truth_freshness_unavailable"
        ]
        assert (
            msg["data"]["hold"]["recovery_freshness_next_action"]
            == "refresh_capital_truth_snapshot"
        )


def test_summary_websocket_surfaces_recovery_history_count_and_severity_for_capital_truth_hold(
    monkeypatch,
):
    runtime = _FrontendCapitalUnavailableRuntime()
    runtime._fund_service = SimpleNamespace(
        summary=lambda runtime: {
            "ok": True,
            "health": {
                "holdReasonCode": "capital_truth_unavailable",
                "holdReasonCodes": ["capital_truth_unavailable"],
                "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                "suggestedNextAction": "restore_capital_truth",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_unavailable",
                "recoveryReasonCodes": ["capital_truth_unavailable"],
                "recoveryHistoryComponent": "capital_truth",
                "recoveryHistoryStatus": "degraded",
                "recoveryDegradedCount": 4,
                "recoveryLastHealthyTsMs": 1700000000000,
                "recoveryDegradationSeverityClass": "persistent",
            },
        }
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)
    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
    assert msg["data"]["hold"]["recovery_degraded_count"] == 4
    assert int(msg["data"]["hold"]["recovery_last_healthy_ts_ms"]) == 1700000000000
    assert msg["data"]["hold"]["recovery_degradation_severity_class"] == "persistent"


def test_frontend_summary_websocket_surfaces_recovery_reliability_for_capital_truth_unavailable(
    monkeypatch,
):
    class Runtime(_FrontendRuntime):
        def __init__(self):
            super().__init__()
            self._subscribe_payloads = [self._subscribe_payloads[-1]]
            self._fund_service = SimpleNamespace(
                summary=lambda runtime: {
                    "ok": True,
                    "health": {
                        "holdReasonCode": "capital_truth_unavailable",
                        "holdReasonCodes": ["capital_truth_unavailable"],
                        "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                        "recoveryStatus": "capital_truth_restore_required",
                        "recoveryReasonCode": "capital_truth_unavailable",
                        "recoveryReasonCodes": ["capital_truth_unavailable"],
                        "capitalTruthReliabilityClass": "unavailable",
                        "capitalTruthReliabilityReasonCode": "capital_truth_reliability_unavailable",
                        "capitalTruthReliabilityReasonCodes": [
                            "capital_truth_reliability_unavailable",
                            "capital_truth_freshness_unavailable",
                        ],
                        "recoveryReliabilityClass": "unavailable",
                        "recoveryReliabilityReasonCode": "recovery_reliability_unavailable",
                        "recoveryReliabilityReasonCodes": [
                            "recovery_reliability_unavailable",
                            "capital_truth_reliability_unavailable",
                        ],
                        "recoveryReliabilityNextAction": "restore_capital_truth",
                    },
                }
            )

    monkeypatch.setattr(app.state, "runtime", Runtime(), raising=False)
    client = TestClient(app)
    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["data"]["hold"]["recovery_reliability_class"] == "unavailable"
        assert (
            msg["data"]["hold"]["recovery_reliability_reason_code"]
            == "recovery_reliability_unavailable"
        )
        assert msg["data"]["hold"]["recovery_reliability_next_action"] == "restore_capital_truth"


def test_ws_summary_surfaces_execution_advisory_for_fragile_recovery_reliability(monkeypatch):
    from fastapi.testclient import TestClient
    from victor_ai_bot.server import app

    class Runtime:
        def __init__(self):
            self.cfg = SimpleNamespace(chain=SimpleNamespace(name="ethereum"))
            self._opps = [
                SimpleNamespace(
                    id="opp-1",
                    strategy="flash_arb",
                    expected_profit_raw="100",
                    can_execute=True,
                    route_id="r-1",
                    meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
                )
            ]
            self._drawdown_state = SimpleNamespace(
                snapshot=lambda: {
                    "drawdownPct": 0.0,
                    "hardStop": {"active": False, "reason_codes": []},
                }
            )
            self._kill_switch = SimpleNamespace(
                snapshot=lambda: {"metrics": {}, "suppressions": {}, "history": []}
            )
            self._fund_service = SimpleNamespace(
                summary=lambda runtime: {
                    "ok": True,
                    "health": {
                        "recoveryReliabilityClass": "fragile",
                        "recoveryReliabilityReasonCode": "recovery_reliability_fragile",
                        "recoveryReliabilityReasonCodes": [
                            "recovery_reliability_fragile",
                            "recovery_recovered_fragile",
                        ],
                        "recoveryReliabilityNextAction": "repair_internal_prime_accounting",
                    },
                }
            )

        def subscribe(self):
            class _Q:
                def __init__(self, items):
                    self.items = items

                async def get(self):
                    if not self.items:
                        from starlette.websockets import WebSocketDisconnect

                        raise WebSocketDisconnect()
                    return self.items.pop(0)

            return _Q(
                [
                    {
                        "data": {
                            "chain": "ethereum",
                            "metrics": {"last_block": 1, "scan_ms": 5},
                            "opportunities": self._opps,
                        }
                    }
                ]
            )

        def unsubscribe(self, q):
            return None

    monkeypatch.setattr(app.state, "runtime", Runtime(), raising=False)
    client = TestClient(app)
    with client.websocket_connect("/ws/summary") as ws:
        msg = ws.receive_json()
        assert msg["data"]["execution_advisory"]["active"] is True
        assert msg["data"]["execution_advisory"]["class"] == "fragile"
        assert msg["data"]["execution_advisory"]["reason_code"] == "recovery_reliability_fragile"
        assert msg["data"]["top_opportunity"]["execution_allowed"] is True
        assert msg["data"]["top_opportunity"]["execution_advisory_active"] is True
        assert msg["data"]["top_opportunity"]["execution_advisory_class"] == "fragile"
