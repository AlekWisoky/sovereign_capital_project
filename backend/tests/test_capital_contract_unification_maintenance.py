from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.analytics_service import AnalyticsService
from victor_ai_bot.runtime_services.state_service import StateService
from victor_ai_bot.server import app
from victor_ai_bot.runtime_services.capital_truth_read_context import build_capital_truth_read_context
from victor_ai_bot.api_routes.system_routes import _system_summary_payload


class _RpcManager:
    def snapshot(self):
        return {"read": [{"ok": True}], "send": [{"ok": True}], "error_rate": 0.0}


class _Metrics:
    last_block = 123
    scan_ms = 8.5
    gas_mode = "fast"
    send_mode = "private"
    opportunity_rate = 1.2
    realized_profit_raw = "0"
    basefee_gwei = 9.1

    def model_dump(self):
        return {
            "last_block": self.last_block,
            "scan_ms": self.scan_ms,
            "gas_mode": self.gas_mode,
            "send_mode": self.send_mode,
            "opportunity_rate": self.opportunity_rate,
            "realized_profit_raw": self.realized_profit_raw,
            "basefee_gwei": self.basefee_gwei,
        }


class _CapitalContractRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(
                gas_mode="fast",
                send_mode="private",
                brain_mode="adaptive",
                dry_run=False,
                withdraw_mode="txdata",
            ),
        )
        self.metrics = _Metrics()
        self._opps = []
        self._auto_trading = True
        self.rpc_manager = _RpcManager()
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=100, max_borrow_amount_wei=1000),
            state=SimpleNamespace(
                realized_profit_wei=250,
                last_amount_in_wei=125,
                success_streak=3,
                fail_streak=1,
            ),
            success_rate_pct=lambda: 75.0,
        )
        self._treasury = SimpleNamespace(
            snapshot=lambda: {"ok": True, "enabled": True, "allocator": "treasury"},
            cfg=SimpleNamespace(meta={"estimated_capital_wei": 22_000_000_000_000_000_000}),
        )
        self._ledger_repo = SimpleNamespace(
            tail=lambda chain, limit=50: [{"asset": "USD", "delta": 12.5}],
            transactions_tail=lambda chain, limit=50: [
                {
                    "transaction_id": "txn-1",
                    "ts_ms": 101,
                    "tx_type": "receipt_settlement",
                    "metadata": {
                        "net_realized_usd": 2.5,
                        "strategy_family": "flashloan_atomic",
                        "capture_lane": "PRIVATE",
                    },
                }
            ],
        )
        self._ledger = SimpleNamespace(balances=lambda: {"USD": 12.5})
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 1.0})
        self._last_settlement_sync = {"receiptId": "0xabc", "status": "settled"}
        self._last_operator_pnl_summary = {"total_realized_profit_after_gas_usd": 11.0}
        self._analytics_service = AnalyticsService(auxiliary_state=AuxiliaryStateService())
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 88.0, "success_rate_pct": 72.0}
        )

    def telemetry_summary(self):
        return {"ok": True, "tailCount": 1}

    def agent_hub_state(self):
        return {"ok": True, "state": {"agents": 2}}

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 10_000_000_000_000_000_000,
                "reserve_bankroll_wei": 4_000_000_000_000_000_000,
                "experimental_bankroll_wei": 2_000_000_000_000_000_000,
                "drawdown_buffer_wei": 3_000_000_000_000_000_000,
                "treasury_offramp_wei": 1_000_000_000_000_000_000,
                "family_targets": {"flashloan_atomic": 0.5},
                "family_allocations_wei": {"flashloan_atomic": 6_000_000_000_000_000_000},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": 5_000_000_000_000_000_000},
            "reinvestment_policy": {"enabled": True},
        }

    def endpoint_quality_state(self):
        return {"lanes": {"PRIVATE": {"quality": 0.9}}}

    def drawdown_state(self):
        return {"drawdownPct": 1.0, "hardStop": {"active": False}}

    def kill_switch_state(self):
        return {"metrics": {}, "suppressions": {}}

    def endpoint_universe_state(self):
        return {"private": {"candidates": [{"url": "rpc-fast"}]}}

    def venue_scorecards_state(self):
        return {"items": []}

    def route_quality_state(self):
        return {"items": []}

    def execution_live_state(self):
        return {"items": [{"endpoint": "rpc-fast", "lane": "PRIVATE"}]}

    def capital_truth(self):
        return AuxiliaryStateService().capital_truth(self)

    def treasury_state(self):
        return AuxiliaryStateService().treasury_state(self, capital_truth=self.capital_truth())

    def capital_summary(self):
        return self.capital_truth().capital_summary

    def capital_contract(self):
        return self.capital_truth().capital_contract


class _CountingAuxiliaryStateService(AuxiliaryStateService):
    def __init__(self):
        super().__init__()
        self.capital_summary_calls = 0

    def _build_capital_summary(self, runtime):
        self.capital_summary_calls += 1
        return super()._build_capital_summary(runtime)


class _ExplodingCapitalMethodsRuntime(_CapitalContractRuntime):
    def capital_summary(self):  # pragma: no cover - should never be called
        raise AssertionError("runtime.capital_summary should not be called")

    def capital_contract(self):  # pragma: no cover - should never be called
        raise AssertionError("runtime.capital_contract should not be called")

    def capital_policy(self):  # pragma: no cover - should never be called
        raise AssertionError("runtime.capital_policy should not be called")


async def _build_state_summary(runtime: _CapitalContractRuntime):
    return await StateService(auxiliary_state=AuxiliaryStateService()).summary(runtime)


def test_state_summary_and_analytics_share_canonical_capital_contract():
    runtime = _CapitalContractRuntime()

    state_summary = asyncio.run(_build_state_summary(runtime))
    analytics = AnalyticsService(auxiliary_state=AuxiliaryStateService()).system_summary(runtime)
    treasury = runtime.treasury_state()

    assert state_summary["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert analytics["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert treasury["capitalContractVersion"] == "canonical_capital_summary_v1"
    assert "capitalTruthHealth" in state_summary
    assert "capitalTruthHealth" in treasury
    assert treasury["serviceContracts"]["capitalTruth"]["phase"] == "capital_truth_summary"

    assert state_summary["capitalSummary"]["navUsd"] == 12.5
    assert analytics["capitalSummary"]["navUsd"] == 12.5
    assert treasury["capitalSummary"]["navUsd"] == 12.5

    assert state_summary["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert analytics["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert treasury["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert state_summary["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"
    assert state_summary["capital"]["stateContract"]["phase"] == "capital_operator_projection"
    assert analytics["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"


def test_system_summary_and_treasury_routes_expose_canonical_capital_contract(monkeypatch):
    runtime = _CapitalContractRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    system_summary = client.get("/api/system/summary")
    treasury_capital = client.get("/api/treasury/capital")
    treasury_state = client.get("/api/treasury/state")

    assert system_summary.status_code == 200
    assert treasury_capital.status_code == 200
    assert treasury_state.status_code == 200

    system_body = system_summary.json()
    capital_body = treasury_capital.json()
    state_body = treasury_state.json()

    assert system_body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert capital_body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert state_body["capitalContractVersion"] == "canonical_capital_summary_v1"
    assert "capitalTruthHealth" in capital_body
    assert "capitalTruthHealth" in state_body
    assert capital_body["stateContract"]["phase"] == "treasury"
    assert state_body["stateContract"]["phase"] == "treasury"
    assert "capitalPolicy" in capital_body["serviceContracts"]
    assert "runtimeDisable" in state_body["serviceContracts"]

    assert system_body["capitalSummary"]["navUsd"] == 12.5
    assert capital_body["capitalSummary"]["navUsd"] == 12.5
    assert state_body["capitalSummary"]["navUsd"] == 12.5


def test_state_summary_uses_one_canonical_capital_truth_snapshot_per_response():
    runtime = _CapitalContractRuntime()
    aux = _CountingAuxiliaryStateService()

    state_summary = asyncio.run(StateService(auxiliary_state=aux).summary(runtime))

    assert aux.capital_summary_calls == 1
    assert state_summary["capitalSummary"]["navUsd"] == 12.5
    assert state_summary["capitalContract"]["capitalSummary"]["navUsd"] == 12.5
    assert state_summary["treasury"]["capitalSummary"]["navUsd"] == 12.5
    assert state_summary["capitalContract"]["deployableUsd"] == 10.0
    assert state_summary["capitalContract"]["estimatedCapitalUsd"] == 22.0
    assert state_summary["capitalContract"]["internalPrime"]["borrowedUsd"] == 1.0


def test_analytics_and_routes_use_shared_auxiliary_capital_truth_not_runtime_methods(monkeypatch):
    runtime = _ExplodingCapitalMethodsRuntime()
    analytics = AnalyticsService(auxiliary_state=AuxiliaryStateService()).system_summary(runtime)

    assert analytics["capitalSummary"]["navUsd"] == 12.5
    assert analytics["capitalContract"]["deployableUsd"] == 10.0
    assert analytics["capitalPolicy"]["capitalContractVersion"] == "canonical_capital_summary_v1"

    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    system_summary = client.get("/api/system/summary")
    treasury_capital = client.get("/api/treasury/capital")
    treasury_state = client.get("/api/treasury/state")

    assert system_summary.status_code == 200
    assert treasury_capital.status_code == 200
    assert treasury_state.status_code == 200

    system_body = system_summary.json()
    capital_body = treasury_capital.json()
    state_body = treasury_state.json()

    assert system_body["capitalContract"]["deployableUsd"] == 10.0
    assert capital_body["capitalContract"]["estimatedCapitalUsd"] == 22.0
    assert state_body["capitalContract"]["internalPrime"]["borrowedUsd"] == 1.0
    assert (
        system_body["capitalContract"]["capitalSummary"]["navUsd"]
        == system_body["capitalSummary"]["navUsd"]
    )
    assert (
        capital_body["capitalContract"]["capitalSummary"]["navUsd"]
        == capital_body["capitalSummary"]["navUsd"]
    )
    assert (
        state_body["capitalContract"]["capitalSummary"]["navUsd"]
        == state_body["capitalSummary"]["navUsd"]
    )


def test_capital_read_context_reuses_one_canonical_snapshot_across_surfaces_within_same_tick():
    runtime = _CapitalContractRuntime()
    aux = _CountingAuxiliaryStateService()

    ctx_default = build_capital_truth_read_context(runtime, auxiliary_state=aux)
    ctx_health = build_capital_truth_read_context(
        runtime,
        auxiliary_state=aux,
        fund_summary={"capitalTruthStatus": "ok"},
    )
    analytics = AnalyticsService(auxiliary_state=aux).system_summary(runtime)
    treasury = aux.treasury_state(runtime)
    system_summary = _system_summary_payload(runtime)

    assert aux.capital_summary_calls == 1
    assert ctx_default.capital_summary["navUsd"] == 12.5
    assert ctx_health.capital_summary["navUsd"] == 12.5
    assert analytics["capitalSummary"]["navUsd"] == 12.5
    assert treasury["capitalSummary"]["navUsd"] == 12.5
    assert system_summary["capitalSummary"]["navUsd"] == 12.5


def test_capital_read_context_invalidates_when_tick_scope_changes():
    runtime = _CapitalContractRuntime()
    aux = _CountingAuxiliaryStateService()

    build_capital_truth_read_context(runtime, auxiliary_state=aux)
    runtime.metrics.last_block = 124
    build_capital_truth_read_context(runtime, auxiliary_state=aux)

    assert aux.capital_summary_calls == 2
