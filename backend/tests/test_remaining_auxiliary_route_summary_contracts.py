from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.api_routes.treasury_extra import treasury_goal as treasury_goal_route
from victor_ai_bot.runtime_services.auxiliary_state_service import (
    AuxiliaryStateService,
    CAPITAL_CONTRACT_VERSION,
    CAPITAL_POLICY_VERSION,
    CapitalTruthSnapshot,
)


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = "0x2222222222222222222222222222222222222222"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _Treasury:
    def __init__(self) -> None:
        self.cfg = SimpleNamespace(
            goal=SimpleNamespace(
                target_return_percentage=12.0,
                time_horizon_seconds=30 * 24 * 60 * 60,
                timeframe_days=30,
                risk_tolerance="moderate",
                max_drawdown_pct=8.0,
                capital_commitment_pct=25.0,
            )
        )

    def snapshot(self) -> dict:
        return {"aggressiveness": {"current_return_pct": 2.5}}


class _CioService:
    def summary(self, runtime) -> dict:
        del runtime
        return {"ok": True, "items": []}


class _Runtime:
    def __init__(self) -> None:
        self.cfg = _Cfg()
        self._cc = None
        self._treasury = _Treasury()
        self._cio_service = _CioService()

    def capital_contract(self) -> dict:
        return {"contractVersion": CAPITAL_CONTRACT_VERSION, "ok": True}

    def capital_policy(self) -> dict:
        return {"contractVersion": CAPITAL_POLICY_VERSION, "ok": True}

    def capital_truth_state(self) -> dict:
        return {"ok": True, "status": "ok", "reason_code": "ok"}

    def service_health_state(self) -> dict:
        return {"ok": True, "services": {"telemetry": {"ok": True}}}

    def unified_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def spread_opportunities(self) -> dict:
        return {"ok": True, "count": 1, "opps": [], "last": {}}

    def orchestrator_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def consensus_state(self) -> dict:
        return {"ok": True, "last": {}, "cfg": {}}

    def behaveagent_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def governance_layer_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def blockspace_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def agent_hub_state(self) -> dict:
        return {"ok": True, "state": {}, "attribution": {"agents": []}, "weights": {}}

    def agent_attribution_state(self) -> dict:
        return {"agents": []}

    def strategy_scorecards_state(self) -> dict:
        return {"families": []}

    def quicksight_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def quicksight_dataset(self, name: str) -> dict:
        return {"ok": True, "dataset": str(name), "rows": []}

    def quicksight_dashboards(self) -> dict:
        return {"ok": True, "dashboards": []}

    def treasury_state(self) -> dict:
        return {"ok": True, "enabled": True}

    def execution_calibration_state(self) -> dict:
        return {"items": []}

    def venue_profiles_state(self) -> dict:
        return {"venues": []}

    def risk_memory_state(self) -> dict:
        return {"failures": {}}

    def path_diversity_state(self) -> dict:
        return {"paths": []}

    def edge_learning_state(self) -> dict:
        return {"items": []}

    def endpoint_quality_state(self) -> dict:
        return {"lanes": {}, "summary": {}, "generatedAtMs": 0}

    def endpoint_universe_state(self) -> dict:
        return {"read": {}, "public": {}, "protected": {}, "private": {}}

    def venue_scorecards_state(self) -> dict:
        return {"pairs": {}}

    def route_quality_state(self) -> dict:
        return {"items": []}

    def execution_live_state(self) -> dict:
        return {"items": []}

    def drawdown_state(self) -> dict:
        return {}

    def kill_switch_state(self) -> dict:
        return {"suppressed": []}

    def capital_engine_state(self) -> dict:
        return {"capital_engine": {}, "capital_efficiency_metrics": {}}


def _capital_truth_snapshot() -> CapitalTruthSnapshot:
    return CapitalTruthSnapshot(
        capital_summary={"ok": True, "lastSettlement": {}, "withdrawal": {"available": True}},
        capital_contract={"ok": True, "contractVersion": CAPITAL_CONTRACT_VERSION},
        capital_policy={"ok": True, "contractVersion": CAPITAL_POLICY_VERSION},
        capital_economic_model={"ok": True, "modelVersion": "capital_economic_model_v1"},
        authority={"ok": True, "mode": "live_rebuilt"},
    )


def test_remaining_auxiliary_dashboard_routes_emit_summary_contracts(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(
        AuxiliaryStateService,
        "capital_truth",
        lambda self, runtime: _capital_truth_snapshot(),
    )
    client = TestClient(app)

    expectations = {
        "/api/system/services": "service_health",
        "/api/system/execution/quality": "execution_quality",
        "/api/unified/state": "unified_state",
        "/api/spread/opportunities": "spread_opportunities",
        "/api/orchestrator/state": "orchestrator_state",
        "/api/consensus/state": "consensus_state",
        "/api/behaveagent/state": "behaveagent_state",
        "/api/governance/state": "governance_layer",
        "/api/blockspace/state": "blockspace_state",
        "/api/agenthub/state": "agent_hub",
        "/api/analytics/state": "analytics_state",
        "/api/analytics/datasets/test": "analytics_dataset",
        "/api/analytics/dashboards": "analytics_dashboards",
        "/api/agents/state": "agent_hub",
        "/api/agents/attribution": "agent_attribution",
        "/api/strategies/scorecards": "strategy_scorecards",
        "/api/risk/live-state": "risk_live_state",
        "/api/risk/cio-summary": "cio_route",
        "/api/treasury/capital": "treasury_capital",
        "/api/treasury/state": "treasury_state",
        "/api/wealth/goal": "wealth_goal",
    }

    for path, family in expectations.items():
        body = client.get(path).json()
        assert body["summaryContract"]["truthFamily"] == family, path
        assert (
            body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
        ), path
        assert body["summaryContract"]["capitalContractVersion"] == CAPITAL_CONTRACT_VERSION, path
        assert body["summaryContract"]["capitalPolicyVersion"] == CAPITAL_POLICY_VERSION, path
    treasury_goal_body = treasury_goal_route(rt=runtime)
    assert treasury_goal_body["summaryContract"]["truthFamily"] == "treasury_goal"
    assert (
        treasury_goal_body["summaryContract"]["contractVersion"]
        == "canonical_summary_read_contract_v1"
    )
    assert (
        treasury_goal_body["summaryContract"]["capitalContractVersion"] == CAPITAL_CONTRACT_VERSION
    )
    assert treasury_goal_body["summaryContract"]["capitalPolicyVersion"] == CAPITAL_POLICY_VERSION
