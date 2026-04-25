from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.models import Metrics
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.state_service import StateService
from victor_ai_bot.runtime_services.execution_service import ExecutionService


class _UnexpectedOptionalFailure(Exception):
    pass


class _UnexpectedSyncComponent:
    def state(self):
        raise _UnexpectedOptionalFailure("boom")


class _UnexpectedAsyncComponent:
    async def query(self, runtime, *, agent_id: str, query_text: str, data_level: str):
        del runtime, agent_id, query_text, data_level
        raise _UnexpectedOptionalFailure("boom")


class _RuntimeStateStub:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(
                redact_routes_when_private=False,
                send_mode="private",
                gas_mode="standard",
                brain_mode="off",
                dry_run=True,
                withdraw_mode="txdata",
                executor_address="0x0",
                enforce_executor_version=False,
                expected_executor_abi_version=0,
            ),
        )
        self._opps = []
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
        self._auto_trading = False
        self._executor_abi_version = None
        self._executor_impl_version = None
        self._executor_version_error = None


def test_auxiliary_state_service_keeps_expected_runtime_failures_structured():
    runtime = SimpleNamespace(
        _mev=SimpleNamespace(state=lambda: (_ for _ in ()).throw(RuntimeError("mev_state")))
    )
    svc = AuxiliaryStateService()

    assert svc.mev_state(runtime)["error"] == "mev_state_failed:mev_state"


def test_auxiliary_state_service_does_not_swallow_unexpected_sync_failures():
    runtime = SimpleNamespace(_mev=_UnexpectedSyncComponent())
    svc = AuxiliaryStateService()

    with pytest.raises(_UnexpectedOptionalFailure):
        svc.mev_state(runtime)


def test_auxiliary_state_service_does_not_swallow_unexpected_async_failures():
    runtime = SimpleNamespace(_inl=_UnexpectedAsyncComponent())
    svc = AuxiliaryStateService()

    with pytest.raises(_UnexpectedOptionalFailure):
        asyncio.run(svc.narrative_query(runtime, agent_id="ops", query_text="status"))


def test_state_service_contract_validation_hook_records_expected_failures(monkeypatch):
    runtime = _RuntimeStateStub()

    monkeypatch.setenv("VICTOR_VALIDATE_CONTRACT", "1")
    monkeypatch.setattr(
        "victor_ai_bot.contract.validate_runtime_state",
        lambda data: (_ for _ in ()).throw(ValueError("bad_state")),
    )

    payload = asyncio.run(StateService().snapshot(runtime))

    assert payload["chain"] == "ethereum"
    assert runtime._errors[-1] == "contract_validation_failed:bad_state"


def test_state_service_contract_validation_hook_does_not_hide_unexpected_failures(monkeypatch):
    runtime = _RuntimeStateStub()

    monkeypatch.setenv("VICTOR_VALIDATE_CONTRACT", "1")
    monkeypatch.setattr(
        "victor_ai_bot.contract.validate_runtime_state",
        lambda data: (_ for _ in ()).throw(Exception("unexpected")),
    )

    with pytest.raises(Exception, match="unexpected"):
        asyncio.run(StateService().snapshot(runtime))


class _SummaryOpp:
    def __init__(
        self,
        *,
        oid: str,
        expected_profit_raw: str,
        can_execute: bool,
        route_id: str,
        meta: dict[str, object] | None = None,
    ):
        self.id = oid
        self.strategy = "flash_arb"
        self.expected_profit_raw = expected_profit_raw
        self.can_execute = can_execute
        self.route_id = route_id
        self.meta = meta or {}


def test_state_service_summary_prefers_verified_after_cost_top_opportunity():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="gross-only", expected_profit_raw="9999", can_execute=True, route_id="r-gross"
        ),
        _SummaryOpp(
            oid="after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-after",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "after-cost"
    assert payload["top_opportunity"]["expected_profit_after_costs_wei"] == "250"
    assert payload["top_opportunity"]["profit_after_costs_verified"] is True
    assert payload["top_opportunity"]["can_execute_after_costs"] is True
    assert payload["top_opportunity"]["selected_on_after_costs"] is True


def test_state_service_summary_skips_mismatched_after_fee_truth_when_selecting_top_opportunity():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="mismatched-higher-profit",
            expected_profit_raw="1000",
            can_execute=True,
            route_id="r-mismatch",
            meta={
                "profit_after_costs": "900",
                "safety": {"profit_after_costs_wei": "100", "exec_ready": True},
            },
        ),
        _SummaryOpp(
            oid="verified-lower-profit",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-verified",
            meta={
                "profit_after_costs": "250",
                "safety": {"profit_after_costs_wei": "250", "exec_ready": True},
            },
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "verified-lower-profit"
    assert payload["top_opportunity"]["expected_profit_after_costs_wei"] == "250"
    assert payload["top_opportunity"]["profit_after_costs_verified"] is True
    assert payload["top_opportunity"]["profit_after_costs_reason"] == "ok"
    assert payload["top_opportunity"]["can_execute_after_costs"] is True


def test_state_service_summary_prefers_execution_ready_after_cost_opportunity_over_blocked_higher_profit():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="blocked-higher-profit",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-blocked",
            meta={
                "profit_after_costs": "500",
                "safety": {"exec_ready": False, "reason": "signing_not_ready"},
            },
        ),
        _SummaryOpp(
            oid="ready-lower-profit",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "ready-lower-profit"
    assert payload["top_opportunity"]["can_execute_after_costs"] is True



def test_state_service_summary_prefers_verified_non_positive_truth_over_positional_gross_only_fallback():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="gross-first",
            expected_profit_raw="9999",
            can_execute=True,
            route_id="r-gross",
        ),
        _SummaryOpp(
            oid="verified-not-positive",
            expected_profit_raw="10",
            can_execute=True,
            route_id="r-verified",
            meta={
                "profit_after_costs": "0",
                "safety": {"profit_after_costs_wei": "0", "exec_ready": True},
            },
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "verified-not-positive"
    assert payload["top_opportunity"]["profit_after_costs_verified"] is True
    assert payload["top_opportunity"]["profit_after_costs_reason"] == "profit_after_costs_not_positive"
    assert payload["top_opportunity"]["can_execute_after_costs"] is False


def test_state_service_summary_prefers_execution_ready_fallback_over_non_ready_positional_first():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="not-ready-first",
            expected_profit_raw="5000",
            can_execute=True,
            route_id="r-first",
            meta={"safety": {"exec_ready": False, "reason": "executor_missing"}},
        ),
        _SummaryOpp(
            oid="fallback-ready",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "fallback-ready"
    assert payload["top_opportunity"]["execution_ready"] is True
    assert payload["top_opportunity"]["execution_ready_reason"] == "ok"
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["selected_on_execution_eligibility"] is False
    assert payload["top_opportunity"]["execution_ready"] is True
    assert payload["top_opportunity"]["execution_ready_reason"] == "ok"


def test_state_service_summary_marks_after_cost_opportunity_not_executable_when_exec_ready_is_false():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="blocked-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-blocked",
            meta={
                "profit_after_costs": "250",
                "safety": {"exec_ready": False, "reason": "executor_missing"},
            },
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "blocked-after-cost"
    assert payload["top_opportunity"]["can_execute"] is True
    assert payload["top_opportunity"]["execution_ready"] is False
    assert payload["top_opportunity"]["execution_ready_reason"] == "executor_missing"
    assert payload["top_opportunity"]["can_execute_after_costs"] is False


def test_state_service_summary_prefers_route_ready_after_cost_opportunity_over_higher_profit_route_invalid():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="route-invalid-higher-profit",
            expected_profit_raw="1000",
            can_execute=True,
            route_id="r-invalid",
            meta={
                "profit_after_costs": "500",
                "safety": {"exec_ready": True},
                "execution_route_plan": {
                    "executable": False,
                    "route_invalid_causes": ["leg:0:venue-a:invalid"],
                },
                "route_invalid_causes": ["leg:0:venue-a:invalid"],
            },
        ),
        _SummaryOpp(
            oid="route-ready-lower-profit",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={
                "profit_after_costs": "250",
                "safety": {"exec_ready": True},
                "execution_route_plan": {"executable": True},
            },
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "route-ready-lower-profit"
    assert payload["top_opportunity"]["execution_ready"] is True
    assert payload["top_opportunity"]["execution_ready_reason"] == "ok"
    assert payload["top_opportunity"]["selected_on_execution_eligibility"] is True


def test_state_service_summary_marks_route_runtime_degraded_after_cost_opportunity_not_execution_ready():
    runtime = _RuntimeStateStub()
    runtime._opps = [
        _SummaryOpp(
            oid="route-runtime-degraded",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-runtime",
            meta={
                "profit_after_costs": "250",
                "safety": {"exec_ready": True},
                "execution_route_plan": {"executable": True},
                "execution_route_runtime": {
                    "degraded": True,
                    "profit": {"ok": False, "code": "plan_profit_after_costs_mismatch"},
                },
            },
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["top_opportunity"]["id"] == "route-runtime-degraded"
    assert payload["top_opportunity"]["execution_ready"] is False
    assert payload["top_opportunity"]["execution_ready_reason"] == "profit_after_costs_mismatch"
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["meta"]["route_runtime_degraded"] is True
    assert payload["top_opportunity"]["meta"]["route_runtime_reason_codes"] == [
        "profit_after_costs_mismatch"
    ]


def test_state_service_summary_blocks_after_cost_executability_when_drawdown_hard_stop_is_active():
    runtime = _RuntimeStateStub()
    runtime._drawdown_state = SimpleNamespace(
        snapshot=lambda: {
            "drawdownPct": 7.5,
            "hardStop": {"active": True, "reason_codes": ["drawdown_hard_stop"]},
        }
    )
    runtime._kill_switch = SimpleNamespace(
        snapshot=lambda: {"metrics": {}, "suppressions": {}, "history": []}
    )
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_gate"]["blocked"] is True
    assert payload["execution_gate"]["reason_code"] == "drawdown_hard_stop"
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["execution_gate_reason_code"] == "drawdown_hard_stop"


def test_state_service_summary_blocks_after_cost_executability_when_kill_switch_is_active():
    runtime = _RuntimeStateStub()
    runtime._drawdown_state = SimpleNamespace(
        snapshot=lambda: {"drawdownPct": 0.0, "hardStop": {"active": False, "reason_codes": []}}
    )
    runtime._kill_switch = SimpleNamespace(
        snapshot=lambda: {
            "metrics": {},
            "suppressions": {"execution": {"reason": "manual_block"}},
            "history": [],
        }
    )
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_gate"]["blocked"] is True
    assert payload["execution_gate"]["reason_code"] == "kill_switch_active"
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["execution_gate_reason_codes"] == ["kill_switch_active"]


class _CapitalTruthHoldRuntime(_RuntimeStateStub):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "holdReasonCode": "capital_truth_degraded",
                    "holdReasonCodes": ["capital_truth_degraded"],
                    "capitalTruthReasonCodes": ["capital_truth_degraded"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


class _InternalPrimeHoldRuntime(_RuntimeStateStub):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "holdReasonCode": "internal_prime_journal_borrowed_mismatch",
                    "holdReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                    "internalPrimeReasonCodes": ["internal_prime_journal_borrowed_mismatch"],
                    "suggestedNextAction": "repair_internal_prime_accounting",
                },
            }
        )


def test_state_service_summary_blocks_after_cost_executability_when_capital_truth_is_degraded():
    runtime = _CapitalTruthHoldRuntime()
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_gate"]["blocked"] is False
    assert payload["hold"]["blocked"] is True
    assert payload["hold"]["reason_code"] == "capital_truth_degraded"
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["hold_reason_code"] == "capital_truth_degraded"
    assert payload["top_opportunity"]["hold_reason_codes"] == ["capital_truth_degraded"]


def test_state_service_summary_blocks_after_cost_executability_when_internal_prime_truth_is_degraded():
    runtime = _InternalPrimeHoldRuntime()
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_gate"]["blocked"] is False
    assert payload["hold"]["blocked"] is True
    assert payload["hold"]["reason_code"] == "internal_prime_journal_borrowed_mismatch"
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert (
        payload["top_opportunity"]["hold_reason_code"] == "internal_prime_journal_borrowed_mismatch"
    )
    assert payload["top_opportunity"]["hold_reason_codes"] == [
        "internal_prime_journal_borrowed_mismatch"
    ]


class _CapitalTruthUnavailableRuntime(_RuntimeStateStub):
    def __init__(self):
        super().__init__()
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                "ok": True,
                "health": {
                    "holdReasonCode": "capital_truth_unavailable",
                    "holdReasonCodes": ["capital_truth_unavailable"],
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "suggestedNextAction": "restore_capital_truth",
                },
            }
        )


def test_state_service_summary_blocks_after_cost_executability_when_capital_truth_is_unavailable():
    runtime = _CapitalTruthUnavailableRuntime()
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_gate"]["blocked"] is False
    assert payload["hold"]["blocked"] is True
    assert payload["hold"]["reason_code"] == "capital_truth_unavailable"
    assert payload["hold"]["reason_codes"] == ["capital_truth_unavailable"]
    assert payload["hold"]["recovery_status"] == "capital_truth_restore_required"
    assert payload["hold"]["recovery_reason_code"] == "capital_truth_unavailable"
    assert payload["hold"]["recovery_reason_codes"] == ["capital_truth_unavailable"]
    assert payload["hold"]["recovery_next_action"] == "restore_capital_truth"
    assert payload["hold"]["recovery_ready"] is False
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["hold_reason_code"] == "capital_truth_unavailable"
    assert payload["top_opportunity"]["hold_reason_codes"] == ["capital_truth_unavailable"]


def test_state_summary_hold_info_surfaces_recovery_history_count_and_severity_for_capital_truth_unavailable():
    from types import SimpleNamespace
    from victor_ai_bot.runtime_services.state_service import summary_hold_info

    runtime = SimpleNamespace(
        _fund_service=SimpleNamespace(
            summary=lambda runtime: {
                "health": {
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_unavailable",
                    "recoveryReasonCodes": ["capital_truth_unavailable"],
                    "recoveryHistoryComponent": "capital_truth",
                    "recoveryHistoryStatus": "degraded",
                    "recoveryDegradedCount": 2,
                    "recoveryLastHealthyTsMs": 1700000000000,
                    "recoveryDegradationSeverityClass": "persistent",
                    "capitalTruthRecoveryHistoryStatus": "degraded",
                    "capitalTruthDegradedCount": 2,
                    "capitalTruthLastHealthyTsMs": 1700000000000,
                    "capitalTruthDegradationSeverityClass": "persistent",
                }
            }
        )
    )

    out = summary_hold_info(runtime)
    assert out["recovery_degraded_count"] == 2
    assert out["recovery_last_healthy_ts_ms"] == 1700000000000
    assert out["recovery_degradation_severity_class"] == "persistent"
    assert out["capital_truth_degraded_count"] == 2
    assert out["capital_truth_last_healthy_ts_ms"] == 1700000000000
    assert out["capital_truth_degradation_severity_class"] == "persistent"


def test_state_summary_hold_info_surfaces_recovery_reliability_for_capital_truth_unavailable():
    from types import SimpleNamespace
    from victor_ai_bot.runtime_services.state_service import summary_hold_info

    runtime = SimpleNamespace(
        _fund_service=SimpleNamespace(
            summary=lambda runtime: {
                "health": {
                    "capitalTruthReasonCodes": ["capital_truth_unavailable"],
                    "recoveryStatus": "capital_truth_restore_required",
                    "recoveryReasonCode": "capital_truth_unavailable",
                    "recoveryReasonCodes": ["capital_truth_unavailable"],
                    "capitalTruthReliabilityClass": "unavailable",
                    "capitalTruthReliabilityReasonCode": "capital_truth_reliability_unavailable",
                    "capitalTruthReliabilityReasonCodes": [
                        "capital_truth_reliability_unavailable",
                        "capital_truth_freshness_unavailable",
                    ],
                    "recoveryReliabilityClass": "unavailable",
                    "recoveryReliabilityReasonCode": "recovery_reliability_unavailable",
                    "recoveryReliabilityReasonCodes": [
                        "recovery_reliability_unavailable",
                        "capital_truth_reliability_unavailable",
                    ],
                    "recoveryReliabilityNextAction": "restore_capital_truth",
                }
            }
        )
    )

    hold = summary_hold_info(runtime, {"blocked": False, "reason_code": "ok", "reason_codes": []})
    assert hold["capital_truth_reliability_class"] == "unavailable"
    assert hold["capital_truth_reliability_reason_code"] == "capital_truth_reliability_unavailable"
    assert hold["recovery_reliability_class"] == "unavailable"
    assert hold["recovery_reliability_reason_code"] == "recovery_reliability_unavailable"
    assert hold["recovery_reliability_next_action"] == "restore_capital_truth"


def test_state_summary_hold_info_fails_closed_when_family_hardening_service_is_unavailable():
    from types import SimpleNamespace

    from victor_ai_bot.runtime_services.state_service import summary_hold_info

    runtime = SimpleNamespace(
        _fund_service=SimpleNamespace(
            summary=lambda runtime: {
                "health": {
                    "familyHardeningReasonCodes": ["family_hardening_service_unavailable"],
                    "recoveryReady": True,
                    "recoveryStatus": "ready",
                    "recoveryReasonCode": "ok",
                    "recoveryReasonCodes": [],
                }
            }
        )
    )

    hold = summary_hold_info(runtime, {"blocked": False, "reason_code": "ok", "reason_codes": []})
    assert hold["blocked"] is True
    assert hold["reason_code"] == "family_hardening_service_unavailable"
    assert hold["reason_codes"] == ["family_hardening_service_unavailable"]
    assert hold["family_hardening_reason_codes"] == ["family_hardening_service_unavailable"]
    assert hold["recovery_ready"] is False
    assert hold["recovery_status"] == "family_hardening_restore_required"
    assert hold["recovery_reason_code"] == "family_hardening_service_unavailable"
    assert hold["recovery_reason_codes"] == ["family_hardening_service_unavailable"]
    assert hold["suggested_next_action"] == "restore_family_hardening"
    assert hold["recovery_next_action"] == "restore_family_hardening"


def test_state_service_summary_surfaces_execution_advisory_for_fragile_recovery_reliability_without_blocking_ready_top_opportunity():
    runtime = _RuntimeStateStub()
    runtime._fund_service = SimpleNamespace(
        summary=lambda runtime: {
            "health": {
                "recoveryReliabilityClass": "fragile",
                "recoveryReliabilityReasonCode": "recovery_reliability_fragile",
                "recoveryReliabilityReasonCodes": [
                    "recovery_reliability_fragile",
                    "recovery_recovered_fragile",
                ],
                "recoveryReliabilityNextAction": "repair_internal_prime_accounting",
            }
        }
    )
    runtime._opps = [
        _SummaryOpp(
            oid="ready-after-cost",
            expected_profit_raw="100",
            can_execute=True,
            route_id="r-ready",
            meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
        ),
    ]

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["execution_advisory"]["active"] is True
    assert payload["execution_advisory"]["severity"] == "warning"
    assert payload["execution_advisory"]["class"] == "fragile"
    assert payload["execution_advisory"]["reason_code"] == "recovery_reliability_fragile"
    assert payload["execution_advisory"]["next_action"] == "repair_internal_prime_accounting"
    assert payload["top_opportunity"]["execution_allowed"] is True
    assert payload["top_opportunity"]["execution_advisory_active"] is True
    assert payload["top_opportunity"]["execution_advisory_class"] == "fragile"
    assert (
        payload["top_opportunity"]["execution_advisory_reason_code"]
        == "recovery_reliability_fragile"
    )


def _execution_route_plan_ready() -> dict[str, object]:
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
        "provider_priority": [],
        "provider_fallback": "",
        "reserve_distortion": 0.0,
        "mutation_factor": 1.0,
        "route_invalid_causes": [],
        "runtime": {
            "input": {"ok": True, "code": "ok", "detail": ""},
            "legs": {"ok": True, "code": "ok", "detail": ""},
            "mutation": {"ok": True, "code": "ok", "detail": ""},
            "profit": {"ok": True, "code": "ok", "detail": ""},
            "degraded": False,
        },
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


def _summary_ready_non_flash_opp(*, oid: str = "treasury-blocked"):
    return SimpleNamespace(
        id=oid,
        strategy="funding_arb",
        expected_profit_raw="1000",
        can_execute=True,
        route_id="r-treasury",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(venue="uni", min_out="100"),
                SimpleNamespace(venue="curve", min_out="100"),
            ]
        ),
        min_outs=["100", "100"],
        meta={
            "strategy_family": "funding_arb",
            "profit_after_costs": "250",
            "safety": {"exec_ready": True, "profit_after_costs_wei": "250"},
            "capture": {"metadata": {"execution_route_plan": _execution_route_plan_ready()}},
        },
    )


def test_state_service_summary_surfaces_auto_trade_gate_when_treasury_governance_blocks_ready_top_opportunity():
    from victor_ai_bot.runtime_services.execution_service import ExecutionService

    runtime = _RuntimeStateStub()
    runtime._execution_service = ExecutionService()
    runtime._opps = [_summary_ready_non_flash_opp()]
    runtime._family_hardening_service = SimpleNamespace(
        family_state=lambda runtime, family: {
            "enabled": True,
            "controls": {
                "enabled": True,
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
    runtime._treasury = SimpleNamespace(
        cfg=SimpleNamespace(
            enabled=True, allow_maximum=False, max_aggressiveness_without_approval="HIGH"
        ),
        snapshot=lambda: {
            "aggressiveness": {"aggressiveness_level": "MAXIMUM", "aggressiveness_multiplier": 1.4},
            "goal": {"target_return_percentage": 12.0, "max_drawdown_pct": 4.0},
        },
        governance_check=lambda *, aggressiveness_level, approved_by_human=False: {
            "ok": False,
            "reason": "maximum_disabled",
        },
    )
    runtime.fund_summary_state = lambda: {
        "ok": True,
        "health": {
            "holdReasonCode": "",
            "holdReasonCodes": [],
            "recoveryReady": True,
            "recoveryStatus": "ready",
        },
    }

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["auto_trade_gate"]["allowed"] is False
    assert payload["auto_trade_gate"]["stage"] == "treasury_hold"
    assert payload["auto_trade_gate"]["reason_code"] == "maximum_disabled"
    assert payload["auto_trade_recovery"]["ready"] is False
    assert payload["auto_trade_recovery"]["status"] == "treasury_alignment_required"
    assert payload["auto_trade_recovery"]["reason_code"] == "maximum_disabled"
    assert payload["top_opportunity"]["execution_allowed"] is False
    assert payload["top_opportunity"]["can_execute_after_costs"] is False
    assert payload["top_opportunity"]["auto_trade_gate_stage"] == "treasury_hold"
    assert payload["top_opportunity"]["auto_trade_gate_reason_code"] == "maximum_disabled"
    assert payload["top_opportunity"]["auto_trade_recovery_status"] == "treasury_alignment_required"
    assert payload["top_opportunity"]["auto_trade_recovery_ready"] is False


class _ExplodingAdmissionSummaryService(ExecutionService):
    def auto_trade_hold_gate(self, runtime):
        raise RuntimeError("fund summary offline")


class _AdmissionFailureSummaryRuntime(_RuntimeStateStub):
    def __init__(self):
        super().__init__()
        self._opps = [
            _SummaryOpp(
                oid="after-cost",
                expected_profit_raw="100",
                can_execute=True,
                route_id="r-after",
                meta={"profit_after_costs": "250", "safety": {"exec_ready": True}},
            )
        ]
        self._execution_service = _ExplodingAdmissionSummaryService()


def test_state_service_summary_fails_closed_when_auto_trade_admission_gate_errors():
    runtime = _AdmissionFailureSummaryRuntime()

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["auto_trade_gate"]["allowed"] is False
    assert payload["auto_trade_gate"]["stage"] == "admission_hold"
    assert payload["auto_trade_gate"]["reason_code"] == "admission_gate_failed"
    assert payload["auto_trade_gate"]["next_action"] == "restore_auto_trade_admission_state"
    assert payload["auto_trade_recovery"]["ready"] is False
    assert payload["auto_trade_recovery"]["status"] == "auto_trade_admission_restore_required"
    assert payload["auto_trade_recovery"]["reason_code"] == "admission_gate_failed"
    assert payload["top_opportunity"]["auto_trade_allowed"] is False
    assert payload["top_opportunity"]["auto_trade_gate_reason_code"] == "admission_gate_failed"
    assert (
        payload["top_opportunity"]["auto_trade_recovery_status"]
        == "auto_trade_admission_restore_required"
    )
    assert payload["top_opportunity"]["can_execute_after_costs"] is False


def test_state_service_summary_projects_family_hardening_auto_trade_recovery_contract_into_top_opportunity():
    runtime = _RuntimeStateStub()
    runtime._execution_service = ExecutionService()
    runtime._opps = [_summary_ready_non_flash_opp()]
    runtime.fund_summary_state = lambda: {
        "ok": True,
        "health": {
            "holdReasonCode": "",
            "holdReasonCodes": [],
            "recoveryReady": True,
            "recoveryStatus": "ready",
        },
    }

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["auto_trade_gate"]["stage"] == "family_hold"
    assert payload["auto_trade_gate"]["reason_code"] == "family_hardening_unavailable"
    assert payload["auto_trade_recovery"]["status"] == "family_hardening_restore_required"
    assert payload["auto_trade_recovery"]["reason_code"] == "family_hardening_service_unavailable"
    assert (
        payload["top_opportunity"]["auto_trade_recovery_status"]
        == "family_hardening_restore_required"
    )
    assert (
        payload["top_opportunity"]["auto_trade_recovery_reason_code"]
        == "family_hardening_service_unavailable"
    )
    assert payload["top_opportunity"]["auto_trade_recovery_family_hardening_reason_codes"] == [
        "family_hardening_service_unavailable"
    ]
    assert payload["top_opportunity"]["auto_trade_recovery_reliability_class"] == "unavailable"
    assert (
        payload["top_opportunity"]["auto_trade_recovery_reliability_reason_code"]
        == "family_hardening_reliability_unavailable"
    )
    assert payload["top_opportunity"]["auto_trade_recovery_history_component"] == "family_hardening"
    assert payload["top_opportunity"]["auto_trade_recovery_history_status"] == "degraded"


class _PersistentAutoTradeRecoveryRuntime(_RuntimeStateStub):
    def __init__(self, db_path: str):
        super().__init__()
        self._db = PersistenceDB(db_path)
        self._execution_service = ExecutionService()
        self._opps = [_summary_ready_non_flash_opp()]
        self._family_hardening_service = SimpleNamespace(
            family_state=lambda runtime, family: {
                "enabled": True,
                "controls": {
                    "enabled": True,
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
        self._treasury_reason = "maximum_disabled"
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
                "approved_by_human": self._treasury_reason == "ok",
            },
            governance_check=lambda *, aggressiveness_level, approved_by_human=False: {
                "ok": self._treasury_reason == "ok",
                "reason": ("ok" if self._treasury_reason == "ok" else self._treasury_reason),
            },
        )
        self.fund_summary_state = lambda: {
            "ok": True,
            "health": {
                "holdReasonCode": "",
                "holdReasonCodes": [],
                "recoveryReady": True,
                "recoveryStatus": "ready",
            },
        }


def test_state_service_summary_persists_auto_trade_recovery_history_across_recovery_cycle(tmp_path):
    runtime = _PersistentAutoTradeRecoveryRuntime(str(tmp_path / "runtime.sqlite3"))

    first = asyncio.run(StateService().summary(runtime))
    assert first["auto_trade_gate"]["reason_code"] == "maximum_disabled"
    assert first["auto_trade_recovery"]["history_status"] == "blocked"
    assert first["auto_trade_recovery"]["degraded_count"] == 1
    assert first["top_opportunity"]["auto_trade_recovery_history_status"] == "blocked"
    first_events = list(first["auto_trade_recovery"].get("recent_events") or [])
    assert len(first_events) == 1
    assert first_events[0]["event_type"] == "blocked"
    assert first_events[0]["reason_code"] == "maximum_disabled"

    blocked_again = asyncio.run(StateService().summary(runtime))
    assert blocked_again["auto_trade_recovery"]["history_status"] == "blocked"
    assert blocked_again["auto_trade_recovery"]["degraded_count"] == 1
    blocked_again_events = list(blocked_again["auto_trade_recovery"].get("recent_events") or [])
    assert len(blocked_again_events) == 1
    assert blocked_again_events[0]["event_type"] == "blocked"

    runtime._treasury_reason = "ok"
    second = asyncio.run(StateService().summary(runtime))
    assert second["auto_trade_gate"]["reason_code"] == "ok"
    assert second["auto_trade_recovery"]["status"] == "ready"
    assert second["auto_trade_recovery"]["history_status"] == "recovered"
    assert second["auto_trade_recovery"]["degraded_count"] == 1
    assert second["auto_trade_recovery"]["last_healthy_ts_ms"] > 0
    assert second["top_opportunity"]["auto_trade_recovery_history_status"] == "recovered"
    assert second["top_opportunity"]["auto_trade_recovery_degraded_count"] == 1
    second_events = list(second["auto_trade_recovery"].get("recent_events") or [])
    assert [evt["event_type"] for evt in second_events[:2]] == ["recovered", "blocked"]
    assert second_events[0]["reason_code"] == "ok"


def test_state_service_summary_records_blocked_update_when_blocker_reason_changes_while_degraded(
    tmp_path,
):
    runtime = _PersistentAutoTradeRecoveryRuntime(str(tmp_path / "runtime.sqlite3"))

    first = asyncio.run(StateService().summary(runtime))
    assert first["auto_trade_recovery"]["history_status"] == "blocked"
    assert first["auto_trade_recovery"]["degraded_count"] == 1
    first_events = list(first["auto_trade_recovery"].get("recent_events") or [])
    assert len(first_events) == 1
    assert first_events[0]["event_type"] == "blocked"
    assert first_events[0]["reason_code"] == "maximum_disabled"

    runtime._treasury_reason = "aggressiveness_requires_approval"
    updated = asyncio.run(StateService().summary(runtime))
    assert updated["auto_trade_gate"]["reason_code"] == "aggressiveness_requires_approval"
    assert updated["auto_trade_recovery"]["history_status"] == "blocked"
    assert updated["auto_trade_recovery"]["degraded_count"] == 1
    assert updated["top_opportunity"]["auto_trade_recovery_history_status"] == "blocked"
    assert updated["top_opportunity"]["auto_trade_recovery_degraded_count"] == 1
    updated_events = list(updated["auto_trade_recovery"].get("recent_events") or [])
    assert [evt["event_type"] for evt in updated_events[:2]] == ["blocked_update", "blocked"]
    assert updated_events[0]["reason_code"] == "aggressiveness_requires_approval"
    assert updated_events[0]["stage"] == "treasury_hold"

    repeated = asyncio.run(StateService().summary(runtime))
    assert repeated["auto_trade_recovery"]["history_status"] == "blocked"
    assert repeated["auto_trade_recovery"]["degraded_count"] == 1
    repeated_events = list(repeated["auto_trade_recovery"].get("recent_events") or [])
    assert [evt["event_type"] for evt in repeated_events[:2]] == ["blocked_update", "blocked"]
    assert len(repeated_events) == 2


def test_state_service_summary_uses_persisted_blocked_auto_trade_recovery_when_no_top_candidate(
    tmp_path,
):
    import asyncio
    from victor_ai_bot.persistence.db import PersistenceDB
    from victor_ai_bot.persistence.repositories.auto_trade_recovery_repository import (
        AutoTradeRecoveryRepository,
    )

    runtime = _RuntimeStateStub()
    runtime._db = PersistenceDB(str(tmp_path / "runtime.sqlite3"))
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(name="test"),
        execution=SimpleNamespace(
            dry_run=False,
            gas_mode="legacy",
            send_mode="private",
            brain_mode="off",
            withdraw_mode="txdata",
        ),
    )
    repo = AutoTradeRecoveryRepository(runtime._db, chain="test")
    runtime._auto_trade_recovery_repo = repo
    repo.observe(
        component="auto_trade_admission",
        degraded=True,
        ts_ms=1_000,
        reason_code="maximum_disabled",
        stage="treasury_hold",
        blocker_component="treasury",
        next_action="lower_treasury_aggressiveness_or_enable_maximum",
        reason_codes=["maximum_disabled"],
    )
    runtime._opps = []

    payload = asyncio.run(StateService().summary(runtime))

    assert payload["auto_trade_recovery"]["blocked"] is True
    assert payload["auto_trade_recovery"]["status"] == "treasury_alignment_required"
    assert payload["auto_trade_recovery"]["reason_code"] == "maximum_disabled"
    assert payload["auto_trade_recovery"]["history_status"] == "blocked"
