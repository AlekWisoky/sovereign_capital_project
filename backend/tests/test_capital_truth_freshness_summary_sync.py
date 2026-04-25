from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.fund_service import FundService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.server import app


class _FundSummaryFreshnessRuntime:
    _fund_service = FundService()

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "ok",
            "ts_ms": 1_000_000,
            "ledger": {"last_ts_ms": 1_000_000 - (30 * 60 * 60 * 1000)},
        }

    def doctrine_state(self):
        return {"ok": True, "optimizationObjectives": {}}

    def ledger_state(self):
        return {"balances": {}, "tail": [], "transactions": []}

    def internal_prime_state(self):
        return {
            "ok": True,
            "stateReady": True,
            "stateStatus": "ok",
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
        }

    def family_hardening_state(self):
        return {"ok": True, "status": "ok", "items": []}

    def endpoint_quality_state(self):
        return {}

    def endpoint_universe_state(self):
        return {}

    def route_quality_state(self):
        return {}

    def capital_engine_state(self):
        return {"capital_engine": {}, "capital_efficiency_metrics": {}, "reinvestment_policy": {}}


def test_fund_summary_health_elevates_stale_capital_truth_freshness_into_recovery_block():
    runtime = _FundSummaryFreshnessRuntime()
    summary = runtime._fund_service.summary(runtime)
    health = summary["health"]
    assert health["capitalTruthStatus"] == "degraded"
    assert health["capitalTruthReasonCodes"] == ["capital_truth_freshness_stale"]
    assert health["holdReasonCode"] == "capital_truth_freshness_stale"
    assert health["suggestedNextAction"] == "refresh_capital_truth_snapshot"
    assert health["recoveryStatus"] == "capital_truth_restore_required"
    assert health["recoveryReasonCode"] == "capital_truth_freshness_stale"
    assert health["recoveryReasonCodes"] == ["capital_truth_freshness_stale"]
    assert health["recoveryNextAction"] == "refresh_capital_truth_snapshot"


class _SystemSummaryFreshnessRuntime:
    def __init__(self):
        self._analytics_service = SimpleNamespace(
            system_summary=lambda runtime: {"ok": True, "services": {}}
        )
        self._execution_service = SimpleNamespace(
            summarize=lambda runtime: {
                "stateContract": {
                    "phase": "execution",
                    "status": "ok",
                    "reason_code": "ok",
                    "degraded": False,
                    "blocked": False,
                    "denied": False,
                    "sticky_cycle": True,
                    "details": {},
                }
            }
        )

    def service_health_state(self):
        return {"admission": {"ok": True}}

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "ok",
            "ts_ms": 1_000_000,
            "ledger": {"last_ts_ms": 1_000_000 - (30 * 60 * 60 * 1000)},
        }

    def family_hardening_state(self):
        return {"ok": True, "status": "ok", "items": []}

    def fund_summary_state(self):
        return {
            "ok": True,
            "health": {
                "capitalTruthStatus": "degraded",
                "capitalTruthReasonCodes": ["capital_truth_freshness_stale"],
                "holdReasonCode": "capital_truth_freshness_stale",
                "holdReasonCodes": ["capital_truth_freshness_stale"],
                "suggestedNextAction": "refresh_capital_truth_snapshot",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_freshness_stale",
                "recoveryReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryNextAction": "refresh_capital_truth_snapshot",
                "capitalTruthObservedTsMs": 1_000_000,
                "capitalTruthLedgerLastTsMs": 1_000_000 - (30 * 60 * 60 * 1000),
                "capitalTruthAgeMs": 30 * 60 * 60 * 1000,
                "capitalTruthFreshnessClass": "stale",
                "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryFreshnessClass": "stale",
                "recoveryFreshnessReasonCode": "capital_truth_freshness_stale",
                "recoveryFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryFreshnessNextAction": "refresh_capital_truth_snapshot",
                "capitalTruthRecoveryHistoryStatus": "degraded",
                "capitalTruthDegradedCount": 1,
                "capitalTruthDegradationSeverityClass": "acute",
                "capitalTruthReliabilityClass": "fragile",
                "capitalTruthReliabilityReasonCode": "capital_truth_reliability_fragile",
                "capitalTruthReliabilityReasonCodes": [
                    "capital_truth_reliability_fragile",
                    "capital_truth_freshness_stale",
                ],
            },
        }


def test_system_summary_surfaces_capital_truth_health_and_degraded_contract(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _SystemSummaryFreshnessRuntime(), raising=False)
    client = TestClient(app)

    body = client.get("/api/system/summary").json()

    assert body["capitalTruthHealth"]["status"] == "degraded"
    assert body["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert body["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert body["serviceContracts"]["capitalTruth"]["status"] == "blocked"
    assert (
        body["serviceContracts"]["capitalTruth"]["reason_code"] == "capital_truth_freshness_stale"
    )
    assert body["stateContract"]["status"] == "blocked"
    assert body["stateContract"]["reason_code"] == "capital_truth_freshness_stale"


class _OperatorSummaryFreshnessRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum", chain_id=1),
            execution=SimpleNamespace(auto_trading=True),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(model_dump=lambda: {})
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=False,
                sandbox_only=False,
                defensive_mode=False,
                full_system_enabled=False,
                mutation_enabled=False,
                evolution_frozen=True,
            ),
            snapshot=lambda: {"fundStage": "internal_capital"},
            audit=SimpleNamespace(tail=lambda limit=250: []),
            state=lambda: {"degraded": False},
        )
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "fundStage": "internal_capital",
                    "riskPosture": "defensive",
                    "riskScore": 0.2,
                    "capitalTruthStatus": "degraded",
                    "capitalTruthReasonCodes": ["capital_truth_freshness_stale"],
                    "holdReasonCode": "capital_truth_freshness_stale",
                    "holdReasonCodes": ["capital_truth_freshness_stale"],
                    "suggestedNextAction": "refresh_capital_truth_snapshot",
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_freshness_stale",
                    "recoveryReasonCodes": ["capital_truth_freshness_stale"],
                    "recoveryNextAction": "refresh_capital_truth_snapshot",
                    "capitalTruthObservedTsMs": 1_000_000,
                    "capitalTruthLedgerLastTsMs": 1_000_000 - (30 * 60 * 60 * 1000),
                    "capitalTruthAgeMs": 30 * 60 * 60 * 1000,
                    "capitalTruthFreshnessClass": "stale",
                    "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                    "recoveryFreshnessClass": "stale",
                    "recoveryFreshnessReasonCode": "capital_truth_freshness_stale",
                    "recoveryFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                    "recoveryFreshnessNextAction": "refresh_capital_truth_snapshot",
                    "capitalTruthRecoveryHistoryStatus": "degraded",
                    "capitalTruthDegradedCount": 1,
                    "capitalTruthDegradationSeverityClass": "acute",
                    "capitalTruthReliabilityClass": "fragile",
                    "capitalTruthReliabilityReasonCode": "capital_truth_reliability_fragile",
                    "capitalTruthReliabilityReasonCodes": [
                        "capital_truth_reliability_fragile",
                        "capital_truth_freshness_stale",
                    ],
                },
            }
        )
        self._telemetry_service = SimpleNamespace(service_health=lambda runtime: {})
        self._execution_service = SimpleNamespace(build_live_state=lambda runtime: {"items": []})
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {"hardStop": {"active": False, "reason_codes": []}}
        )
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(snapshot=lambda: {"configured": True})
        self._agent_attribution = SimpleNamespace(summary=lambda: {"agents": []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {"items": []})
        self._endpoint_universe = SimpleNamespace(snapshot=lambda: {"private": {}})
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": []})
        self._telemetry = SimpleNamespace(summary=lambda: {})
        self._launch = SimpleNamespace(summary=lambda **kwargs: {"ok": True, "launch": {}})
        self._pnl = SimpleNamespace(summary=lambda window=50: {})
        self._super = None
        self._inl = None
        self._fioa = None
        self._treasury = None
        self._gov = None
        self._blockspace = None
        self._consensus = None
        self._behave = None
        self._omni = None
        self._agent_hub = None
        self._wealth_goal_service = SimpleNamespace(summary=lambda runtime: {})
        self._replay_service = SimpleNamespace(summary=lambda runtime: {})
        self._admission_service = SimpleNamespace(summary=lambda runtime: {})
        self._receipt_service = SimpleNamespace(summary=lambda runtime: {})
        self._analytics_service = None
        self._decision = None
        self._orchestrator = None
        self._withdraw_all_service = None
        self._capital_truth_service = None
        self._opps = []
        self._pending = {}
        self._auto_trading = True

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "ok",
            "ts_ms": 1_000_000,
            "ledger": {"last_ts_ms": 1_000_000 - (30 * 60 * 60 * 1000)},
        }

    def chain_state(self):
        return {"name": "ethereum", "chain_id": 1}

    def telemetry_summary(self):
        return {}

    def execution_calibration_state(self):
        return {"items": []}

    def agent_hub_state(self):
        return {"state": {}}

    def capital_engine_state(self):
        return {"capital_engine": {}, "capital_efficiency_metrics": {}, "reinvestment_policy": {}}

    def endpoint_quality_state(self):
        return {}

    def drawdown_state(self):
        return {"hardStop": {"active": False, "reason_codes": []}}

    def kill_switch_state(self):
        return {"suppressions": {}}

    def endpoint_universe_state(self):
        return {"private": {}}

    def venue_scorecards_state(self):
        return {"pairs": {}}

    def route_quality_state(self):
        return {"items": []}

    def execution_live_state(self):
        return {"items": []}

    def service_health_state(self):
        return {}

    def family_hardening_state(self):
        return {"ok": True, "status": "ok", "items": []}


def test_operator_summary_surfaces_capital_truth_health_contract():
    payload = asyncio.run(
        OperatorSummaryService().build_snapshot(_OperatorSummaryFreshnessRuntime())
    )
    assert payload["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert payload["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert payload["capitalTruthHealth"]["stateContract"]["status"] == "blocked"
    assert payload["capital"]["capitalTruthHealth"]["reasonCode"] == "capital_truth_freshness_stale"


from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.state_service import StateService


class _TreasuryAndStateFreshnessRuntime(_SystemSummaryFreshnessRuntime):
    def __init__(self):
        super().__init__()
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum", chain_id=1),
            execution=SimpleNamespace(
                auto_trading=True,
                gas_mode="fast",
                send_mode="private",
                brain_mode="adaptive",
                dry_run=False,
                withdraw_mode="txdata",
            ),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(
            model_dump=lambda: {"gas_mode": "fast", "send_mode": "private"}
        )
        self._opps = []
        self._pending = {}
        self._auto_trading = True
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=1, max_borrow_amount_wei=2),
            state=SimpleNamespace(
                realized_profit_wei=0, last_amount_in_wei=0, success_streak=0, fail_streak=0
            ),
            success_rate_pct=lambda: 0.0,
        )
        self.rpc_manager = SimpleNamespace(snapshot=lambda: {"read": [], "send": []})
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 0.0, "success_rate_pct": 0.0}
        )

    def treasury_state(self):
        return {"ok": True, "enabled": True, "allocator": "treasury"}

    def capital_engine_state(self):
        return {"capital_engine": {}, "capital_efficiency_metrics": {}, "reinvestment_policy": {}}

    def ledger_state(self):
        return {"balances": {}, "tail": [], "transactions": []}

    def internal_prime_state(self):
        return {
            "ok": True,
            "stateReady": True,
            "stateStatus": "ok",
            "borrowedUsd": 0.0,
            "capacityUsd": 0.0,
            "utilization": 0.0,
            "inventory": {},
            "familyExposure": {},
            "openLoans": [],
            "disputedLoans": [],
            "loanCount": 0,
            "disputedLoanCount": 0,
        }

    def doctrine_state(self):
        return {"ok": True, "optimizationObjectives": {}}

    def execution_live_state(self):
        return {"items": []}

    async def snapshot(self):
        return await StateService(auxiliary_state=AuxiliaryStateService()).summary(self)


def test_treasury_route_and_state_summary_surface_capital_truth_health(monkeypatch):
    runtime = _TreasuryAndStateFreshnessRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    treasury = client.get("/api/treasury/state").json()
    assert treasury["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert treasury["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert treasury["serviceContracts"]["capitalTruth"]["status"] == "blocked"

    state_summary = asyncio.run(
        StateService(auxiliary_state=AuxiliaryStateService()).summary(runtime)
    )
    assert state_summary["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert (
        state_summary["treasury"]["capitalTruthHealth"]["reasonCode"]
        == "capital_truth_freshness_stale"
    )

    api_state = client.get("/api/state").json()
    assert api_state["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert (
        api_state["treasury"]["capitalTruthHealth"]["nextAction"]
        == "refresh_capital_truth_snapshot"
    )
