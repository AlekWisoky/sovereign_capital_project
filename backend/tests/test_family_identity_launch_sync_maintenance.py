from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.fund_os.family_readiness import build_family_readiness
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager
from victor_ai_bot.runtime_services.launch_service import LaunchService


BASE_SUMMARY = {
    "capitalReady": True,
    "internalPrimeReady": True,
    "privateRoutingReady": True,
    "receiptOutcomeTruthFreshnessClass": "current",
    "receiptOutcomeTruthFreshnessReasonCodes": [],
    "receiptOutcomeTruthReliabilityClass": "stable",
    "receiptOutcomeTruthReliabilityReasonCode": "ok",
    "receiptOutcomeTruthReliabilityReasonCodes": [],
}


def test_family_readiness_normalizes_runtime_aliases_into_launch_family_identity():
    readiness = build_family_readiness(
        family="flashloan_atomic",
        stage="private_fund",
        scorecards={
            "families": [
                {
                    "family": "flashloan_atomic",
                    "count": 12,
                    "executionSuccessRate": 0.91,
                    "gasEfficiency": 3.4,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.1,
                }
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "flashloan_atomic", "mode": "live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "flashloan_atomic", "route_family": "flashloan_atomic|uni"},
                    "admission": {"allowed": True, "mode": "live"},
                    "capture": {"action": "trade"},
                }
            ],
        },
        telemetry={"venueReliability": 0.91},
        calibration={"items": [{"route_family": "flashloan_atomic", "calibration_factor": 1.0}]},
        fund_summary=dict(BASE_SUMMARY),
        active_families=["flash_arb"],
        family_states={"flash_arb": "live"},
        exploration_budget={"used_trades": 0, "max_trades": 3},
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.5}}},
    )
    assert readiness["family"] == "flash_arb"
    assert readiness["requestedFamily"] == "flashloan_atomic"
    assert readiness["launchFamily"] == "flash_arb"
    assert readiness["runtimeFamily"] == "flashloan_atomic"
    assert readiness["capitalFamily"] == "flashloan_atomic"
    assert "flashloan_atomic" in readiness["familyAliases"]
    assert readiness["count"] == 12
    assert readiness["executionEvidencePresent"] is True
    assert readiness["actualExecutionReady"] is True



def test_family_status_surfaces_execution_truth_override_for_active_noncore_family():
    readiness = build_family_readiness(
        family="funding_arb",
        stage="private_fund",
        scorecards={
            "families": [
                {
                    "family": "funding_arb",
                    "count": 8,
                    "executionSuccessRate": 0.74,
                    "gasEfficiency": 2.5,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.1,
                }
            ]
        },
        engine_state={
            "summary": {"engines": [{"engine_type": "funding_arb", "mode": "live"}]},
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 42.0},
                    "admission": {"allowed": True, "mode": "observe_only"},
                    "capture": {"action": "drop", "drop_reason": "insufficient_confidence"},
                }
            ],
        },
        telemetry={"venueReliability": 0.8},
        calibration={"items": [{"route_family": "funding_arb", "calibration_factor": 0.9}]},
        fund_summary=dict(BASE_SUMMARY),
        active_families=["flash_arb", "funding_arb"],
        family_states={"funding_arb": "live"},
        exploration_budget={"used_trades": 0, "max_trades": 3},
        capital_state={"capital_engine": {"family_targets": {"funding_arb": 0.2}}},
    )
    assert readiness["profileState"] == "live"
    assert readiness["effectiveState"] == "degraded"
    assert readiness["stateAlignment"] == "execution_truth_override"
    assert readiness["executionEvidencePresent"] is True
    assert readiness["actualExecutionReady"] is False


class _StubRollout:
    def __init__(self):
        self.profile = SimpleNamespace(
            rollout_order=["flash_arb", "funding_arb"],
            family_states={"flash_arb": "live", "funding_arb": "observe_only"},
        )
        self.calls = []

    def recommendation(self, **kwargs):
        return {
            "recommended_next_family": "funding_arb",
            "families": [{"family": "funding_arb", "ready": True, "status": "eligible"}],
            "profile": {"mode": "V1_ONLY"},
        }

    def family_detail(self, family, **kwargs):
        self.calls.append(("family_detail", family, kwargs))
        return {"ok": True, "family": family, "item": {"family": family}, "profile": {}}


class _Runtime:
    def __init__(self):
        self._launch_rollout = _StubRollout()
        self._cc = SimpleNamespace(controls=SimpleNamespace(paused=False, allocations_frozen=False))
        self._ledger = SimpleNamespace(tail=lambda limit=50: [], transactions_tail=lambda limit=50: [], balances=lambda: {"USD": 10.0})
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 0.0})
        self._last_operator_pnl_summary = {"total_realized_profit_after_gas_usd": 10.0}
        self._treasury = SimpleNamespace(snapshot=lambda: {"ok": True, "enabled": True}, cfg=SimpleNamespace(meta={}))

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

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"flashloan_atomic": 0.5}}}



def test_launch_service_family_detail_accepts_runtime_alias_and_routes_canonical_launch_family():
    svc = LaunchService()
    runtime = _Runtime()
    out = svc.family_detail(runtime, "flashloan_atomic")
    assert out["ok"] is True
    assert out["family"] == "flash_arb"
    assert runtime._launch_rollout.calls[0][1] == "flash_arb"



def test_staged_rollout_family_detail_accepts_runtime_alias():
    mgr = StagedRolloutManager(data_dir="/tmp/family_identity_launch_sync", chain="eth")
    detail = mgr.family_detail(
        "flashloan_atomic",
        stage="private_fund",
        scorecards={"families": [{"family": "flashloan_atomic", "count": 10, "executionSuccessRate": 0.9, "gasEfficiency": 3.0}]},
        engine_state={"summary": {"engines": [{"engine_type": "flashloan_atomic", "mode": "live"}]}, "items": []},
        telemetry={"venueReliability": 0.9},
        calibration={"items": [{"route_family": "flashloan_atomic", "calibration_factor": 1.0}]},
        fund_summary=dict(BASE_SUMMARY),
        capital_state={"capital_engine": {"family_targets": {"flashloan_atomic": 0.5}}},
    )
    assert detail["ok"] is True
    assert detail["family"] == "flash_arb"
    assert detail["item"]["family"] == "flash_arb"
