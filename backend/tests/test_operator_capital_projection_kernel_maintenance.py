from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                auto_trading=True,
                base_borrow_amount="0",
                gas_mode="fast",
                send_mode="private",
                v1_focus="flashloan_atomic",
            ),
            chain=SimpleNamespace(
                name="ethereum",
                v3_pairs=[{"amount_in": "150"}],
                curve_pools=[],
                balancer_pools=[],
            ),
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
            audit=SimpleNamespace(tail=lambda limit=250: []),
            state=lambda: {"degraded": False},
        )
        self._execution_service = SimpleNamespace(build_live_state=lambda runtime: {"items": []})
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
                "health": {
                    "fundStage": "staging",
                    "riskPosture": "balanced",
                    "riskScore": 0.22,
                },
            }
        )
        self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {"ok": True, "services": {}})
        self._capital_explanation_service = SimpleNamespace(explain=lambda runtime, snapshot=None: {"ok": True, "text": "ok", "facts": {}, "causal": {}})
        self._endpoint_universe = SimpleNamespace(snapshot=lambda: {"private": {"candidates": [{"url": "rpc-fast"}]}})
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": [{"quality": 0.9}]})
        self._drawdown_state = SimpleNamespace(snapshot=lambda: {"drawdownPct": 1.0, "hardStop": {"active": False}})
        self._kill_switch = SimpleNamespace(snapshot=lambda: {"suppressions": {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(snapshot=lambda: {"configured": True, "read": ["rpc-fast"]})
        self._agent_attribution = SimpleNamespace(summary=lambda: {"agents": []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {"items": []})
        self._pending = {}
        self._auto_trading = True
        self._pnl = SimpleNamespace(summary=self._pnl_summary)

    async def _pnl_summary(self, window=50):
        return {
            "total_realized_profit_after_gas_usd": 9.25,
            "realized_profit_after_gas_usd_micro": "9250000",
            "recent": [],
        }

    async def snapshot(self):
        return {
            "metrics": {"auto_trading": True},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [],
        }

    def wealth_goal_state(self):
        return {"ok": True, "state": {"targetReturnPct": 8.0, "timeframeDays": 14, "riskTolerance": "moderate", "progressPct": 55.0, "goalAchieved": False, "nextGoalAllowed": True, "pacing": "steady", "aggressivenessCap": 0.9, "goalStatus": "active", "goalUrgency": "steady"}, "explanation": {"why_posture": "steady"}}

    def capital_summary(self):
        return {
            "ok": True,
            "navUsd": 12.5,
            "navSource": "ledger_usd_balance",
            "deployableUsd": 10.0,
            "estimatedCapitalUsd": 20.0,
            "deployedCapitalUsd": 4.0,
            "utilizationPct": 25.0,
            "exposure": {"activePct": 20.0, "sandboxPct": 5.0, "idlePct": 65.0, "atRiskPct": 10.0},
            "internalPrime": {"borrowedUsd": 2.0, "utilization": 0.1},
            "ledger": {
                "balances": {"USD": 12.5},
                "transactions": [{"transaction_id": "tx123"}],
                "tail": [{"receipt_id": "0xabc"}],
                "accounting": {"assetAccounts": {"USD": 12.5}},
            },
            "lastSettlement": {"receiptId": "0xabc", "transactionId": "tx123", "status": "settled"},
            "terminalProfitabilityAuthority": {"stage": "realized_settlement", "authoritative": True},
            "capitalAdmission": {"ok": True, "stateContract": {"phase": "capital_admission"}},
            "familyCapitalPlanVersion": "family_capital_plan_v1",
            "familyCapitalPlan": [{"id": "flashloan_atomic", "launchFamily": "flash_arb"}],
            "allocations": [],
            "capitalFlows": [],
        }

    def capital_truth_state(self):
        return {"ok": True, "reason_code": "ok", "freshness_class": "current"}



def test_state_summary_service_reads_capital_surfaces_through_canonical_runtime_methods():
    runtime = _Runtime()
    svc = StateSummaryService()

    summary = svc.capital_summary(runtime)
    truth = svc.capital_truth_state(runtime)

    assert summary["navUsd"] == 12.5
    assert summary["navSource"] == "ledger_usd_balance"
    assert truth["ok"] is True
    assert truth["reason_code"] == "ok"



def test_operator_summary_projects_capital_ledger_truth_from_canonical_kernel():
    runtime = _Runtime()
    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))

    assert out["capital"]["navUsd"] == 12.5
    assert out["capital"]["navSource"] == "ledger_usd_balance"
    assert out["capital"]["ledgerTruth"]["ledgerUsdBalance"] == 12.5
    assert out["capital"]["ledgerTruth"]["settlementRecorded"] is True
    assert out["capital"]["ledgerTruth"]["lastSettlement"]["receiptId"] == "0xabc"
    assert out["capital"]["ledgerTruth"]["capitalAdmission"]["ok"] is True
    assert out["capitalLedgerTruth"]["stateContract"]["phase"] == "capital_ledger_truth"
    assert out["capital"]["stateContract"]["phase"] == "capital_operator_projection"
