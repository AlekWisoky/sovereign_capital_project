from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                auto_trading=True,
                base_borrow_amount="0",
                gas_mode="fast",
                send_mode="private",
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
        self._analytics_service = SimpleNamespace(
            system_summary=lambda runtime: {"ok": True, "services": {}}
        )
        self._capital_explanation_service = SimpleNamespace(
            explain=lambda runtime, snapshot=None: {
                "ok": True,
                "text": "ok",
                "facts": {},
                "causal": {},
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
        self._pending = {}
        self._auto_trading = True
        self._last_settlement_sync = {
            "ok": True,
            "receiptId": "0xabc",
            "status": "settled",
            "transactionId": "tx123",
            "terminalProfitabilityAuthority": {
                "stage": "execution_preflight_gate",
                "reason": "profit_positive",
                "authoritative": True,
                "live_gas_derived": True,
                "profitability": {"profit_after_costs_wei": "12500000"},
            },
            "terminalProfitability": {"profit_after_costs_wei": "12500000"},
            "capitalAdmission": {"ok": True, "reason": "approved", "details": {}},
            "profitabilityChain": {
                "terminalProfitabilityAuthority": {
                    "stage": "execution_preflight_gate",
                    "reason": "profit_positive",
                    "authoritative": True,
                    "live_gas_derived": True,
                    "profitability": {"profit_after_costs_wei": "12500000"},
                },
                "terminalProfitability": {"profit_after_costs_wei": "12500000"},
                "capitalAdmission": {"ok": True, "reason": "approved", "details": {}},
                "expectedAfterCostsWei": "13000000",
                "realizedAfterGasWei": "12500000",
            },
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

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": int(10e18),
                "reserve_bankroll_wei": int(5e18),
                "experimental_bankroll_wei": int(1e18),
                "drawdown_buffer_wei": int(1e18),
                "treasury_offramp_wei": int(1e18),
                "family_targets": {"flashloan_atomic": 0.7, "funding_arb": 0.3},
                "family_allocations_wei": {
                    "flashloan_atomic": int(7e18),
                    "funding_arb": int(3e18),
                },
            },
            "reinvestment_policy": {"autoReinvest": True},
            "capital_efficiency_metrics": {"deployedCapitalWei": int(4e18)},
        }

    def strategy_scorecards_state(self):
        return {
            "families": [
                {
                    "family": "flashloan_atomic",
                    "gasEfficiency": 11.5,
                    "stability": 0.82,
                    "competitionPressure": 0.14,
                },
                {
                    "family": "funding_arb",
                    "gasEfficiency": 6.2,
                    "stability": 0.63,
                    "competitionPressure": 0.22,
                },
            ]
        }

    def wealth_goal_state(self):
        return {
            "ok": True,
            "state": {
                "targetReturnPct": 8.0,
                "timeframeDays": 14,
                "riskTolerance": "moderate",
                "progressPct": 55.0,
                "goalAchieved": False,
                "nextGoalAllowed": True,
                "pacing": "steady",
                "aggressivenessCap": 0.9,
                "goalStatus": "active",
                "goalUrgency": "steady",
            },
            "explanation": {"why_posture": "steady"},
        }


def test_auxiliary_capital_summary_canonicalizes_treasury_bankroll_and_ledger():
    runtime = _Runtime()
    svc = AuxiliaryStateService()

    summary = svc.capital_summary(runtime)
    assert summary["navUsd"] == 12.5
    assert summary["navSource"] == "ledger_usd_balance"
    assert int(summary["bankroll"]["realizedProfitWei"]) == int(6e18)
    assert int(summary["treasury"]["meta"]["estimated_capital_wei"]) == int(20e18)
    assert summary["allocations"][0]["id"] == "flashloan_atomic"
    assert summary["capitalFlows"][0]["amountUsd"] == 12.5
    assert summary["terminalProfitabilityAuthority"]["stage"] == "execution_preflight_gate"
    assert summary["profitabilityChain"]["realizedAfterGasWei"] == "12500000"
    contract = svc.capital_contract(runtime)
    assert contract["terminalProfitabilityAuthority"]["live_gas_derived"] is True
    treasury_state = svc.treasury_state(runtime)
    assert treasury_state["capitalSummary"]["navUsd"] == 12.5
    assert treasury_state["ledger"]["lastSettlement"]["receiptId"] == "0xabc"
    assert treasury_state["terminalProfitabilityAuthority"]["stage"] == "execution_preflight_gate"


def test_operator_summary_uses_canonical_capital_summary_for_nav_and_flows():
    runtime = _Runtime()
    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    assert out["ok"] is True
    assert out["portfolio"]["navUsd"] == 12.5
    assert out["exposure"]["atRiskPct"] == 10.0
    assert out["allocations"][0]["id"] == "flashloan_atomic"
    assert out["capitalFlows"][0]["execSummary"] == "route-1"
    assert out["capital"]["navSource"] == "ledger_usd_balance"
    assert out["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
    assert out["summaryContract"]["truthFamily"] == "operator"
    assert out["summaryContract"]["readModel"] == "operator_summary_projection_v1"
