from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService


class _OperatorRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                base_borrow_amount="0",
                gas_mode="fast",
                send_mode="private",
                v1_focus="flashloan_atomic",
            ),
            chain=SimpleNamespace(v3_pairs=[{"amount_in": "150"}], curve_pools=[], balancer_pools=[]),
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
        )
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
            audit=SimpleNamespace(
                tail=lambda limit=250: [
                    {
                        "kind": "trade_lifecycle",
                        "hash": "0xabc",
                        "ts_ms": 123,
                        "payload": {
                            "ok": True,
                            "strategy_family": "flashloan_atomic",
                            "route_family": "flashloan_atomic|uni",
                            "route_id": "route-1",
                        },
                    }
                ]
            ),
        )
        self._execution_service = SimpleNamespace(
            build_live_state=lambda runtime: {
                "items": [
                    {
                        "endpoint": "rpc-fast",
                        "lane": "PRIVATE",
                        "flashloan": {"selectedProvider": "aave"},
                    }
                ]
            }
        )
        self._receipt_service = SimpleNamespace(
            summarize=lambda runtime: {
                "ok": True,
                "lastTxHash": "0xsettled",
                "lastRouteFamily": "flashloan_atomic|uni",
                "lastFamily": "flash_arb",
                "lastRuntimeFamily": "flashloan_atomic",
                "lastCapitalFamily": "flashloan_atomic",
                "lastDisplayFamily": "Flash Arbitrage",
                "lastFamilyAliases": ["flash_arb", "flashloan_atomic"],
                "lastFamilyIdentity": {
                    "requestedFamily": "flashloan_atomic",
                    "launchFamily": "flash_arb",
                    "runtimeFamily": "flashloan_atomic",
                    "capitalFamily": "flashloan_atomic",
                    "displayName": "Flash Arbitrage",
                    "aliases": ["flash_arb", "flashloan_atomic"],
                    "isCore": True,
                },
                "lastProvider": "aave",
                "lastFlashloanFeeWei": 4500,
                "lastBorrowCostUsd": 1.25,
                "lastBorrowing": {"source": "flashloan", "provider": "aave", "flashloanFeeWei": 4500, "borrowCostUsd": 1.25},
                "lastLoanSettlement": {"ok": True},
                "lastTerminalProfitabilityAuthority": {"stage": "realized_settlement", "authoritative": True},
                "lastCapitalAdmission": {"ok": True},
                "lastLearningSync": {"executed": True, "ok": True, "reasonCode": "ok"},
                "lastMemorySync": {"executed": True, "ok": True, "reasonCode": "ok"},
                "lastClosedLoop": {"settlementAccounting": True, "learningRecorded": True, "memoryRecorded": True, "completed": True, "reasonCodes": [], "nextAction": "none"},
                "stateContract": {"phase": "settlement", "reason_code": "settled_success"},
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
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {"fundStage": "staging", "riskPosture": "balanced", "riskScore": 0.22},
            }
        )
        self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {"ok": True, "services": {}})
        self._capital_explanation_service = SimpleNamespace(
            explain=lambda runtime, snapshot=None: {"ok": True, "text": "ok", "facts": {}, "causal": {}}
        )
        self._endpoint_universe = SimpleNamespace(snapshot=lambda: {"private": {"candidates": [{"url": "rpc-fast"}]}})
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": [{"quality": 0.9}]})
        self._drawdown_state = SimpleNamespace(snapshot=lambda: {"drawdownPct": 1.0, "hardStop": {"active": False}})
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(snapshot=lambda: {"configured": True, "read": ["rpc-fast"]})
        self._profit_ledger = SimpleNamespace(snapshot=lambda: {"items": []})
        self._execution_router = SimpleNamespace(snapshot=lambda: {"lanes": {}})
        self._trade_journal = SimpleNamespace(snapshot=lambda: {"items": []})
        self._reward_trace = SimpleNamespace(snapshot=lambda: {"items": []})
        self._brain = SimpleNamespace(snapshot=lambda: {"state": "steady"})
        self._chaos_breakers = SimpleNamespace(snapshot=lambda: {"active": []})
        self._capital_service = SimpleNamespace(summary=lambda runtime: {"ok": True, "navUsd": 10.0, "allocations": [], "flows": {}, "exposure": {}})
        self._auxiliary_state_service = None

    def family_hardening_state(self):
        return {"ok": True, "items": []}

    def route_quality_state(self):
        return {"items": []}

    def endpoint_quality_state(self):
        return {"lanes": {}, "summary": {}, "generatedAtMs": 0}

    def execution_live_state(self):
        return self._execution_service.build_live_state(self)



def test_execution_live_state_exposes_canonical_family_identity_for_pending_runtime_aliases():
    runtime = SimpleNamespace(
        _pending={
            "0xflash": {
                "route_family": "flashloan_atomic|uni",
                "strategy_family": "flashloan_atomic",
                "capture_meta": {"metadata": {}},
                "created_at_ms": 123,
            }
        }
    )

    live = ExecutionService().build_live_state(runtime)
    item = live["items"][0]

    assert item["family"] == "flash_arb"
    assert item["requestedFamily"] == "flashloan_atomic"
    assert item["runtimeFamily"] == "flashloan_atomic"
    assert item["capitalFamily"] == "flashloan_atomic"
    assert item["displayFamily"] == "Flash Arbitrage"
    assert "flashloan_atomic" in item["familyAliases"]



def test_operator_summary_decision_feed_and_v1_focus_use_canonical_family_identity():
    runtime = _OperatorRuntime()
    summary = asyncio.run(OperatorSummaryService().build_snapshot(runtime))

    assert summary["aiIntent"]["strategies"] == ["flash_arb"]
    assert summary["aiIntent"]["strategyRuntimeFamilies"] == ["flashloan_atomic"]
    assert summary["governance"]["v1Focus"] == "flash_arb"
    assert summary["governance"]["v1FocusRuntimeFamily"] == "flashloan_atomic"
    assert "flashloan_atomic" in summary["governance"]["v1FocusAliases"]
    assert summary["decisions"][0]["strategies"] == ["flash_arb"]
    assert summary["decisions"][0]["strategyRuntimeFamilies"] == ["flashloan_atomic"]
    assert summary["decisions"][0]["strategyIdentities"][0]["launchFamily"] == "flash_arb"
    assert summary["receiptSummary"]["lastFamily"] == "flash_arb"
    assert summary["receiptSummary"]["lastClosedLoop"]["completed"] is True
    assert summary["flashloanArbLifecycle"]["family"] == "flash_arb"
    assert summary["flashloanArbLifecycle"]["runtimeFamily"] == "flashloan_atomic"
    assert summary["flashloanArbLifecycle"]["provider"] == "aave"
    assert summary["flashloanArbLifecycle"]["autoTradingReady"] is True
    assert summary["flashloanArbLifecycle"]["endToEndConfirmed"] is True
    assert summary["flashloanArbLifecycle"]["closedLoop"]["completed"] is True
