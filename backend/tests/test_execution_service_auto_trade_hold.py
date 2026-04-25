from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import ExecResult
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.runtime_services.state_service import current_auto_trade_recovery_info
from victor_ai_bot.runtime_services.execution_service import ExecutionService, ExecutionGateResult


class _RuntimeWithFundSummary:
    def __init__(self, summary):
        self._summary = summary

    def fund_summary_state(self):
        return self._summary


class _RuntimeWithoutFundSummary:
    pass


class _FamilyHardeningService:
    def __init__(self, state):
        self._state = state

    def family_state(self, runtime, family):
        out = dict(self._state)
        out.setdefault("family", family)
        return out


class _RuntimeWithFamilyHardening:
    def __init__(self, state):
        self._family_hardening_service = _FamilyHardeningService(state)


class _RuntimeWithoutFamilyHardening:
    pass


class _FalseyInvalidFamilyHardeningService:
    def family_state(self, runtime, family):
        del runtime, family
        return []


class _RuntimeWithFalseyInvalidFamilyHardening:
    def __init__(self):
        self._family_hardening_service = _FalseyInvalidFamilyHardeningService()


class _TreasuryRuntimeStub:
    def __init__(self, *, enabled=True, allow_maximum=False, max_without="HIGH", state=None):
        self.cfg = SimpleNamespace(
            enabled=enabled,
            allow_maximum=allow_maximum,
            max_aggressiveness_without_approval=max_without,
        )
        self._state = dict(state or {})

    def snapshot(self):
        return dict(self._state)

    def governance_check(self, *, aggressiveness_level: str, approved_by_human: bool = False):
        lvl = str(aggressiveness_level or "LOW").upper()
        max_without = str(self.cfg.max_aggressiveness_without_approval or "HIGH").upper()
        order = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "MAXIMUM": 3}
        if lvl == "MAXIMUM" and not bool(self.cfg.allow_maximum) and not bool(approved_by_human):
            return {"ok": False, "reason": "maximum_disabled"}
        if order.get(lvl, 0) > order.get(max_without, 2) and not bool(approved_by_human):
            return {
                "ok": False,
                "reason": (
                    "maximum_requires_approval"
                    if lvl == "MAXIMUM"
                    else "aggressiveness_requires_approval"
                ),
            }
        return {"ok": True, "reason": "ok"}


class _RuntimeWithTreasury:
    def __init__(self, treasury):
        self._treasury = treasury


class _RuntimeWithoutTreasury:
    pass


class _DeniedExecutionService:
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del decision
        gate = self.auto_trade_hold_gate(runtime)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "fund_hold",
            gate.reason,
            opp,
            dict(gate.metadata or {}),
            {"hold": dict(gate.metadata or {})},
        )

    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(
            False,
            "capital_truth_degraded",
            {
                "blocked": True,
                "holdReasonCode": "capital_truth_degraded",
                "holdReasonCodes": ["capital_truth_degraded"],
                "suggestedNextAction": "restore_capital_truth",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_degraded",
                "recoveryReasonCodes": ["capital_truth_degraded"],
                "recoveryNextAction": "restore_capital_truth",
            },
        )


class _DeniedFamilyExecutionService:
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del runtime, decision
        gate = self.auto_trade_family_gate(None, opp)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "family_hold",
            gate.reason,
            opp,
            dict(gate.metadata or {}),
            {"hold": {"blocked": False}, "family": dict(gate.metadata or {})},
        )

    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_family_gate(self, runtime, opp):
        return ExecutionGateResult(
            False,
            "family_not_active",
            {
                "blocked": True,
                "family": "funding_arb",
                "enabled": False,
                "reason_code": "family_not_active",
                "reason_codes": ["family_not_active"],
                "suggested_next_action": "activate_family",
            },
        )


class _DeniedFamilyHardeningExecutionService(ExecutionService):
    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del decision
        gate = self.auto_trade_family_gate(runtime, opp)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "family_hold",
            gate.reason,
            opp,
            dict(gate.metadata or {}),
            {"hold": {"blocked": False}, "family": dict(gate.metadata or {})},
        )


class _DeniedRouteExecutionService(ExecutionService):
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del runtime
        prepared, gate = self.auto_trade_execution_realism_gate(opp, decision)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "route_hold",
            gate.reason,
            prepared,
            dict(gate.metadata or {}),
            {
                "hold": {"blocked": False},
                "family": {"blocked": False},
                "route": dict(gate.metadata or {}),
            },
        )

    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_family_gate(self, runtime, opp):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_execution_realism_gate(self, opp, decision):
        return opp, ExecutionGateResult(
            False,
            "profit_after_costs_unavailable",
            {
                "blocked": True,
                "reason_code": "profit_after_costs_unavailable",
                "reason_codes": ["profit_after_costs_unavailable"],
                "profitAfterCostsVerified": False,
                "profitAfterCostsReason": "profit_after_costs_unavailable",
                "suggestedNextAction": "refresh_after_fee_profitability_truth",
            },
        )


class _DeniedFlashloanExecutionService:
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        gate = self.auto_trade_flashloan_gate(runtime, opp, decision)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "flashloan_hold",
            gate.reason,
            opp,
            dict(gate.metadata or {}),
            {
                "hold": {"blocked": False},
                "family": {"blocked": False},
                "route": {"blocked": False},
                "flashloan": dict(gate.metadata or {}),
            },
        )

    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_family_gate(self, runtime, opp):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_execution_realism_gate(self, opp, decision):
        return opp, ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        return ExecutionGateResult(
            False,
            "flashloan_sizing_unavailable",
            {
                "blocked": True,
                "reason_code": "flashloan_sizing_unavailable",
                "reason_codes": ["flashloan_sizing_unavailable"],
                "suggested_next_action": "refresh_flashloan_eligibility_truth",
            },
        )


class _DeniedTreasuryExecutionService:
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del decision
        gate = self.auto_trade_treasury_gate(runtime)
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            False,
            "treasury_hold",
            gate.reason,
            opp,
            dict(gate.metadata or {}),
            {
                "hold": {"blocked": False},
                "family": {"blocked": False},
                "route": {"blocked": False},
                "flashloan": {"blocked": False},
                "treasury": dict(gate.metadata or {}),
            },
        )

    def auto_trade_hold_gate(self, runtime):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_family_gate(self, runtime, opp):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_execution_realism_gate(self, opp, decision):
        return opp, ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        return ExecutionGateResult(True, "ok", {"blocked": False})

    def auto_trade_treasury_gate(self, runtime):
        return ExecutionGateResult(
            False,
            "maximum_disabled",
            {
                "blocked": True,
                "reason_code": "maximum_disabled",
                "reason_codes": ["maximum_disabled"],
                "suggested_next_action": "lower_treasury_aggressiveness_or_enable_maximum",
            },
        )


class _AutoExecHarness:
    def __init__(self, execution_service=None):
        self._cc = None
        self._execution_service = execution_service or _DeniedExecutionService()
        self.cfg = SimpleNamespace(execution=SimpleNamespace(dry_run=False))
        self.recorded = []

    async def _record_exec(self, res, opp, latency_ms: int, mode: str):
        self.recorded.append((res, opp, latency_ms, mode))


class _PersistentAutoExecHarness(_AutoExecHarness):
    def __init__(self, db_path: str, execution_service=None):
        super().__init__(execution_service=execution_service)
        self._db = PersistenceDB(db_path)
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(dry_run=False),
        )


class _AllowExecutionService(ExecutionService):
    def auto_trade_admission_gate(self, runtime, opp, decision=None):
        del runtime, decision
        from victor_ai_bot.runtime_services.execution_service import AutoTradeAdmissionResult

        return AutoTradeAdmissionResult(
            True,
            "ok",
            "ok",
            opp,
            {"blocked": False, "reason_code": "ok", "reason_codes": []},
            {},
        )


class _RpcManagerStub:
    def best_send(self):
        return None

    def best_private(self):
        return None

    def best_read(self):
        return None


class _ReachableRpcManagerStub(_RpcManagerStub):
    def best_send(self):
        return "http://send"

    def best_read(self):
        return "http://read"


class _PersistentAllowedAutoExecHarness(_PersistentAutoExecHarness):
    def __init__(self, db_path: str, execution_service=None):
        super().__init__(db_path, execution_service=execution_service or _AllowExecutionService())
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
            ),
        )
        self.rpc_manager = _RpcManagerStub()
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")


class _ExplodingAdmissionExecutionService(ExecutionService):
    def auto_trade_hold_gate(self, runtime):
        raise RuntimeError("fund summary offline")


def test_auto_trade_admission_gate_fails_closed_when_subgate_raises_expected_runtime_error():
    admission = _ExplodingAdmissionExecutionService().auto_trade_admission_gate(
        _RuntimeWithoutFundSummary(),
        SimpleNamespace(id="opp-admission-failure", meta={}),
        None,
    )

    assert admission.allowed is False
    assert admission.stage == "admission_hold"
    assert admission.reason == "admission_gate_failed"
    assert admission.gate["reason_code"] == "admission_gate_failed"
    assert admission.gate["suggested_next_action"] == "restore_auto_trade_admission_state"
    assert admission.plan["admission"]["detail"] == "fund summary offline"


def test_handle_auto_trade_admission_returns_blocked_exec_result_for_denied_gate():
    service = _DeniedRouteExecutionService()
    opp = SimpleNamespace(id="opp-route-denied", meta={})

    handled = service.handle_auto_trade_admission(SimpleNamespace(), opp, None, force_dry_run=False)

    assert handled.opportunity is opp
    assert handled.blocked_result is not None
    assert handled.blocked_result.reason == "route_hold:profit_after_costs_unavailable"
    assert handled.blocked_result.plan["route"]["reason_code"] == "profit_after_costs_unavailable"


def test_handle_auto_trade_admission_fails_closed_when_gate_raises_expected_runtime_error():
    service = _ExplodingAdmissionExecutionService()
    opp = SimpleNamespace(id="opp-admission-handled", meta={})

    handled = service.handle_auto_trade_admission(
        _RuntimeWithoutFundSummary(), opp, None, force_dry_run=True
    )

    assert handled.opportunity is opp
    assert handled.blocked_result is not None
    assert handled.blocked_result.reason == "admission_hold:admission_gate_failed"
    assert handled.blocked_result.dry_run is True
    assert handled.blocked_result.plan["admission"]["reason_code"] == "admission_gate_failed"
    assert handled.blocked_result.plan["admission"]["detail"] == "fund summary offline"


class _SuperRuntimeStub:
    def __init__(self, gate):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(dry_run=False, gas_mode="standard", send_mode="public")
        )
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
        self._super = SimpleNamespace(
            cfg=SimpleNamespace(enabled=True),
            pre_execute_trade=lambda **kwargs: dict(gate),
        )


def test_handle_superstructure_pre_execute_returns_blocked_exec_result_for_rejected_negotiation():
    service = ExecutionService()
    runtime = _SuperRuntimeStub({"allow": False, "reason": "safe_mode", "size_mult": 0.0})
    opp = SimpleNamespace(id="opp-super-block", meta={})

    handled = service.handle_superstructure_pre_execute(runtime, opp, None, force_dry_run=True)

    assert handled.opportunity is opp
    assert handled.super_enabled is True
    assert handled.old_gas_mode == "standard"
    assert handled.old_send_mode == "public"
    assert handled.blocked_result is not None
    assert handled.blocked_result.reason == "negotiation_rejected:safe_mode"
    assert handled.blocked_result.dry_run is True


def test_handle_superstructure_pre_execute_scales_opportunity_and_applies_planner_overrides():
    service = ExecutionService()
    runtime = _SuperRuntimeStub(
        {
            "allow": True,
            "reason": "approved",
            "size_mult": 0.5,
            "overrides": {"gas_mode": "fast", "send_mode": "private"},
        }
    )
    opp = SimpleNamespace(
        id="opp-super-allow",
        model_copy=lambda deep=True: SimpleNamespace(
            id="opp-super-allow-copy",
            route=SimpleNamespace(
                legs=[
                    SimpleNamespace(amount_in="100", min_out="90"),
                    SimpleNamespace(amount_in="90", min_out="80"),
                ]
            ),
            meta={
                "out1": "90",
                "profit_after_costs": "70",
                "brain": {},
                "safety": {"profit_after_costs_wei": "70"},
            },
            min_outs=["90", "80"],
        ),
    )

    handled = service.handle_superstructure_pre_execute(runtime, opp, None, force_dry_run=False)

    assert handled.blocked_result is None
    assert handled.super_enabled is True
    assert handled.old_gas_mode == "standard"
    assert handled.old_send_mode == "public"
    assert runtime.cfg.execution.gas_mode == "fast"
    assert runtime.metrics.gas_mode == "fast"
    assert runtime.cfg.execution.send_mode == "private"
    assert runtime.metrics.send_mode == "private"
    assert handled.opportunity.route.legs[0].amount_in == "50"
    assert handled.opportunity.route.legs[0].min_out == "45"


class _GovStub:
    def __init__(self, gate):
        self._gate = dict(gate)
        self.approved = []

    def generate_intent(self, **kwargs):
        return SimpleNamespace(intent_id="intent-1", **kwargs)

    def governance_check(self, **kwargs):
        return dict(self._gate)

    def approve_intent(self, *, intent_id: str, reviewer: str):
        self.approved.append((intent_id, reviewer))


class _GovernanceRuntimeStub:
    def __init__(self, *, gate=None, consensus=True, consensus_allow=True):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                governance=SimpleNamespace(enforce_on_auto=True),
                consensus=SimpleNamespace(enforce_on_auto=True),
                daily_gas_budget_wei="0",
            ),
            safety=SimpleNamespace(slippage_bps=50, require_simulation=False),
        )
        self._cc = None
        self._consensus = object() if consensus else None
        self._gov = _GovStub(gate or {"ok": True, "reason": "ok", "outcome": "approved"})
        self.opp = SimpleNamespace(
            id="opp-gov",
            route_id="route-gov",
            route=SimpleNamespace(legs=[SimpleNamespace(), SimpleNamespace()]),
            meta={"overlay": {"consensus_allow": consensus_allow}},
        )


def test_handle_governance_pre_execute_returns_blocked_exec_result_for_consensus_rejection():
    service = ExecutionService()
    runtime = _GovernanceRuntimeStub(consensus=True, consensus_allow=False)

    handled = service.handle_governance_pre_execute(
        runtime, runtime.opp, 123, None, force_dry_run=True
    )

    assert handled.opportunity is runtime.opp
    assert handled.blocked_result is not None
    assert handled.blocked_result.reason == "consensus_rejected"
    assert handled.blocked_result.dry_run is True


def test_handle_governance_pre_execute_approves_intent_and_records_intent_id():
    service = ExecutionService()
    runtime = _GovernanceRuntimeStub(
        gate={"ok": True, "reason": "ok", "outcome": "approved"}, consensus=False
    )
    decision = SimpleNamespace(gas_mode="fast", size_mult=1.2, borrow_mult=1.0, portfolio=None)

    handled = service.handle_governance_pre_execute(
        runtime, runtime.opp, 456, decision, force_dry_run=False
    )

    assert handled.blocked_result is None
    assert runtime.opp.meta["intent_id"] == "intent-1"
    assert runtime._gov.approved == [("intent-1", "agent")]


class _GovernanceBlockedHarness(_AutoExecHarness):
    def __init__(self):
        super().__init__(execution_service=_AllowExecutionService())
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
                governance=SimpleNamespace(enforce_on_auto=True),
                consensus=SimpleNamespace(enforce_on_auto=False),
            ),
            safety=SimpleNamespace(slippage_bps=50, require_simulation=False),
        )
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
        self.rpc_manager = _ReachableRpcManagerStub()
        self._gov = _GovStub(
            {"ok": False, "reason": "security_stack_failed", "outcome": "rejected"}
        )
        self._cc = None
        self._consensus = None


@pytest.mark.asyncio
async def test_runtime_auto_execute_blocks_on_governance_rejection_via_extracted_handler():
    harness = _GovernanceBlockedHarness()
    opp = SimpleNamespace(
        id="opp-gov-runtime",
        route_id="route-gov-runtime",
        route=SimpleNamespace(legs=[SimpleNamespace(), SimpleNamespace()]),
        meta={"overlay": {}},
    )

    await RuntimeBundle._execute_auto(
        harness,
        opp,
        789,
        SimpleNamespace(gas_mode="standard", size_mult=1.0, borrow_mult=1.0, portfolio=None),
    )

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "governance_rejected:security_stack_failed:rejected"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_fails_closed_when_admission_gate_raises_expected_runtime_error():
    harness = _AutoExecHarness(execution_service=_ExplodingAdmissionExecutionService())
    opp = SimpleNamespace(id="opp-admission-runtime", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "admission_hold:admission_gate_failed"
    assert res.plan["admission"]["reason_code"] == "admission_gate_failed"
    assert res.plan["admission"]["detail"] == "fund summary offline"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.parametrize(
    ("summary", "expected_reason", "expected_next_action"),
    [
        (
            {
                "health": {
                    "capitalTruthReasonCodes": ["capital_truth_degraded"],
                    "holdReasonCode": "capital_truth_degraded",
                    "holdReasonCodes": ["capital_truth_degraded"],
                    "suggestedNextAction": "restore_capital_truth",
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_degraded",
                    "recoveryReasonCodes": ["capital_truth_degraded"],
                    "recoveryNextAction": "restore_capital_truth",
                }
            },
            "capital_truth_degraded",
            "restore_capital_truth",
        ),
        (
            {
                "health": {
                    "globalExecutionBlocked": True,
                    "globalExecutionReasonCodes": ["drawdown_hard_stop"],
                    "holdReasonCode": "drawdown_hard_stop",
                    "holdReasonCodes": ["drawdown_hard_stop"],
                    "suggestedNextAction": "reduce_drawdown_and_clear_hard_stop",
                    "recoveryReady": False,
                    "recoveryStatus": "global_execution_blocked",
                    "recoveryReasonCode": "drawdown_hard_stop",
                    "recoveryReasonCodes": ["drawdown_hard_stop"],
                    "recoveryNextAction": "reduce_drawdown_and_clear_hard_stop",
                }
            },
            "drawdown_hard_stop",
            "reduce_drawdown_and_clear_hard_stop",
        ),
    ],
)
def test_auto_trade_hold_gate_blocks_on_canonical_fund_hold(
    summary, expected_reason, expected_next_action
):
    gate = ExecutionService().auto_trade_hold_gate(_RuntimeWithFundSummary(summary))

    assert gate.allowed is False
    assert gate.reason == expected_reason
    assert gate.metadata["holdReasonCode"] == expected_reason
    assert gate.metadata["suggestedNextAction"] == expected_next_action
    assert gate.metadata["recoveryReady"] is False


def test_auto_trade_hold_gate_preserves_receipt_outcome_truth_as_first_class_recovery_component():
    gate = ExecutionService().auto_trade_hold_gate(
        _RuntimeWithFundSummary(
            {
                "health": {
                    "globalExecutionBlocked": False,
                    "globalExecutionReasonCodes": [],
                    "capitalTruthReasonCodes": ["settled_profit_truth_unavailable"],
                    "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
                    "receiptOutcomeTruthReliabilityClass": "degraded",
                    "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                    "receiptOutcomeTruthReliabilityReasonCodes": [
                        "receipt_outcome_truth_reliability_degraded",
                        "settled_profit_truth_unavailable",
                    ],
                    "internalPrimeReasonCodes": [],
                    "holdReasonCode": "",
                    "holdReasonCodes": [],
                    "recoveryReady": False,
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "settled_profit_truth_unavailable",
                    "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
                    "suggestedNextAction": "restore_receipt_outcome_truth",
                    "recoveryNextAction": "restore_receipt_outcome_truth",
                    "recoveryHistoryComponent": "receipt_outcome_truth",
                    "recoveryHistoryStatus": "degraded",
                    "recoveryReliabilityClass": "degraded",
                    "recoveryReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                    "recoveryReliabilityReasonCodes": [
                        "receipt_outcome_truth_reliability_degraded",
                        "settled_profit_truth_unavailable",
                    ],
                }
            }
        )
    )

    assert gate.allowed is False
    assert gate.reason == "settled_profit_truth_unavailable"
    assert gate.metadata["receiptOutcomeTruthReasonCodes"] == ["settled_profit_truth_unavailable"]
    assert gate.metadata["holdReasonCode"] == "settled_profit_truth_unavailable"
    assert gate.metadata["suggestedNextAction"] == "restore_receipt_outcome_truth"
    assert gate.metadata["recoveryStatus"] == "capital_truth_restore_required"
    assert gate.metadata["recoveryHistoryComponent"] == "receipt_outcome_truth"
    assert gate.metadata["receiptOutcomeTruthReliabilityClass"] == "degraded"
    assert (
        gate.metadata["receiptOutcomeTruthReliabilityReasonCode"]
        == "receipt_outcome_truth_reliability_degraded"
    )
    assert gate.metadata["recoveryReliabilityClass"] == "degraded"
    assert (
        gate.metadata["recoveryReliabilityReasonCode"]
        == "receipt_outcome_truth_reliability_degraded"
    )


def test_auto_trade_hold_gate_allows_execution_when_fund_health_is_ready():
    gate = ExecutionService().auto_trade_hold_gate(
        _RuntimeWithFundSummary(
            {
                "health": {
                    "globalExecutionBlocked": False,
                    "globalExecutionReasonCodes": [],
                    "capitalTruthReasonCodes": [],
                    "internalPrimeReasonCodes": [],
                    "holdReasonCode": "",
                    "holdReasonCodes": [],
                    "recoveryReady": True,
                    "recoveryStatus": "ready",
                    "recoveryReasonCode": "ok",
                    "recoveryReasonCodes": [],
                }
            }
        )
    )

    assert gate.allowed is True
    assert gate.reason == "ok"
    assert gate.metadata["blocked"] is False
    assert gate.metadata["recoveryReady"] is True


def test_auto_trade_hold_gate_fails_closed_when_fund_summary_is_unavailable():
    gate = ExecutionService().auto_trade_hold_gate(_RuntimeWithoutFundSummary())

    assert gate.allowed is False
    assert gate.reason == "fund_summary_unavailable"
    assert gate.metadata["holdReasonCode"] == "fund_summary_unavailable"
    assert gate.metadata["recoveryReady"] is False


def test_auto_trade_hold_gate_blocks_when_family_hardening_service_is_degraded_even_without_hold_reason_copy():
    gate = ExecutionService().auto_trade_hold_gate(
        _RuntimeWithFundSummary(
            {
                "health": {
                    "globalExecutionBlocked": False,
                    "globalExecutionReasonCodes": [],
                    "capitalTruthReasonCodes": [],
                    "internalPrimeReasonCodes": [],
                    "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                    "holdReasonCode": "",
                    "holdReasonCodes": [],
                    "recoveryReady": True,
                    "recoveryStatus": "ready",
                    "recoveryReasonCode": "ok",
                    "recoveryReasonCodes": [],
                }
            }
        )
    )

    assert gate.allowed is False
    assert gate.reason == "family_hardening_service_unavailable"
    assert gate.metadata["familyHardeningReasonCodes"] == ["family_hardening_service_unavailable"]
    assert gate.metadata["holdReasonCode"] == "family_hardening_service_unavailable"
    assert gate.metadata["holdReasonCodes"] == ["family_hardening_service_unavailable"]
    assert gate.metadata["suggestedNextAction"] == "restore_family_hardening"
    assert gate.metadata["recoveryReady"] is False
    assert gate.metadata["recoveryStatus"] == "family_hardening_restore_required"
    assert gate.metadata["recoveryReasonCode"] == "family_hardening_service_unavailable"
    assert gate.metadata["recoveryReasonCodes"] == ["family_hardening_service_unavailable"]
    assert gate.metadata["recoveryNextAction"] == "restore_family_hardening"
    assert gate.metadata["recoveryHistoryComponent"] == "family_hardening"
    assert gate.metadata["recoveryHistoryStatus"] == "degraded"
    assert gate.metadata["familyHardeningRecoveryHistoryStatus"] == "degraded"
    assert gate.metadata["familyHardeningReliabilityClass"] == "unavailable"
    assert (
        gate.metadata["familyHardeningReliabilityReasonCode"]
        == "family_hardening_reliability_unavailable"
    )
    assert gate.metadata["familyHardeningReliabilityReasonCodes"] == [
        "family_hardening_reliability_unavailable"
    ]
    assert gate.metadata["recoveryReliabilityClass"] == "unavailable"
    assert (
        gate.metadata["recoveryReliabilityReasonCode"] == "family_hardening_reliability_unavailable"
    )
    assert gate.metadata["recoveryReliabilityReasonCodes"] == [
        "family_hardening_reliability_unavailable"
    ]


def test_auto_trade_family_gate_blocks_when_family_is_not_active():
    gate = ExecutionService().auto_trade_family_gate(
        _RuntimeWithFamilyHardening(
            {
                "enabled": False,
                "controls": {
                    "admission_ready": False,
                    "execution_eligible": False,
                    "capital_eligible": True,
                    "treasury_eligible": True,
                    "governance_eligible": True,
                    "recovery_ready": True,
                    "no_trade": True,
                    "no_trade_reason_codes": ["family_not_active"],
                    "admission_reason_codes": ["family_not_active"],
                    "execution_reason_codes": ["stage_restriction"],
                },
                "explanation": {
                    "status": "blocked",
                    "reason_code": "family_not_active",
                    "suggested_next_action": "activate_family",
                },
                "readiness": {
                    "ready": False,
                    "actualExecutionReady": False,
                    "status": "blocked",
                    "blockers": ["family_not_active"],
                },
            }
        ),
        SimpleNamespace(meta={"strategy_family": "funding_arb"}),
    )

    assert gate.allowed is False
    assert gate.reason == "family_not_active"
    assert gate.metadata["family"] == "funding_arb"
    assert gate.metadata["enabled"] is False
    assert gate.metadata["suggested_next_action"] == "activate_family"


def test_auto_trade_family_gate_maps_flashloan_atomic_to_flash_arb_and_allows_ready_family():
    gate = ExecutionService().auto_trade_family_gate(
        _RuntimeWithFamilyHardening(
            {
                "enabled": True,
                "controls": {
                    "admission_ready": True,
                    "execution_eligible": True,
                    "capital_eligible": True,
                    "treasury_eligible": True,
                    "governance_eligible": True,
                    "recovery_ready": True,
                    "no_trade": False,
                    "no_trade_reason_codes": [],
                    "admission_reason_codes": [],
                    "execution_reason_codes": [],
                },
                "explanation": {
                    "status": "eligible",
                    "reason_code": "eligible",
                    "suggested_next_action": "continue_v1_learning",
                },
                "readiness": {
                    "ready": True,
                    "actualExecutionReady": True,
                    "status": "eligible",
                    "blockers": [],
                },
            }
        ),
        SimpleNamespace(meta={"strategy_family": "flashloan_atomic"}),
    )

    assert gate.allowed is True
    assert gate.reason == "ok"
    assert gate.metadata["family"] == "flash_arb"
    assert gate.metadata["execution_eligible"] is True


def test_auto_trade_family_gate_fails_closed_when_family_hardening_is_unavailable():
    gate = ExecutionService().auto_trade_family_gate(
        _RuntimeWithoutFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "funding_arb"}),
    )

    assert gate.allowed is False
    assert gate.reason == "family_hardening_unavailable"
    assert gate.metadata["family"] == "funding_arb"
    assert gate.metadata["reason_code"] == "family_hardening_unavailable"
    assert gate.metadata["reason_codes"] == ["family_hardening_unavailable"]
    assert gate.metadata["suggested_next_action"] == "restore_family_hardening"
    assert gate.metadata["recovery_status"] == "family_hardening_restore_required"
    assert gate.metadata["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert gate.metadata["recovery_reason_codes"] == ["family_hardening_service_unavailable"]
    assert gate.metadata["recovery_next_action"] == "restore_family_hardening"
    assert gate.metadata["recovery_history_component"] == "family_hardening"
    assert gate.metadata["recovery_history_status"] == "degraded"
    assert gate.metadata["recovery_reliability_class"] == "unavailable"
    assert gate.metadata["family_hardening_reason_codes"] == [
        "family_hardening_service_unavailable"
    ]
    assert gate.metadata["family_hardening_recovery_history_status"] == "degraded"
    assert gate.metadata["family_hardening_reliability_class"] == "unavailable"


def test_auto_trade_family_gate_fails_closed_when_family_hardening_state_is_falsey_invalid():
    gate = ExecutionService().auto_trade_family_gate(
        _RuntimeWithFalseyInvalidFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "funding_arb"}),
    )

    assert gate.allowed is False
    assert gate.reason == "family_hardening_unavailable"
    assert gate.metadata["family"] == "funding_arb"
    assert gate.metadata["reason_code"] == "family_hardening_unavailable"
    assert gate.metadata["recovery_status"] == "family_hardening_restore_required"
    assert gate.metadata["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert gate.metadata["detail"] == "invalid_family_hardening_state"


def _healthy_execution_opp(*, profit_after_costs: str = "500"):
    return SimpleNamespace(
        id="opp-route",
        expected_profit_raw="1000",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(venue="uni", min_out="100"),
                SimpleNamespace(venue="curve", min_out="100"),
            ]
        ),
        min_outs=["100", "100"],
        meta={
            "profit_after_costs": profit_after_costs,
            "safety": {"profit_after_costs_wei": profit_after_costs},
        },
    )


def _healthy_execution_route_plan(*, degraded: bool = False):
    runtime = {
        "input": {
            "ok": not degraded,
            "code": ("ok" if not degraded else "route_input_invalid"),
            "detail": "",
        },
        "legs": {"ok": True, "code": "ok", "detail": ""},
        "mutation": {"ok": True, "code": "ok", "detail": ""},
        "profit": {"ok": True, "code": "ok", "detail": ""},
        "degraded": bool(degraded),
    }
    return {
        "selected_venues": ["uni", "curve"],
        "split": [
            {"venue": "uni", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
            {"venue": "curve", "share": 0.5, "size_mult": 0.5, "venue_quality": 0.9},
        ],
        "fallback_tree": [],
        "fallback_used": False,
        "executable": True,
        "require_fallback_tree": False,
        "provider_priority": ["aave"],
        "provider_fallback": "",
        "reserve_distortion": 0.0,
        "mutation_factor": 1.0,
        "route_invalid_causes": [],
        "runtime": runtime,
        "leg_plan": [
            {
                "index": 0,
                "venue": "uni",
                "share": 0.5,
                "venue_quality": 0.9,
                "viability": 1.0,
                "selected": True,
                "distortion": 0.0,
                "action": "execute",
                "fallback_venues": [],
            },
            {
                "index": 1,
                "venue": "curve",
                "share": 0.5,
                "venue_quality": 0.9,
                "viability": 1.0,
                "selected": True,
                "distortion": 0.0,
                "action": "execute",
                "fallback_venues": [],
            },
        ],
        "raw_route_plan": {},
    }


def test_auto_trade_execution_realism_gate_blocks_when_execution_route_plan_is_missing():
    opp = _healthy_execution_opp()
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(metadata={}),
    )

    assert prepared is opp
    assert gate.allowed is False
    assert gate.reason == "no_execution_route_plan"
    assert gate.metadata["blocked"] is True
    assert gate.metadata["suggestedNextAction"] == "refresh_execution_capture"


def test_auto_trade_execution_realism_gate_blocks_when_route_runtime_is_degraded():
    opp = _healthy_execution_opp()
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(
            metadata={"execution_route_plan": _healthy_execution_route_plan(degraded=True)}
        ),
    )

    assert prepared is not opp
    assert gate.allowed is False
    assert gate.reason == "route_input_invalid"
    assert gate.metadata["routeRuntimeDegraded"] is True
    assert gate.metadata["routeRuntimeReasonCodes"] == ["route_input_invalid"]


def test_auto_trade_execution_realism_gate_blocks_when_after_fee_profitability_truth_is_missing():
    opp = _healthy_execution_opp()
    opp.meta = {}
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(metadata={"execution_route_plan": _healthy_execution_route_plan()}),
    )

    assert prepared is not opp
    assert gate.allowed is False
    assert gate.reason == "profit_after_costs_unavailable"
    assert gate.metadata["profitAfterCostsVerified"] is False
    assert gate.metadata["suggestedNextAction"] == "refresh_after_fee_profitability_truth"


def test_auto_trade_execution_realism_gate_blocks_when_after_fee_profitability_truth_is_mismatched():
    opp = _healthy_execution_opp()
    opp.meta = {
        "profit_after_costs": "500",
        "safety": {"profit_after_costs_wei": "300"},
    }
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(metadata={"execution_route_plan": _healthy_execution_route_plan()}),
    )

    assert prepared is not opp
    assert gate.allowed is False
    assert gate.reason == "profit_after_costs_mismatch"
    assert gate.metadata["profitAfterCostsVerified"] is False
    assert gate.metadata["profitAfterCostsCanonical"] is False
    assert gate.metadata["profitAfterCostsMetaWei"] == "500"
    assert gate.metadata["profitAfterCostsSafetyWei"] == "300"
    assert gate.metadata["suggestedNextAction"] == "refresh_after_fee_profitability_truth"


def test_auto_trade_execution_realism_gate_allows_when_route_truth_and_after_fee_profitability_are_ready():
    opp = _healthy_execution_opp()
    prepared, gate = ExecutionService().auto_trade_execution_realism_gate(
        opp,
        SimpleNamespace(metadata={"execution_route_plan": _healthy_execution_route_plan()}),
    )

    assert prepared is not opp
    assert gate.allowed is True
    assert gate.reason == "ok"
    assert gate.metadata["profitAfterCostsVerified"] is True
    assert gate.metadata["routeRuntimeDegraded"] is False


def test_auto_trade_flashloan_gate_blocks_when_flashloan_sizing_truth_is_missing():
    gate = ExecutionService().auto_trade_flashloan_gate(
        _RuntimeWithoutFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "flashloan_atomic"}),
        SimpleNamespace(metadata={}),
    )

    assert gate.allowed is False
    assert gate.reason == "flashloan_sizing_unavailable"
    assert gate.metadata["applicable"] is True
    assert gate.metadata["suggested_next_action"] == "refresh_flashloan_eligibility_truth"


def test_auto_trade_flashloan_gate_blocks_when_flashloan_sizing_is_not_allowed():
    gate = ExecutionService().auto_trade_flashloan_gate(
        _RuntimeWithoutFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "flashloan_atomic"}),
        SimpleNamespace(
            metadata={
                "flashloan_resilience": {
                    "selected_provider": "aave",
                    "provider_priority": ["aave"],
                    "sizing": {
                        "allowed": False,
                        "reason_codes": ["family_target_unresolved"],
                        "selected_provider": "aave",
                        "provider_priority": ["aave"],
                    },
                }
            }
        ),
    )

    assert gate.allowed is False
    assert gate.reason == "family_target_unresolved"
    assert gate.metadata["reason_code"] == "family_target_unresolved"


def test_auto_trade_flashloan_gate_allows_when_flashloan_sizing_truth_is_ready():
    gate = ExecutionService().auto_trade_flashloan_gate(
        _RuntimeWithoutFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "flashloan_atomic"}),
        SimpleNamespace(
            metadata={
                "flashloan_resilience": {
                    "selected_provider": "aave",
                    "provider_priority": ["aave", "balancer"],
                    "sizing": {
                        "allowed": True,
                        "selected_provider": "aave",
                        "provider_priority": ["aave", "balancer"],
                        "size_mult": 1.25,
                        "borrow_mult": 1.4,
                        "provider_limit": 4.0,
                        "family_target_known": True,
                        "resolved_family_target_key": "flashloan_atomic",
                    },
                }
            }
        ),
    )

    assert gate.allowed is True
    assert gate.reason == "ok"
    assert gate.metadata["selected_provider"] == "aave"
    assert gate.metadata["family"] == "flash_arb"


def test_auto_trade_flashloan_gate_is_not_applicable_for_non_flash_family_without_sizing():
    gate = ExecutionService().auto_trade_flashloan_gate(
        _RuntimeWithoutFamilyHardening(),
        SimpleNamespace(meta={"strategy_family": "funding_arb"}),
        SimpleNamespace(metadata={}),
    )

    assert gate.allowed is True
    assert gate.metadata["applicable"] is False


def test_auto_trade_treasury_gate_is_not_applicable_when_treasury_is_disabled():
    gate = ExecutionService().auto_trade_treasury_gate(
        _RuntimeWithTreasury(_TreasuryRuntimeStub(enabled=False, state={}))
    )

    assert gate.allowed is True
    assert gate.metadata["applicable"] is False


def test_auto_trade_treasury_gate_blocks_when_maximum_is_disabled():
    gate = ExecutionService().auto_trade_treasury_gate(
        _RuntimeWithTreasury(
            _TreasuryRuntimeStub(
                enabled=True,
                allow_maximum=False,
                max_without="HIGH",
                state={
                    "aggressiveness": {
                        "aggressiveness_level": "MAXIMUM",
                        "aggressiveness_multiplier": 1.4,
                        "current_return_pct": 0.0,
                        "performance_gap": 5.0,
                        "urgency_factor": 1.0,
                        "drawdown_pct": 0.0,
                    },
                    "goal": {
                        "target_return_percentage": 5.0,
                        "max_drawdown_pct": 10.0,
                    },
                },
            )
        )
    )

    assert gate.allowed is False
    assert gate.reason == "maximum_disabled"
    assert gate.metadata["aggressiveness_level"] == "MAXIMUM"
    assert (
        gate.metadata["suggested_next_action"] == "lower_treasury_aggressiveness_or_enable_maximum"
    )


def test_auto_trade_treasury_gate_allows_when_aggressiveness_is_within_auto_trade_limit():
    gate = ExecutionService().auto_trade_treasury_gate(
        _RuntimeWithTreasury(
            _TreasuryRuntimeStub(
                enabled=True,
                allow_maximum=False,
                max_without="HIGH",
                state={
                    "aggressiveness": {
                        "aggressiveness_level": "HIGH",
                        "aggressiveness_multiplier": 1.25,
                        "current_return_pct": 1.0,
                        "performance_gap": 0.5,
                        "urgency_factor": 0.1,
                        "drawdown_pct": 1.0,
                    },
                    "goal": {
                        "target_return_percentage": 5.0,
                        "max_drawdown_pct": 10.0,
                    },
                },
            )
        )
    )

    assert gate.allowed is True
    assert gate.reason == "ok"
    assert gate.metadata["blocked"] is False


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_hold_rejection_before_execution_attempt():
    harness = _AutoExecHarness()
    opp = SimpleNamespace(id="opp-1", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "fund_hold:capital_truth_degraded"
    assert res.plan["hold"]["holdReasonCode"] == "capital_truth_degraded"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_family_rejection_before_execution_attempt():
    harness = _AutoExecHarness(execution_service=_DeniedFamilyExecutionService())
    opp = SimpleNamespace(id="opp-2", meta={"strategy_family": "funding_arb"})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "family_hold:family_not_active"
    assert res.plan["family"]["reason_code"] == "family_not_active"
    assert res.plan["family"]["family"] == "funding_arb"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_route_rejection_before_execution_attempt():
    harness = _AutoExecHarness(execution_service=_DeniedRouteExecutionService())
    opp = SimpleNamespace(id="opp-3", meta={"strategy_family": "flashloan_atomic"})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "route_hold:profit_after_costs_unavailable"
    assert res.plan["route"]["reason_code"] == "profit_after_costs_unavailable"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_treasury_rejection_before_execution_attempt():
    harness = _AutoExecHarness(execution_service=_DeniedTreasuryExecutionService())
    opp = SimpleNamespace(id="opp-5", meta={"strategy_family": "flashloan_atomic"})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "treasury_hold:maximum_disabled"
    assert res.plan["treasury"]["reason_code"] == "maximum_disabled"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_flashloan_rejection_before_execution_attempt():
    harness = _AutoExecHarness(execution_service=_DeniedFlashloanExecutionService())
    opp = SimpleNamespace(id="opp-4", meta={"strategy_family": "flashloan_atomic"})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is False
    assert res.attempted is False
    assert res.reason == "flashloan_hold:flashloan_sizing_unavailable"
    assert res.plan["flashloan"]["reason_code"] == "flashloan_sizing_unavailable"
    assert recorded_opp is opp
    assert latency_ms == 0
    assert mode == "auto"


@pytest.mark.asyncio
async def test_runtime_auto_execute_persists_admission_blocker_history_without_summary_reads(
    tmp_path,
):
    harness = _PersistentAutoExecHarness(str(tmp_path / "runtime.sqlite3"))
    opp = SimpleNamespace(id="opp-persisted-block", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is True
    assert recovery["status"] == "fund_hold_active"
    assert recovery["reason_code"] == "capital_truth_degraded"
    assert recovery["history_status"] == "blocked"
    assert recovery["degraded_count"] == 1
    history = list(recovery.get("recent_events") or [])
    assert len(history) == 1
    assert history[0]["event_type"] == "blocked"
    assert history[0]["stage"] == "fund_hold"
    assert history[0]["reason_code"] == "capital_truth_degraded"

    await RuntimeBundle._execute_auto(harness, opp, 124)

    repeated = current_auto_trade_recovery_info(harness)
    assert repeated["blocked"] is True
    assert repeated["degraded_count"] == 1
    repeated_history = list(repeated.get("recent_events") or [])
    assert len(repeated_history) == 1
    assert repeated_history[0]["event_type"] == "blocked"


@pytest.mark.asyncio
async def test_runtime_auto_execute_preserves_family_hardening_recovery_contract_in_auto_trade_recovery_history(
    tmp_path,
):
    harness = _PersistentAutoExecHarness(
        str(tmp_path / "runtime-family-hardening.sqlite3"),
        execution_service=_DeniedFamilyHardeningExecutionService(),
    )
    opp = SimpleNamespace(id="opp-family-hardening", meta={"strategy_family": "funding_arb"})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is True
    assert recovery["status"] == "family_hardening_restore_required"
    assert recovery["reason_code"] == "family_hardening_service_unavailable"
    assert recovery["reason_codes"] == ["family_hardening_service_unavailable"]
    assert recovery["next_action"] == "restore_family_hardening"
    assert recovery["component"] == "family_hardening"
    assert recovery["history_status"] == "degraded"
    assert recovery["reliability_class"] == "unavailable"
    assert recovery["reliability_reason_code"] == "family_hardening_reliability_unavailable"
    assert recovery["reliability_reason_codes"] == ["family_hardening_reliability_unavailable"]
    assert recovery["family_hardening_reason_codes"] == ["family_hardening_service_unavailable"]
    history = list(recovery.get("recent_events") or [])
    assert len(history) == 1
    assert history[0]["event_type"] == "blocked"
    assert history[0]["stage"] == "family_hold"
    assert history[0]["reason_code"] == "family_hardening_service_unavailable"


class _PersistentReceiptOutcomeTruthAutoExecHarness(_PersistentAutoExecHarness):
    def __init__(self, db_path: str):
        super().__init__(db_path, execution_service=ExecutionService())
        self._summary = {
            "health": {
                "globalExecutionBlocked": False,
                "globalExecutionReasonCodes": [],
                "capitalTruthReasonCodes": ["settled_profit_truth_unavailable"],
                "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
                "receiptOutcomeTruthReliabilityClass": "degraded",
                "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "receiptOutcomeTruthReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                    "settled_profit_truth_unavailable",
                ],
                "internalPrimeReasonCodes": [],
                "holdReasonCode": "settled_profit_truth_unavailable",
                "holdReasonCodes": ["settled_profit_truth_unavailable"],
                "suggestedNextAction": "restore_receipt_outcome_truth",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "settled_profit_truth_unavailable",
                "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
                "recoveryNextAction": "restore_receipt_outcome_truth",
                "recoveryHistoryComponent": "receipt_outcome_truth",
                "recoveryHistoryStatus": "degraded",
                "recoveryReliabilityClass": "degraded",
                "recoveryReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "recoveryReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                    "settled_profit_truth_unavailable",
                ],
            }
        }

    def fund_summary_state(self):
        return self._summary


@pytest.mark.asyncio
async def test_runtime_auto_execute_preserves_receipt_outcome_truth_recovery_contract_in_auto_trade_recovery_history(
    tmp_path,
):
    harness = _PersistentReceiptOutcomeTruthAutoExecHarness(
        str(tmp_path / "runtime-receipt-outcome.sqlite3")
    )
    opp = SimpleNamespace(id="opp-receipt-outcome", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is True
    assert recovery["status"] == "capital_truth_restore_required"
    assert recovery["reason_code"] == "settled_profit_truth_unavailable"
    assert recovery["reason_codes"] == ["settled_profit_truth_unavailable"]
    assert recovery["next_action"] == "restore_receipt_outcome_truth"
    assert recovery["component"] == "receipt_outcome_truth"
    assert recovery["history_status"] == "degraded"
    assert recovery["reliability_class"] == "degraded"
    assert recovery["reliability_reason_code"] == "receipt_outcome_truth_reliability_degraded"
    assert recovery["reliability_reason_codes"] == [
        "receipt_outcome_truth_reliability_degraded",
        "settled_profit_truth_unavailable",
    ]
    assert recovery["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    history = list(recovery.get("recent_events") or [])
    assert len(history) == 1
    assert history[0]["event_type"] == "blocked"
    assert history[0]["stage"] == "fund_hold"
    assert history[0]["reason_code"] == "settled_profit_truth_unavailable"
    assert history[0]["history_component"] == "receipt_outcome_truth"
    assert history[0]["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert history[0]["reliability_reason_code"] == ("receipt_outcome_truth_reliability_degraded")


@pytest.mark.asyncio
async def test_runtime_auto_execute_persists_admission_gate_failure_history_without_summary_reads(
    tmp_path,
):
    harness = _PersistentAutoExecHarness(
        str(tmp_path / "runtime.sqlite3"),
        execution_service=_ExplodingAdmissionExecutionService(),
    )
    opp = SimpleNamespace(id="opp-admission-runtime-persisted", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is True
    assert recovery["status"] == "auto_trade_admission_restore_required"
    assert recovery["reason_code"] == "admission_gate_failed"
    assert recovery["history_status"] == "blocked"
    history = list(recovery.get("recent_events") or [])
    assert len(history) == 1
    assert history[0]["event_type"] == "blocked"
    assert history[0]["stage"] == "admission_hold"
    assert history[0]["reason_code"] == "admission_gate_failed"
    assert history[0]["next_action"] == "restore_auto_trade_admission_state"


@pytest.mark.asyncio
async def test_runtime_auto_execute_records_blocked_update_when_runtime_blocker_reason_changes_without_summary_reads(
    tmp_path,
):
    harness = _PersistentAutoExecHarness(
        str(tmp_path / "runtime.sqlite3"), execution_service=_DeniedExecutionService()
    )
    opp = SimpleNamespace(id="opp-runtime-blocked-update", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    harness._execution_service = _DeniedRouteExecutionService()
    await RuntimeBundle._execute_auto(harness, opp, 124)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is True
    assert recovery["status"] == "execution_route_restore_required"
    assert recovery["reason_code"] == "profit_after_costs_unavailable"
    assert recovery["history_status"] == "blocked"
    assert recovery["degraded_count"] == 1
    history = list(recovery.get("recent_events") or [])
    assert [evt["event_type"] for evt in history[:2]] == ["blocked_update", "blocked"]
    assert history[0]["stage"] == "route_hold"
    assert history[0]["reason_code"] == "profit_after_costs_unavailable"

    await RuntimeBundle._execute_auto(harness, opp, 125)

    repeated = current_auto_trade_recovery_info(harness)
    assert repeated["blocked"] is True
    assert repeated["degraded_count"] == 1
    repeated_history = list(repeated.get("recent_events") or [])
    assert [evt["event_type"] for evt in repeated_history[:2]] == ["blocked_update", "blocked"]


@pytest.mark.asyncio
async def test_runtime_auto_execute_persists_recovered_event_after_runtime_block_clears_without_summary_reads(
    tmp_path,
):
    harness = _PersistentAllowedAutoExecHarness(
        str(tmp_path / "runtime.sqlite3"), execution_service=_DeniedExecutionService()
    )
    opp = SimpleNamespace(id="opp-runtime-recovered", meta={})

    await RuntimeBundle._execute_auto(harness, opp, 123)

    harness._execution_service = _AllowExecutionService()
    await RuntimeBundle._execute_auto(harness, opp, 124)

    recovery = current_auto_trade_recovery_info(harness)
    assert recovery["blocked"] is False
    assert recovery["ready"] is True
    assert recovery["status"] == "ready"
    assert recovery["history_status"] == "recovered"
    assert recovery["degraded_count"] == 1
    assert recovery["last_healthy_ts_ms"] > 0
    history = list(recovery.get("recent_events") or [])
    assert [evt["event_type"] for evt in history[:2]] == ["recovered", "blocked"]
    assert history[0]["stage"] == "ok"
    assert history[0]["reason_code"] == "ok"


class _FioaStub:
    TRADE_EXECUTION = "TRADE_EXECUTION"
    INTERNAL_STRATEGY = "INTERNAL_STRATEGY"

    def __init__(
        self, *, enabled: bool = True, estimate=(0.25, 0.1), estimate_exc: Exception | None = None
    ):
        self.cfg = SimpleNamespace(enabled=enabled)
        self._estimate = estimate
        self._estimate_exc = estimate_exc
        self.wrapper_calls = []

    def estimate_trade_context(self, runtime, opp, *, decision=None):
        if self._estimate_exc is not None:
            raise self._estimate_exc
        return self._estimate

    async def execution_wrapper(self, core_coro, **kwargs):
        self.wrapper_calls.append(dict(kwargs))
        return await core_coro()


class _FioaRuntimeStub:
    def __init__(self, fioa):
        self._fioa = fioa


@pytest.mark.asyncio
async def test_handle_fioa_execution_wrapper_uses_wrapper_with_estimated_context():
    service = ExecutionService()
    fioa = _FioaStub(estimate=(0.4, 0.2))
    runtime = _FioaRuntimeStub(fioa)
    opp = SimpleNamespace(id="opp-fioa", route_id="route-fioa")
    core_calls = []

    async def _core():
        core_calls.append("called")
        return ExecResult(True, False, "ok", attempted=True)

    res = await service.handle_fioa_execution_wrapper(runtime, opp, None, _core)

    assert isinstance(res, ExecResult)
    assert res.ok is True
    assert core_calls == ["called"]
    assert len(fioa.wrapper_calls) == 1
    call = fioa.wrapper_calls[0]
    assert call["agent_id"] == "ARBITRAGE_AGENT"
    assert call["action_type"] == "TRADE_EXECUTION"
    assert call["capital"] == 0.4
    assert call["risk"] == 0.2
    assert call["data_level"] == "INTERNAL_STRATEGY"
    assert call["meta"] == {"opportunity_id": "opp-fioa", "route_id": "route-fioa"}


@pytest.mark.asyncio
async def test_handle_fioa_execution_wrapper_zeroes_context_when_estimate_raises():
    service = ExecutionService()
    fioa = _FioaStub(estimate_exc=RuntimeError("estimate offline"))
    runtime = _FioaRuntimeStub(fioa)
    opp = SimpleNamespace(id="opp-fioa-fallback", route_id="route-fioa-fallback")

    async def _core():
        return ExecResult(True, False, "ok", attempted=True)

    await service.handle_fioa_execution_wrapper(runtime, opp, None, _core)

    assert len(fioa.wrapper_calls) == 1
    call = fioa.wrapper_calls[0]
    assert call["capital"] == 0.0
    assert call["risk"] == 0.0


class _LatencyTrackerStub:
    def __init__(self):
        self.values = []

    def add(self, key: str, value: float):
        assert key == "exec_e2e_ms"
        self.values.append(float(value))

    def get(self, key: str):
        assert key == "exec_e2e_ms"
        values = list(self.values)
        if not values:
            return {"p50": 0.0, "p90": 0.0, "p99": 0.0}
        values.sort()
        return {"p50": values[0], "p90": values[-1], "p99": values[-1]}


class _PostExecuteRuntimeStub:
    def __init__(self):
        self._cc = None
        self._lat = _LatencyTrackerStub()
        self._last_submitted_block = None
        self.metrics = SimpleNamespace(
            exec_e2e_p50_ms=0.0,
            exec_e2e_p90_ms=0.0,
            exec_e2e_p99_ms=0.0,
            last_submitted_block=None,
        )
        self.recorded = []

    async def _record_exec(self, res, opp, latency_ms: int, mode: str):
        self.recorded.append((res, opp, latency_ms, mode))


@pytest.mark.asyncio
async def test_handle_post_execute_bookkeeping_updates_latency_metrics_and_submitted_block():
    service = ExecutionService()
    runtime = _PostExecuteRuntimeStub()
    opp = SimpleNamespace(id="opp-post-exec")
    res = ExecResult(
        True,
        False,
        "ok",
        attempted=True,
        submitted=True,
        plan={"latency_stages_ms": {"total": 12.5}},
    )

    await service.handle_post_execute_bookkeeping(
        runtime,
        opp,
        res,
        bn=321,
        latency_ms=17,
        mode="auto",
    )

    assert runtime.recorded == [(res, opp, 17, "auto")]
    assert runtime._lat.values == [12.5]
    assert runtime.metrics.exec_e2e_p50_ms == 12.5
    assert runtime.metrics.exec_e2e_p90_ms == 12.5
    assert runtime.metrics.exec_e2e_p99_ms == 12.5
    assert runtime._last_submitted_block == 321
    assert runtime.metrics.last_submitted_block == 321


class _PostExecuteRecordingExecutionService(_AllowExecutionService):
    def __init__(self):
        self.calls = []

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn: int, latency_ms: int, mode: str
    ):
        self.calls.append(
            {"opp": opp, "result": result, "bn": bn, "latency_ms": latency_ms, "mode": mode}
        )
        return await ExecutionService.handle_post_execute_bookkeeping(
            self,
            runtime,
            opp,
            result,
            bn=bn,
            latency_ms=latency_ms,
            mode=mode,
        )


class _PostExecuteRuntimeHarness(_AutoExecHarness):
    def __init__(self):
        service = _PostExecuteRecordingExecutionService()
        super().__init__(execution_service=service)
        self._execution_service = service
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
            ),
        )
        self.metrics = SimpleNamespace(
            gas_mode="standard",
            send_mode="public",
            exec_e2e_p50_ms=0.0,
            exec_e2e_p90_ms=0.0,
            exec_e2e_p99_ms=0.0,
            last_submitted_block=None,
        )
        self.rpc_manager = _ReachableRpcManagerStub()
        self._last_submitted_block = None
        self.cache = None
        self._mev_guard = None
        self._cc = None
        self._lat = _LatencyTrackerStub()


class _FioaRuntimeAutoExecHarness(_AutoExecHarness):
    def __init__(self, fioa):
        super().__init__(execution_service=_AllowExecutionService())
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="test"),
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
            ),
        )
        self.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
        self.rpc_manager = _ReachableRpcManagerStub()
        self._fioa = fioa
        self._last_submitted_block = None
        self.cache = None
        self._mev_guard = None


@pytest.mark.asyncio
async def test_runtime_auto_execute_routes_core_through_extracted_fioa_handler(monkeypatch):
    import victor_ai_bot.runtime_legacy as runtime_legacy_module

    class _DummyJsonRpcClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_try_execute(*args, **kwargs):
        return ExecResult(True, False, "ok", attempted=True)

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _DummyJsonRpcClient)
    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", _fake_try_execute)

    fioa = _FioaStub(estimate=(0.3, 0.15))
    harness = _FioaRuntimeAutoExecHarness(fioa)
    opp = SimpleNamespace(
        id="opp-fioa-runtime",
        route_id="route-fioa-runtime",
        route=SimpleNamespace(legs=[]),
        meta={},
    )

    await RuntimeBundle._execute_auto(harness, opp, 111, None)

    assert len(fioa.wrapper_calls) == 1
    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert isinstance(res, ExecResult)
    assert res.ok is True
    assert recorded_opp is opp
    assert mode == "auto"
    assert latency_ms >= 0


@pytest.mark.asyncio
async def test_runtime_auto_execute_routes_post_execute_bookkeeping_through_extracted_handler(
    monkeypatch,
):
    import victor_ai_bot.runtime_legacy as runtime_legacy_module

    class _DummyJsonRpcClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _fake_try_execute(*args, **kwargs):
        return ExecResult(True, False, "ok", attempted=True, submitted=True)

    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _DummyJsonRpcClient)
    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", _fake_try_execute)

    harness = _PostExecuteRuntimeHarness()
    opp = SimpleNamespace(
        id="opp-post-runtime",
        route_id="route-post-runtime",
        route=SimpleNamespace(legs=[]),
        meta={},
    )

    await RuntimeBundle._execute_auto(harness, opp, 222, None)

    assert len(harness._execution_service.calls) == 1
    call = harness._execution_service.calls[0]
    assert call["opp"] is opp
    assert call["bn"] == 222
    assert call["mode"] == "auto"
    assert call["latency_ms"] >= 0
    assert len(harness.recorded) == 1
    res, recorded_opp, latency_ms, mode = harness.recorded[0]
    assert res.ok is True
    assert recorded_opp is opp
    assert mode == "auto"
    assert latency_ms >= 0
    assert harness._last_submitted_block == 222
    assert harness.metrics.last_submitted_block == 222


class _RuntimeWithControlMode:
    def __init__(self, *, force_send_mode: str = ""):
        self.cfg = SimpleNamespace(execution=SimpleNamespace(send_mode="public"))
        self._cc = SimpleNamespace(controls=SimpleNamespace(force_send_mode=force_send_mode))


def test_auto_trade_execution_realism_gate_blocks_when_capture_payload_marks_drop():
    service = ExecutionService()
    opp = SimpleNamespace(
        meta={
            "strategy_family": "funding_arb",
            "profit_after_costs": "250",
            "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
            "execution_route_runtime": {"degraded": False, "reason_codes": []},
            "capture": {
                "action": "drop",
                "drop_reason": "stale_or_decayed_edge",
                "metadata": {
                    "execution_route_plan": {
                        "executable": True,
                        "selected_venues": ["uni"],
                        "provider_priority": ["router-a"],
                        "route_invalid_causes": [],
                    }
                },
            },
        },
        route=SimpleNamespace(legs=[SimpleNamespace(min_out="100")]),
        min_outs=["100"],
    )

    prepared, gate = service.auto_trade_execution_realism_gate(
        opp,
        decision=None,
        runtime=_RuntimeWithControlMode(),
    )

    assert getattr(prepared, "meta", {}).get("capture", {}).get("action") == "drop"
    assert gate.allowed is False
    assert gate.reason == "stale_or_decayed_edge"
    assert gate.metadata["suggestedNextAction"] == "refresh_execution_capture"


def test_auto_trade_execution_realism_gate_blocks_when_private_lane_capture_is_forced_public():
    service = ExecutionService()
    opp = SimpleNamespace(
        meta={
            "strategy_family": "funding_arb",
            "profit_after_costs": "250",
            "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
            "execution_route_runtime": {"degraded": False, "reason_codes": []},
            "capture": {
                "lane": "PRIVATE",
                "metadata": {
                    "execution_route_plan": {
                        "executable": True,
                        "selected_venues": ["uni"],
                        "provider_priority": ["router-a"],
                        "route_invalid_causes": [],
                    }
                },
            },
        },
        route=SimpleNamespace(legs=[SimpleNamespace(min_out="100")]),
        min_outs=["100"],
    )

    _, gate = service.auto_trade_execution_realism_gate(
        opp,
        decision=None,
        runtime=_RuntimeWithControlMode(force_send_mode="public"),
    )

    assert gate.allowed is False
    assert gate.reason == "private_lane_required"
    assert gate.metadata["reason_codes"] == [
        "private_lane_required",
        "operator_force_send_mode_conflict",
    ]
    assert (
        gate.metadata["suggestedNextAction"]
        == "clear_force_send_mode_or_restore_private_submission"
    )


def test_auto_trade_hold_gate_blocks_on_stale_capital_truth_health_even_when_hold_fields_are_soft():
    runtime = _RuntimeWithFundSummary(
        {
            "ok": True,
            "health": {
                "capitalTruthStatus": "degraded",
                "capitalTruthFreshnessClass": "stale",
                "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
                "suggestedNextAction": "refresh_capital_truth_snapshot",
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "capital_truth_freshness_stale",
                "recoveryReasonCodes": ["capital_truth_freshness_stale"],
                "recoveryNextAction": "refresh_capital_truth_snapshot",
            },
            "capitalTruthStatus": "degraded",
            "capitalTruthReasonCodes": ["capital_truth_freshness_stale"],
            "capitalTruthFreshnessClass": "stale",
            "capitalTruthFreshnessReasonCodes": ["capital_truth_freshness_stale"],
            "recoveryStatus": "capital_truth_restore_required",
            "recoveryReasonCode": "capital_truth_freshness_stale",
            "recoveryReasonCodes": ["capital_truth_freshness_stale"],
            "recoveryNextAction": "refresh_capital_truth_snapshot",
        }
    )
    gate = ExecutionService().auto_trade_hold_gate(runtime)
    assert gate.allowed is False
    assert gate.reason == "capital_truth_freshness_stale"
    assert gate.metadata["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert gate.metadata["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert gate.metadata["capitalTruthReasonCodes"] == ["capital_truth_freshness_stale"]
    assert gate.metadata["suggestedNextAction"] == "refresh_capital_truth_snapshot"
