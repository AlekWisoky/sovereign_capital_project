from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime_services.analytics_service import AnalyticsService
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.command_center_service import CommandCenterService
from victor_ai_bot.runtime_services.launch_service import LaunchService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.server import app


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


class _LaunchRollout:
    def recommendation(self, **kwargs):
        return {
            "currentLaunchMode": "V1_ONLY",
            "activeFamilies": ["flashloan_atomic"],
            "recommended_next_family": "funding_arb",
            "blockedFamilies": {"mev_search": "private_routing_not_ready"},
            "families": [],
            "reasons": ["capital_ready"],
        }

    def family_detail(self, family, **kwargs):
        return {"ok": True, "family": str(family), "status": "eligible"}


class _DashboardRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                auto_trading=True,
                base_borrow_amount="0",
                gas_mode="fast",
                send_mode="private",
                brain_mode="adaptive",
                dry_run=False,
                withdraw_mode="txdata",
            ),
            chain=SimpleNamespace(name="ethereum", chain_id=1),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(
            exec_e2e_p50_ms=10,
            exec_e2e_p90_ms=20,
            exec_e2e_p99_ms=40,
            submit_to_receipt_p50_ms=30,
            submit_to_receipt_p90_ms=50,
            submit_to_receipt_p99_ms=90,
            loop_p50_ms=5,
            loop_p90_ms=10,
            loop_p99_ms=20,
            gas_mode="fast",
            send_mode="private",
            last_tick_ms=7,
            model_dump=lambda: {"gas_mode": "fast", "send_mode": "private"},
        )
        self._opps = []
        self._pending = {}
        self._auto_trading = True
        self.rpc_manager = _RpcManager()
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=False,
                sandbox_only=False,
                defensive_mode=False,
                control_mode="auto",
                governance_enabled=True,
                mutation_enabled=False,
                evolution_frozen=True,
                allocations_frozen=False,
                metrics_enabled=True,
                latency_profiling_enabled=True,
                reward_trace_enabled=True,
                chaos_breakers_enabled=True,
                rpc_batch_enabled=False,
                rft_episode_export_enabled=False,
                kelly_enabled=True,
                auto_reinvest_enabled=False,
                force_send_mode="",
                force_gas_mode="",
                brain_mode="",
                aggression_mode="balanced",
                full_system_enabled=False,
            ),
            audit=SimpleNamespace(tail=lambda limit=250: []),
            state=lambda: {"degraded": False},
            snapshot=lambda: {"fundStage": "internal_capital"},
        )
        self._execution_service = SimpleNamespace(
            build_live_state=lambda runtime: {
                "items": [
                    {
                        "endpoint": "rpc-fast",
                        "lane": "PRIVATE",
                        "metadata": {
                            "envelope": {
                                "route_family": "triangular",
                                "latency_half_life_ms": 900.0,
                                "venues": ["uniswap", "curve"],
                            },
                            "endpoint_selection": {
                                "endpoint": "rpc-fast",
                                "reason": "quality_ranked",
                                "pressure_class": "normal",
                                "universe": {"reason": "private_preferred"},
                                "candidates": [
                                    {"endpoint": "rpc-fast"},
                                    {"endpoint": "rpc-alt"},
                                ],
                            },
                            "route_plan": {
                                "selected_venues": ["uniswap", "curve"],
                                "fallback_tree": [
                                    {
                                        "selected_venues": ["curve"],
                                        "score": 0.4,
                                        "expected_value": 3.0,
                                    }
                                ],
                            },
                            "execution_route_plan": {
                                "selected_venues": ["uniswap", "curve"],
                                "executable": True,
                            },
                            "adversarial_state": {
                                "post_ordering_realized_edge": 4.2,
                                "stale_probability": 0.1,
                                "interference_probability": 0.05,
                                "copy_risk": 0.02,
                                "relay_necessity": True,
                            },
                            "flashloan_resilience": {
                                "selected_provider": "aave",
                                "sizing": {
                                    "borrow_mult": 1.1,
                                    "provider_limit": 50.0,
                                    "route_viability_cap": 25.0,
                                    "pool_depth_cap": 20.0,
                                    "family_budget_cap": 15.0,
                                    "provider_choice_reason": "preferred_provider_selected",
                                },
                            },
                            "pipeline_latency_ms": 120.0,
                        },
                        "routeFamily": "triangular",
                        "family": "flashloan_atomic",
                        "sizeMult": 0.9,
                        "expectedValue": 4.2,
                        "selectedVenues": ["uniswap", "curve"],
                        "routeExecutable": True,
                        "fallbackReady": True,
                        "routeInvalidCauses": [],
                        "flashloan": {
                            "selectedProvider": "aave",
                            "sizing": {"borrow_mult": 1.1},
                        },
                        "adversarial": {"postOrderingRealizedEdge": 4.2},
                    }
                ]
            }
        )
        self._telemetry_service = SimpleNamespace(
            service_health=lambda runtime: {
                "admission": {"ok": True},
                "execution": {"ok": True},
                "receipt": {"ok": True},
                "telemetry": {"ok": True},
            }
        )
        self._endpoint_universe = SimpleNamespace(
            snapshot=lambda: {"private": {"candidates": [{"url": "rpc-fast"}]}}
        )
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": [{"quality": 0.9}]})
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {"drawdownPct": 1.0, "hardStop": {"active": False}}
        )
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(
            snapshot=lambda: {"configured": True, "read": ["rpc-fast"]}
        )
        self._agent_attribution = SimpleNamespace(summary=lambda: {"agents": []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {"items": []})
        self._last_settlement_sync = {
            "ok": True,
            "receiptId": "0xabc",
            "status": "settled",
            "transactionId": "tx123",
        }
        self._ledger = SimpleNamespace(
            tail=lambda limit=50: [
                {
                    "asset": "USD",
                    "amount": 12.5,
                    "entry_type": "realized_pnl",
                    "receipt_id": "0xabc",
                }
            ],
            transactions_tail=lambda limit=50: [
                {
                    "transaction_id": "tx123",
                    "ts_ms": 1700000000000,
                    "tx_type": "receipt_settlement",
                    "receipt_id": "0xabc",
                    "metadata": {
                        "net_realized_usd": 12.5,
                        "strategy_family": "flashloan_atomic",
                        "capture_lane": "PRIVATE",
                        "route_id": "route-1",
                    },
                }
            ],
            balances=lambda: {"USD": 12.5},
        )
        self._ledger_repo = None
        self._internal_prime = SimpleNamespace(
            snapshot=lambda: {"borrowedUsd": 2.0, "utilization": 0.1, "inventory": {}}
        )
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(
                auto_reinvest_enabled=True,
                reinvest_rate_pct=20,
                base_borrow_amount_wei=int(2e18),
                max_borrow_amount_wei=int(8e18),
                kelly_enabled=True,
            ),
            state=SimpleNamespace(
                realized_profit_wei=int(6e18),
                last_amount_in_wei=int(3e18),
                success_streak=4,
                fail_streak=0,
            ),
            success_rate_pct=lambda: 75.0,
        )
        self._treasury = SimpleNamespace(
            snapshot=lambda: {"ok": True, "enabled": True, "allocator": "treasury-runtime"},
            cfg=SimpleNamespace(
                meta={"estimated_capital_wei": int(20e18), "utilization_rate": 0.25}
            ),
        )
        self._last_operator_pnl_summary = {"total_realized_profit_after_gas_usd": 11.0}
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 88.0, "success_rate_pct": 72.0}
        )
        self._launch_rollout = _LaunchRollout()
        auxiliary = AuxiliaryStateService()
        self._launch_service = LaunchService(auxiliary_state=auxiliary)
        self._analytics_service = AnalyticsService(auxiliary_state=auxiliary)
        self._command_center_service = CommandCenterService(
            operator_summary=OperatorSummaryService(auxiliary_state=auxiliary)
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
                "family_targets": {"flashloan_atomic": 0.5, "funding_arb": 0.2},
                "family_allocations_wei": {
                    "flashloan_atomic": 6_000_000_000_000_000_000,
                    "funding_arb": 2_000_000_000_000_000_000,
                },
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": 5_000_000_000_000_000_000},
            "reinvestment_policy": {"enabled": True},
        }

    def endpoint_quality_state(self):
        return {"lanes": {"PRIVATE": {"quality": 0.9}}, "summary": {}, "generatedAtMs": 0}

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
        return self._execution_service.build_live_state(self)

    def treasury_state(self):
        return AuxiliaryStateService().treasury_state(self)

    def capital_summary(self):
        return AuxiliaryStateService().capital_summary(self)

    def capital_contract(self):
        return AuxiliaryStateService().capital_contract(self)

    async def snapshot(self):
        return {
            "ok": True,
            "capitalSummary": self.capital_summary(),
            "capitalContract": self.capital_contract(),
        }

    def capital_explain(self, snapshot=None):
        return {"ok": True, "text": "ok", "facts": dict(snapshot or {}), "causal": {}}

    def fund_summary_state(self):
        return {"health": {"fundStage": "internal_capital", "privateRoutingReady": True}}

    def strategy_scorecards_state(self):
        return {"families": []}

    def engine_state(self):
        return {"summary": {"engines": []}}

    def execution_calibration_state(self):
        return {"items": []}

    def service_health_state(self):
        return {"execution": {"ok": True}}

    async def stress_evaluate(self, *, scenario: str = "standard"):
        return {"ok": True, "scenario": scenario}


def test_command_center_snapshot_and_explain_expose_canonical_capital_contract():
    runtime = _DashboardRuntime()

    snap = asyncio.run(runtime._command_center_service.snapshot(runtime))
    explain = asyncio.run(runtime._command_center_service.explain(runtime))

    assert snap["capitalSummary"]["navUsd"] == 12.5
    assert snap["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert snap["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert snap["capital"]["navUsd"] == snap["capitalSummary"]["navUsd"]
    assert snap["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
    assert snap["summaryContract"]["truthFamily"] == "command_center"
    assert explain["facts"]["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert explain["facts"]["capitalSummary"]["navSource"] == "ledger_usd_balance"


def test_command_center_and_launch_routes_expose_canonical_capital_contract(monkeypatch):
    runtime = _DashboardRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    command_snapshot = client.get("/api/commandcenter/snapshot")
    launch_state = client.get("/api/launch/state")
    system_summary = client.get("/api/system/summary")

    assert command_snapshot.status_code == 200
    assert launch_state.status_code == 200
    assert system_summary.status_code == 200

    command_body = command_snapshot.json()
    launch_body = launch_state.json()
    system_body = system_summary.json()

    assert command_body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert command_body["summaryContract"]["truthFamily"] == "command_center"
    assert launch_body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert system_body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert system_body["summaryContract"]["truthFamily"] == "system"
    assert "capitalTruthHealth" in command_body
    assert "capitalTruthHealth" in launch_body
    assert "capitalTruthHealth" in system_body

    assert command_body["capitalSummary"]["navUsd"] == 12.5
    assert launch_body["capitalSummary"]["navUsd"] == 12.5
    assert system_body["capitalSummary"]["navUsd"] == 12.5

    assert command_body["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert launch_body["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert system_body["capitalContract"]["navSource"] == "ledger_usd_balance"
    assert launch_body["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"
    assert launch_body["capital"]["stateContract"]["phase"] == "capital_operator_projection"
    assert system_body["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"
    assert system_body["capital"]["stateContract"]["phase"] == "capital_operator_projection"
    assert system_body["serviceContracts"]["execution"]["phase"] == "execution"
    assert system_body["stateContract"]["phase"] == "system_summary"


def test_system_summary_fallback_exposes_capital_contract(monkeypatch):
    runtime = _DashboardRuntime()
    runtime._analytics_service = None
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    response = client.get("/api/system/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["error"] == "analytics_service_unavailable"
    assert body["capitalContract"]["contractVersion"] == "canonical_capital_summary_v1"
    assert body["summaryContract"]["truthFamily"] == "system"
    assert body["capitalSummary"]["navUsd"] == 12.5
    assert body["serviceContracts"]["execution"]["phase"] == "execution"
    assert body["stateContract"]["phase"] == "system_summary"
