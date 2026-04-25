from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.models import Metrics
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.state_service import StateService


class _BlockedAutoTradeRecoveryRepo:
    def load(self, component: str):
        assert component == "auto_trade_admission"
        return {
            "is_degraded": True,
            "degraded_since_ts_ms": 1_700_000_000_000,
            "degraded_count": 2,
            "last_healthy_ts_ms": 1_699_999_900_000,
            "history_component": "treasury_governance",
            "history_stage": "treasury_hold",
            "history_reason_code": "maximum_disabled",
            "history_reason_codes": ["maximum_disabled"],
            "history_next_action": "enable_maximum_or_reduce_aggressiveness",
            "component_reliability_class": "blocked",
            "component_reliability_reason_code": "maximum_disabled",
            "component_reliability_reason_codes": ["maximum_disabled"],
            "component_reliability_next_action": "enable_maximum_or_reduce_aggressiveness",
        }

    def recent_events(self, component: str, limit: int = 10):
        assert component == "auto_trade_admission"
        assert limit == 10
        return []


class _RecoveryFallbackRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                redact_routes_when_private=False,
                send_mode="private",
                gas_mode="fast",
                brain_mode="off",
                dry_run=True,
                withdraw_mode="txdata",
                executor_address="",
                enforce_executor_version=False,
                expected_executor_abi_version=0,
                base_borrow_amount="0",
            ),
            chain=SimpleNamespace(
                name="ethereum",
                v3_pairs=[],
                curve_pools=[],
                balancer_pools=[],
            ),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = Metrics(send_mode="private", gas_mode="fast")
        self.rpc_manager = SimpleNamespace(
            snapshot=lambda: {
                "error_rate": 0.0,
                "read": [{"ok": True}],
                "send": [{"ok": True}],
            }
        )
        self._eff = SimpleNamespace(
            snapshot=lambda: {"efficiency_pct": 0.0, "success_rate_pct": 0.0}
        )
        self._bankroll = SimpleNamespace(
            cfg=SimpleNamespace(base_borrow_amount_wei=0, max_borrow_amount_wei=0),
            state=SimpleNamespace(
                realized_profit_wei=0,
                last_amount_in_wei=0,
                success_streak=0,
                fail_streak=0,
            ),
            success_rate_pct=lambda: 0.0,
        )
        self._errors = []
        self._auto_trading = True
        self._executor_abi_version = None
        self._executor_impl_version = None
        self._executor_version_error = None
        self._auto_trade_recovery_repo = _BlockedAutoTradeRecoveryRepo()
        self._opps = [
            SimpleNamespace(
                id="opp-after-cost",
                strategy="flash_arb",
                expected_profit_raw="1000",
                can_execute=True,
                route_id="route-after-cost",
                meta={
                    "strategy_family": "flashloan_atomic",
                    "profit_after_costs": "250",
                    "safety": {
                        "exec_ready": True,
                        "profit_after_costs_wei": "250",
                    },
                },
            )
        ]
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
                    "holdReasonCode": "",
                    "holdReasonCodes": [],
                    "recoveryReady": True,
                    "recoveryStatus": "ready",
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
        self._route_quality = SimpleNamespace(snapshot=lambda: {"items": []})
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {"drawdownPct": 0.0, "hardStop": {"active": False, "reason_codes": []}}
        )
        self._kill_switch = SimpleNamespace(
            snapshot=lambda: {"metrics": {}, "suppressions": {}, "history": []}
        )
        self._risk_memory = SimpleNamespace(snapshot=lambda: {"failures": {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {"paths": []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {"items": []})
        self._rpc_preferences = SimpleNamespace(
            snapshot=lambda: {"configured": True, "read": ["rpc-fast"]}
        )
        self._agent_attribution = SimpleNamespace(summary=lambda: {"agents": []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {"items": []})
        self._pending = {}
        self._pnl = SimpleNamespace(summary=self._pnl_summary, state=lambda: {})

    async def _pnl_summary(self, window=50):
        return {"realized_profit_after_gas_usd_micro": "1000000", "recent": []}

    def fund_summary_state(self):
        return {
            "ok": True,
            "health": {
                "holdReasonCode": "",
                "holdReasonCodes": [],
                "recoveryReady": True,
                "recoveryStatus": "ready",
            },
        }

    def family_hardening_state(self):
        return {"ok": True, "items": []}

    async def snapshot(self):
        return {
            "metrics": {"auto_trading": True},
            "chain": "ethereum",
            "rpc": {"error_rate": 0.0, "read": [{"ok": True}], "send": [{"ok": True}]},
            "opportunities": [],
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


def test_state_service_summary_fails_closed_from_persisted_auto_trade_recovery_when_admission_service_is_unavailable():
    runtime = _RecoveryFallbackRuntime()

    out = asyncio.run(StateService().summary(runtime))

    assert out["auto_trade_gate"]["allowed"] is False
    assert out["auto_trade_gate"]["stage"] == "treasury_hold"
    assert out["auto_trade_gate"]["reason_code"] == "maximum_disabled"
    assert out["auto_trade_gate"]["next_action"] == "enable_maximum_or_reduce_aggressiveness"
    assert out["top_opportunity"]["auto_trade_allowed"] is False
    assert out["top_opportunity"]["auto_trade_gate_stage"] == "treasury_hold"
    assert out["top_opportunity"]["auto_trade_gate_reason_code"] == "maximum_disabled"
    assert out["top_opportunity"]["execution_allowed"] is False
    assert out["top_opportunity"]["can_execute_after_costs"] is False
    assert out["top_opportunity"]["auto_trade_recovery_status"] == "treasury_alignment_required"
    assert out["top_opportunity"]["auto_trade_recovery_ready"] is False


def test_operator_summary_fails_closed_from_persisted_auto_trade_recovery_when_admission_service_is_unavailable():
    runtime = _RecoveryFallbackRuntime()

    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))

    assert out["autoTradeGate"]["allowed"] is False
    assert out["autoTradeGate"]["stage"] == "treasury_hold"
    assert out["autoTradeGate"]["reasonCode"] == "maximum_disabled"
    assert out["autoTradeGate"]["suggestedNextAction"] == "enable_maximum_or_reduce_aggressiveness"
    assert out["autoTradeRecovery"]["ready"] is False
    assert out["autoTradeRecovery"]["status"] == "treasury_alignment_required"
    assert out["autoTradeRecovery"]["reasonCode"] == "maximum_disabled"
    assert "Autonomous execution is blocked because maximum disabled." in out["pausedReason"]


class _ExplodingDirectAdmissionService:
    def auto_trade_admission_gate(self, runtime, opportunity, override):
        raise RuntimeError("admission pipeline offline")


class _DirectAdmissionFailureRuntime(_RecoveryFallbackRuntime):
    def __init__(self):
        super().__init__()
        self._auto_trade_recovery_repo = None
        self._execution_service = _ExplodingDirectAdmissionService()


def test_state_service_summary_fails_closed_when_direct_admission_gate_raises():
    runtime = _DirectAdmissionFailureRuntime()

    out = asyncio.run(StateService().summary(runtime))

    assert out["auto_trade_gate"]["allowed"] is False
    assert out["auto_trade_gate"]["stage"] == "admission_hold"
    assert out["auto_trade_gate"]["reason_code"] == "admission_gate_failed"
    assert out["auto_trade_gate"]["next_action"] == "restore_auto_trade_admission_state"
    assert out["auto_trade_recovery"]["status"] == "auto_trade_admission_restore_required"
    assert out["top_opportunity"]["auto_trade_allowed"] is False
    assert out["top_opportunity"]["auto_trade_gate_reason_code"] == "admission_gate_failed"
    assert out["top_opportunity"]["can_execute_after_costs"] is False


def test_operator_summary_fails_closed_when_direct_admission_gate_raises():
    runtime = _DirectAdmissionFailureRuntime()

    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))

    assert out["autoTradeGate"]["allowed"] is False
    assert out["autoTradeGate"]["stage"] == "admission_hold"
    assert out["autoTradeGate"]["reasonCode"] == "admission_gate_failed"
    assert out["autoTradeGate"]["suggestedNextAction"] == "restore_auto_trade_admission_state"
    assert out["autoTradeRecovery"]["status"] == "auto_trade_admission_restore_required"
    assert out["autoTradeRecovery"]["reasonCode"] == "admission_gate_failed"
    assert "Autonomous execution is blocked because admission gate failed." in out["pausedReason"]
