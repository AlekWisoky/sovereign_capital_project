from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.api_facades.launch_facade import guard_launch_mutation
from victor_ai_bot.runtime_services.analytics_service import AnalyticsService
from victor_ai_bot.runtime_services.auxiliary_state_service import (
    AuxiliaryStateService,
    CAPITAL_POLICY_VERSION,
)
from victor_ai_bot.runtime_services.command_center_service import CommandCenterService
from victor_ai_bot.runtime_services.launch_service import LaunchService


class _Ledger:
    def __init__(self, *, usd_balance: float, settled: bool = False):
        self._usd_balance = usd_balance
        self._settled = settled

    def tail(self, limit: int = 50):
        del limit
        return []

    def transactions_tail(self, limit: int = 50):
        del limit
        if not self._settled:
            return []
        return [
            {
                "transaction_id": "tx-1",
                "receipt_id": "0xabc",
                "tx_type": "receipt_settlement",
                "metadata": {"net_realized_usd": self._usd_balance},
            }
        ]

    def balances(self):
        return {"USD": self._usd_balance}


class _Rollout:
    def __init__(self):
        self.profile = SimpleNamespace(
            rollout_order=["flash_arb", "funding_arb"],
            family_states={"flash_arb": "live", "funding_arb": "observe_only"},
        )

    def recommendation(self, **kwargs):
        del kwargs
        return {
            "recommended_next_family": "funding_arb",
            "families": [{"family": "funding_arb", "ready": True, "status": "eligible"}],
            "profile": {"mode": "V1_ONLY"},
        }

    def set_mode(self, mode):
        return {"mode": mode}

    def enable_family(self, family, **kwargs):
        del kwargs
        return {"ok": True, "profile": {"active_families": ["flash_arb", family]}}

    def family_detail(self, family, **kwargs):
        del kwargs
        return {"ok": True, "family": family, "item": {"family": family}}


class _Runtime:
    def __init__(self, *, nav_usd: float, deployable_wei: int, paused: bool = True):
        self._aux = AuxiliaryStateService()
        self._ledger = _Ledger(usd_balance=nav_usd, settled=nav_usd > 0.0)
        self._ledger_repo = None
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 0.0})
        self._bankroll = None
        self._last_operator_pnl_summary = {"total_realized_profit_after_gas_usd": nav_usd}
        self._treasury = SimpleNamespace(
            snapshot=lambda: {"ok": True, "enabled": True, "allocator": "treasury-runtime"},
            cfg=SimpleNamespace(
                meta={"estimated_capital_wei": int(12e18), "utilization_rate": 0.1}
            ),
        )
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(
                paused=paused,
                control_mode="view_only" if paused else "assist",
                sandbox_only=False,
                allocations_frozen=False,
                defensive_mode=False,
                reduce_exposure_half=False,
                governance_enabled=True,
                mutation_enabled=True,
                aggression_mode="balanced",
                full_system_enabled=False,
                force_send_mode="",
                force_gas_mode="",
            )
        )
        self._launch_rollout = _Rollout()
        self._launch_service = LaunchService(auxiliary_state=self._aux)
        self._analytics_service = AnalyticsService(auxiliary_state=self._aux)
        self.calls = []
        self._deployable_wei = deployable_wei

    def set_settings(self, **kwargs):
        self.calls.append(kwargs)

    def fund_summary_state(self):
        return {"health": {"fundStage": "internal_capital", "privateRoutingReady": True}}

    def strategy_scorecards_state(self):
        return {"families": []}

    def engine_state(self):
        return {"summary": {"engines": []}}

    def telemetry_summary(self):
        return {"ok": True}

    def execution_calibration_state(self):
        return {"items": []}

    def drawdown_state(self):
        return {"drawdownPct": 1.0, "hardStop": {"active": False}}

    def kill_switch_state(self):
        return {"metrics": {}, "suppressions": {}}

    def endpoint_quality_state(self):
        return {}

    def endpoint_universe_state(self):
        return {}

    def venue_scorecards_state(self):
        return {"items": []}

    def route_quality_state(self):
        return {"items": []}

    def execution_live_state(self):
        return {"items": []}

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": self._deployable_wei,
                "reserve_bankroll_wei": int(2e18),
                "experimental_bankroll_wei": 0,
                "drawdown_buffer_wei": int(1e18),
                "treasury_offramp_wei": 0,
                "family_targets": {"flash_arb": 0.6, "funding_arb": 0.2},
                "family_allocations_wei": {"flash_arb": self._deployable_wei},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": int(1e18)},
            "reinvestment_policy": {"enabled": False},
        }

    def capital_truth(self):
        return self._aux.capital_truth(self)

    def treasury_state(self):
        return self._aux.treasury_state(self, capital_truth=self.capital_truth())

    def capital_summary(self):
        return self.capital_truth().capital_summary

    def capital_contract(self):
        return self.capital_truth().capital_contract

    def capital_policy(self):
        return self.capital_truth().capital_policy


def test_capital_policy_contract_blocks_when_nav_and_deployable_are_missing():
    rt = _Runtime(nav_usd=0.0, deployable_wei=0)

    policy = rt.capital_policy()

    assert policy["contractVersion"] == CAPITAL_POLICY_VERSION
    assert policy["enforced"] is True
    assert policy["launch"]["enableAllowed"] is False
    assert policy["commandCenter"]["autoAllowed"] is False
    assert "capital_nav_unavailable" in policy["launch"]["enableBlockers"]
    assert "deployable_capital_unavailable" in policy["commandCenter"]["autoBlockers"]


def test_command_center_control_uses_capital_policy_for_auto_mode():
    rt = _Runtime(nav_usd=0.0, deployable_wei=0)

    result = CommandCenterService().apply_controls(
        rt, {"patch": {"controlMode": "auto"}, "reason": "resume"}
    )

    assert result.ok is False
    assert result.error == "capital_nav_unavailable"
    assert result.payload["capitalPolicy"]["contractVersion"] == CAPITAL_POLICY_VERSION


def test_launch_gating_uses_same_capital_policy_for_enable_and_mode_widening():
    rt = _Runtime(nav_usd=0.0, deployable_wei=0, paused=False)
    svc = LaunchService(auxiliary_state=rt._aux)

    guard = guard_launch_mutation(runtime=rt, family="funding_arb", action="enable_next")
    enable = svc.enable_next(rt, "funding_arb")
    mode = svc.set_mode(rt, "FULL_MULTI_STRATEGY")

    assert guard.allowed is False
    assert guard.reason_code == "capital_nav_unavailable"
    assert enable["reason_code"] == "capital_nav_unavailable"
    assert enable["capitalPolicy"]["contractVersion"] == CAPITAL_POLICY_VERSION
    assert mode["reason_code"] == "capital_nav_unavailable"


def test_treasury_and_launch_surfaces_advertise_shared_capital_policy_contract():
    rt = _Runtime(nav_usd=12.5, deployable_wei=int(6e18), paused=False)
    treasury_state = rt.treasury_state()
    analytics = rt._analytics_service.system_summary(rt)
    launch = rt._launch_service.summary(rt)

    assert treasury_state["capitalPolicy"]["contractVersion"] == CAPITAL_POLICY_VERSION
    assert analytics["capitalPolicy"]["contractVersion"] == CAPITAL_POLICY_VERSION
    assert launch["capitalPolicy"]["contractVersion"] == CAPITAL_POLICY_VERSION
    assert treasury_state["capitalPolicy"]["navSource"] == "ledger_usd_balance"
    assert analytics["capitalPolicy"]["commandCenter"]["autoAllowed"] is True
    assert launch["capitalPolicy"]["launch"]["enableAllowed"] is True


class _ExplodingLegacyCapitalRuntime(_Runtime):
    def capital_summary(self):  # pragma: no cover - legacy method must not be used
        raise AssertionError("runtime.capital_summary should not be called")

    def capital_contract(self):  # pragma: no cover - legacy method must not be used
        raise AssertionError("runtime.capital_contract should not be called")

    def capital_policy(self):  # pragma: no cover - legacy method must not be used
        raise AssertionError("runtime.capital_policy should not be called")




class _BrokenCapitalRuntime(_Runtime):
    def capital_engine_state(self):
        raise ValueError("capital snapshot unavailable")


def test_capital_policy_fails_closed_when_capital_truth_is_unavailable():
    rt = _BrokenCapitalRuntime(nav_usd=12.5, deployable_wei=int(6e18), paused=False)

    policy = rt._aux.capital_policy(rt)

    assert policy["contractVersion"] == CAPITAL_POLICY_VERSION
    assert policy["ok"] is False
    assert policy["status"] == "degraded"
    assert policy["reason_code"] == "capital_truth_unavailable"
    assert policy["launch"]["enableAllowed"] is False
    assert policy["commandCenter"]["autoAllowed"] is False


def test_launch_and_command_center_fail_closed_when_capital_truth_is_unavailable():
    rt = _BrokenCapitalRuntime(nav_usd=12.5, deployable_wei=int(6e18), paused=False)
    launch = LaunchService(auxiliary_state=rt._aux)

    guard = guard_launch_mutation(runtime=rt, family="funding_arb", action="enable_next")
    summary = launch.summary(rt)
    command = CommandCenterService().apply_controls(
        rt, {"patch": {"controlMode": "auto"}, "reason": "resume"}
    )

    assert guard.allowed is False
    assert guard.reason_code == "capital_nav_unavailable"
    assert summary["capitalPolicy"]["reason_code"] == "capital_truth_unavailable"
    assert summary["capitalPolicy"]["launch"]["enableAllowed"] is False
    assert command.ok is False
    assert command.error == "capital_nav_unavailable"
    assert command.payload["capitalPolicy"]["reason_code"] == "capital_truth_unavailable"

def test_launch_guard_uses_shared_capital_truth_not_legacy_runtime_capital_methods():
    rt = _ExplodingLegacyCapitalRuntime(nav_usd=0.0, deployable_wei=0, paused=False)

    guard = guard_launch_mutation(runtime=rt, family="funding_arb", action="enable_next")

    assert guard.allowed is False
    assert guard.reason_code == "capital_nav_unavailable"
