from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.runtime_services.capital_explanation_service import CapitalExplanationService
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.launch_service import LaunchService
from victor_ai_bot.runtime_services.state_service import StateService


class _LaunchRollout:
    def recommendation(self, **kwargs):
        return {"mode": "FULL_MULTI_STRATEGY", "recommended_next_family": "funding_arb"}

    def family_detail(self, family: str, **kwargs):
        return {"ok": True, "family": family, "enabled": True}


class _LaunchRuntime:
    def __init__(self):
        self._launch_service = LaunchService()
        self._launch_rollout = _LaunchRollout()

    def fund_summary_state(self):
        return {"health": {"fundStage": "internal_capital"}}

    def capital_engine_state(self):
        return {}

    def family_hardening_state(self):
        return {"ok": True, "items": [{"family": "funding_arb", "ready": True}]}


class _CapitalReadRuntime:
    def capital_truth_state(self):
        return CapitalTruthService().summary(self)

    def capital_explain(self):
        return CapitalExplanationService().explain(self)

    def treasury_state(self):
        return {"drawdown_buffer_wei": 0}

    def capital_engine_state(self):
        return {"capital_engine": {}, "capital_efficiency_metrics": {}, "reinvestment_policy": {}}

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

    def launch_state(self):
        return {"profile": {"mode": "FULL_MULTI_STRATEGY"}}

    def ledger_state(self):
        return {"balances": {}, "tail": [], "transactions": []}

    def execution_live_state(self):
        return {"items": []}


class _FakeAuxiliary:
    def capital_truth(self, runtime):
        return SimpleNamespace(
            capital_summary={"navUsd": 10.0},
            capital_contract={"contractVersion": "capital_contract_v1", "status": "ok"},
            capital_policy={"contractVersion": "capital_policy_v1"},
        )

    def treasury_state(self, runtime, capital_truth=None):
        del runtime, capital_truth
        return {"ok": True, "enabled": True, "capitalTruthHealth": {"status": "ok"}}


class _SummaryRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(
                gas_mode="standard",
                send_mode="private",
                brain_mode="off",
                dry_run=True,
                withdraw_mode="txdata",
            ),
        )
        self._opps = []
        self.metrics = SimpleNamespace(
            model_dump=lambda: {"send_mode": "private"},
            realized_profit_raw="0",
            efficiency_pct=0.0,
            success_rate_pct=0.0,
        )
        self.rpc_manager = SimpleNamespace(snapshot=lambda: {"ok": True})
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 0.0, "success_rate_pct": 0.0}
        )
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=0, max_borrow_amount_wei=0),
            state=SimpleNamespace(
                realized_profit_wei=0, last_amount_in_wei=0, success_streak=0, fail_streak=0
            ),
            success_rate_pct=lambda: 0.0,
        )
        self._auto_trading = False
        self._errors = []


def test_launch_and_launch_family_routes_expose_summary_contracts(monkeypatch):
    monkeypatch.setattr(app.state, "runtime", _LaunchRuntime(), raising=False)
    client = TestClient(app)

    state = client.get("/api/launch/state").json()
    detail = client.get("/api/launch/family/funding_arb").json()

    assert state["summaryContract"]["truthFamily"] == "launch"
    assert state["summaryContract"]["readModel"] == "launch_summary_projection_v1"
    assert detail["summaryContract"]["truthFamily"] == "launch_family"
    assert detail["summaryContract"]["readModel"] == "launch_family_projection_v1"


def test_capital_truth_and_explain_routes_expose_summary_contracts(monkeypatch):
    runtime = _CapitalReadRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    fund_capital = client.get("/api/fund/capital-truth").json()
    system_explain = client.get("/api/system/capital/explain").json()

    assert fund_capital["capitalTruth"]["summaryContract"]["truthFamily"] == "capital_truth"
    assert (
        fund_capital["capitalTruth"]["summaryContract"]["readModel"]
        == "capital_truth_projection_v1"
    )
    assert system_explain["summaryContract"]["truthFamily"] == "capital_explain"
    assert system_explain["summaryContract"]["readModel"] == "capital_explanation_projection_v1"


def test_state_service_summary_exposes_runtime_operator_summary_contract():
    runtime = _SummaryRuntime()
    payload = asyncio.run(StateService(auxiliary_state=_FakeAuxiliary()).summary(runtime))

    assert payload["summaryContract"]["truthFamily"] == "runtime_operator"
    assert payload["summaryContract"]["readModel"] == "runtime_operator_summary_projection_v1"
    assert payload["summaryContract"]["capitalContractVersion"] == "capital_contract_v1"
