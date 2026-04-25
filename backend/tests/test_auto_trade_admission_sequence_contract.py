from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.models import Metrics
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService
from victor_ai_bot.runtime_services.state_service import StateService


class _SequenceTrackingExecutionService(ExecutionService):
    def __init__(self, blocked_stage: str | None = None):
        self.blocked_stage = blocked_stage
        self.calls: list[str] = []

    def _gate(self, stage: str) -> ExecutionGateResult:
        blocked = self.blocked_stage == stage
        reason = f"{stage}_blocked" if blocked else "ok"
        return ExecutionGateResult(
            not blocked,
            reason,
            {
                "blocked": blocked,
                "reason_code": reason,
                "reason_codes": ([] if not blocked else [reason]),
                "suggested_next_action": ("" if not blocked else f"repair_{stage}"),
                "stage": stage,
            },
        )

    def auto_trade_hold_gate(self, runtime):
        del runtime
        self.calls.append("hold")
        return self._gate("hold")

    def auto_trade_family_gate(self, runtime, opp):
        del runtime, opp
        self.calls.append("family")
        return self._gate("family")

    def auto_trade_execution_realism_gate(self, opp, decision, runtime=None):
        del decision, runtime
        self.calls.append("route")
        prepared = SimpleNamespace(**opp.__dict__)
        prepared.meta = dict(getattr(opp, "meta", {}) or {})
        prepared.meta["prepared_by_route"] = True
        return prepared, self._gate("route")

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        del runtime, opp, decision
        self.calls.append("flashloan")
        return self._gate("flashloan")

    def auto_trade_treasury_gate(self, runtime):
        del runtime
        self.calls.append("treasury")
        return self._gate("treasury")


@pytest.mark.parametrize(
    (
        "blocked_stage",
        "expected_stage",
        "expected_reason",
        "expected_calls",
        "expected_plan_keys",
        "prepared",
    ),
    [
        ("hold", "fund_hold", "hold_blocked", ["hold"], ["hold"], False),
        ("family", "family_hold", "family_blocked", ["hold", "family"], ["hold", "family"], False),
        (
            "route",
            "route_hold",
            "route_blocked",
            ["hold", "family", "route"],
            ["hold", "family", "route"],
            True,
        ),
        (
            "flashloan",
            "flashloan_hold",
            "flashloan_blocked",
            ["hold", "family", "route", "flashloan"],
            ["hold", "family", "route", "flashloan"],
            True,
        ),
        (
            "treasury",
            "treasury_hold",
            "treasury_blocked",
            ["hold", "family", "route", "flashloan", "treasury"],
            ["hold", "family", "route", "flashloan", "treasury"],
            True,
        ),
    ],
)
def test_auto_trade_admission_gate_short_circuits_in_canonical_stage_order(
    blocked_stage,
    expected_stage,
    expected_reason,
    expected_calls,
    expected_plan_keys,
    prepared,
):
    svc = _SequenceTrackingExecutionService(blocked_stage)
    opp = SimpleNamespace(id="opp-seq", meta={"strategy_family": "flashloan_atomic"})

    admission = svc.auto_trade_admission_gate(SimpleNamespace(), opp, None)

    assert admission.allowed is False
    assert admission.stage == expected_stage
    assert admission.reason == expected_reason
    assert svc.calls == expected_calls
    assert list(admission.plan.keys()) == expected_plan_keys
    assert admission.gate["reason_code"] == expected_reason
    assert admission.gate["stage"] == blocked_stage
    assert bool(admission.opportunity.meta.get("prepared_by_route", False)) is prepared


class _CanonicalHoldRuntime:
    def fund_summary_state(self):
        return {
            "ok": True,
            "health": {
                "holdReasonCode": "capital_truth_degraded",
                "holdReasonCodes": ["capital_truth_degraded"],
                "suggestedNextAction": "restore_capital_truth",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_degraded",
                "recoveryReasonCodes": ["capital_truth_degraded"],
                "recoveryNextAction": "restore_capital_truth",
            },
        }


def test_auto_trade_admission_gate_normalizes_hold_metadata_contract():
    admission = ExecutionService().auto_trade_admission_gate(
        _CanonicalHoldRuntime(),
        SimpleNamespace(id="opp-hold", meta={"strategy_family": "flashloan_atomic"}),
        None,
    )

    assert admission.allowed is False
    assert admission.stage == "fund_hold"
    assert admission.reason == "capital_truth_degraded"
    assert admission.gate["reason_code"] == "capital_truth_degraded"
    assert admission.gate["reason_codes"] == ["capital_truth_degraded"]
    assert admission.gate["suggested_next_action"] == "restore_capital_truth"
    assert admission.plan["hold"]["suggested_next_action"] == "restore_capital_truth"


def test_auto_trade_admission_gate_returns_prepared_opportunity_and_full_plan_when_all_stages_pass():
    svc = _SequenceTrackingExecutionService(blocked_stage=None)
    opp = SimpleNamespace(id="opp-ok", meta={"strategy_family": "flashloan_atomic"})

    admission = svc.auto_trade_admission_gate(SimpleNamespace(), opp, None)

    assert admission.allowed is True
    assert admission.stage == "ok"
    assert admission.reason == "ok"
    assert svc.calls == ["hold", "family", "route", "flashloan", "treasury"]
    assert list(admission.plan.keys()) == ["hold", "family", "route", "flashloan", "treasury"]
    assert admission.opportunity is not opp
    assert admission.opportunity.meta["prepared_by_route"] is True


class _SummaryRouteBeforeTreasuryExecutionService(ExecutionService):
    def prepare_execution_opportunity(self, opp, decision):
        del decision
        prepared = SimpleNamespace(**opp.__dict__)
        prepared.meta = dict(getattr(opp, "meta", {}) or {})
        prepared.meta["prepared_by_route"] = True
        return prepared, {
            "applied": False,
            "reason": "route_plan_not_executable",
            "selectedVenues": [],
            "routeInvalidCauses": [],
            "providerPriority": [],
            "flashloanSizing": {},
        }


class _SummarySequenceRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(
                redact_routes_when_private=False,
                send_mode="private",
                gas_mode="fast",
                brain_mode="off",
                dry_run=True,
                withdraw_mode="txdata",
                executor_address="0x0",
                enforce_executor_version=False,
                expected_executor_abi_version=0,
            ),
        )
        self._opps = [
            SimpleNamespace(
                id="opp-summary",
                strategy="flash_arb",
                expected_profit_raw="1000",
                can_execute=True,
                route_id="route-summary",
                meta={
                    "strategy_family": "flashloan_atomic",
                    "profit_after_costs": "250",
                    "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
                },
            )
        ]
        self.metrics = Metrics(send_mode="private")
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
        self._errors = []
        self._auto_trading = True
        self._executor_abi_version = None
        self._executor_impl_version = None
        self._executor_version_error = None
        self._drawdown_state = SimpleNamespace(
            snapshot=lambda: {"drawdownPct": 0.0, "hardStop": {"active": False, "reason_codes": []}}
        )
        self._kill_switch = SimpleNamespace(
            snapshot=lambda: {"metrics": {}, "suppressions": {}, "history": []}
        )
        self._family_hardening_service = SimpleNamespace(
            family_state=lambda runtime, family: {
                "enabled": True,
                "controls": {
                    "admission_ready": True,
                    "execution_eligible": True,
                    "capital_eligible": True,
                    "treasury_eligible": True,
                    "governance_eligible": True,
                    "recovery_ready": True,
                },
                "explanation": {"status": "active", "recovery_ready": True},
                "readiness": {"ready": True, "actualExecutionReady": True},
            }
        )
        self._treasury = SimpleNamespace(
            cfg=SimpleNamespace(
                enabled=True, allow_maximum=False, max_aggressiveness_without_approval="HIGH"
            ),
            snapshot=lambda: {
                "aggressiveness": {
                    "aggressiveness_level": "MAXIMUM",
                    "aggressiveness_multiplier": 1.4,
                },
                "goal": {"target_return_percentage": 12.0, "max_drawdown_pct": 4.0},
            },
            governance_check=lambda *, aggressiveness_level, approved_by_human=False: {
                "ok": False,
                "reason": "maximum_disabled",
            },
        )
        self._execution_service = _SummaryRouteBeforeTreasuryExecutionService()

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


def test_state_service_summary_uses_earliest_canonical_auto_trade_blocker_when_later_treasury_gate_would_also_fail():
    payload = asyncio.run(StateService().summary(_SummarySequenceRuntime()))

    assert payload["auto_trade_gate"]["allowed"] is False
    assert payload["auto_trade_gate"]["stage"] == "route_hold"
    assert payload["auto_trade_gate"]["reason_code"] == "route_plan_not_executable"
    assert payload["auto_trade_gate"]["next_action"] == "refresh_execution_route_plan"
    assert payload["top_opportunity"]["auto_trade_gate_stage"] == "route_hold"
    assert payload["top_opportunity"]["auto_trade_gate_reason_code"] == "route_plan_not_executable"
    assert (
        payload["top_opportunity"]["auto_trade_recovery_status"]
        == "execution_route_restore_required"
    )
    assert payload["top_opportunity"]["auto_trade_recovery_ready"] is False
