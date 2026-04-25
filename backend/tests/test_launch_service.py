from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.launch_service import LaunchService


class _StubRollout:
    def __init__(self):
        self.profile = SimpleNamespace(
            rollout_order=["flash_arb", "funding_arb"],
            family_states={"flash_arb": "live", "funding_arb": "observe_only"},
        )
        self.calls = []

    def recommendation(self, **kwargs):
        self.calls.append(("recommendation", kwargs))
        return {
            "recommended_next_family": "funding_arb",
            "families": [{"family": "funding_arb", "ready": True, "status": "eligible"}],
            "profile": {"mode": "V1_ONLY"},
        }

    def set_mode(self, mode):
        self.calls.append(("set_mode", mode))
        return {"mode": mode}

    def enable_family(self, family, **kwargs):
        self.calls.append(("enable_family", family, kwargs))
        return {"ok": True, "profile": {"active_families": ["flash_arb", family]}}

    def pause_family(self, family):
        self.calls.append(("pause_family", family))
        return {"ok": True, "transition": {"family": family, "to_state": "observe_only"}}

    def revert_family(self, family):
        self.calls.append(("revert_family", family))
        return {"ok": True, "transition": {"family": family, "to_state": "capped_live"}}

    def quarantine_family(self, family, *, actor, reason_code):
        self.calls.append(("quarantine_family", family, actor, reason_code))
        return {"ok": True, "transition": {"family": family, "to_state": "quarantined"}}

    def family_detail(self, family, **kwargs):
        self.calls.append(("family_detail", family, kwargs))
        return {
            "ok": True,
            "family": family,
            "item": {"family": family},
            "profile": {"mode": "V1_ONLY"},
        }


class _Runtime:
    def __init__(self, *, paused: bool = False, rollout: _StubRollout | None = None):
        self._launch_rollout = rollout
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(paused=paused, allocations_frozen=False)
        )
        self._ledger = SimpleNamespace(
            tail=lambda limit=50: [],
            transactions_tail=lambda limit=50: [],
            balances=lambda: {"USD": 12.5},
        )
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 0.0})
        self._last_operator_pnl_summary = {"total_realized_profit_after_gas_usd": 12.5}
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
        return {
            "capital_engine": {
                "deployable_bankroll_wei": int(6e18),
                "reserve_bankroll_wei": int(2e18),
                "experimental_bankroll_wei": 0,
                "drawdown_buffer_wei": int(1e18),
                "treasury_offramp_wei": 0,
                "family_targets": {"flash_arb": 0.6, "funding_arb": 0.2},
                "family_allocations_wei": {"flash_arb": int(6e18)},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": int(1e18)},
            "reinvestment_policy": {"enabled": False},
        }


def test_launch_service_handles_missing_rollout():
    svc = LaunchService()
    rt = _Runtime(rollout=None)
    assert svc.summary(rt) == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "launch_rollout_unavailable",
        "reason": "launch_rollout_unavailable",
    }
    assert svc.set_mode(rt, "FULL_MULTI_STRATEGY") == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "launch_rollout_unavailable",
        "reason": "launch_rollout_unavailable",
    }


def test_launch_service_enable_next_returns_launch_context_when_guard_blocks():
    svc = LaunchService()
    rollout = _StubRollout()
    rt = _Runtime(paused=True, rollout=rollout)

    out = svc.enable_next(rt)

    assert out["ok"] is False
    assert out["reason_code"] == "command_center_paused"
    assert out["launch"]["recommended_next_family"] == "funding_arb"
    assert all(call[0] != "enable_family" for call in rollout.calls)


def test_launch_service_routes_mutations_and_detail_through_service_boundary():
    svc = LaunchService()
    rollout = _StubRollout()
    rt = _Runtime(rollout=rollout)

    mode = svc.set_mode(rt, "FULL_MULTI_STRATEGY")
    enabled = svc.enable_next(rt, "funding_arb")
    paused = svc.pause_family(rt, "funding_arb")
    reverted = svc.revert_family(rt, "funding_arb")
    quarantined = svc.quarantine_family(rt, "funding_arb", reason_code="operator_quarantine")
    detail = svc.family_detail(rt, "funding_arb")

    assert mode == {"ok": True, "profile": {"mode": "FULL_MULTI_STRATEGY"}}
    assert enabled["ok"] is True
    assert enabled["launch"]["recommended_next_family"] == "funding_arb"
    assert paused["transition"]["family"] == "funding_arb"
    assert reverted["transition"]["to_state"] == "capped_live"
    assert quarantined["transition"]["to_state"] == "quarantined"
    assert detail["item"]["family"] == "funding_arb"


class _HardeningService:
    def summary(self, runtime):
        return {"ok": True, "items": [{"family": "funding_arb"}]}

    def family_state(self, runtime, family):
        return {"family": family, "controls": {"no_trade": False}}


def test_launch_service_attaches_family_hardening_context():
    svc = LaunchService()
    rollout = _StubRollout()
    rt = _Runtime(rollout=rollout)
    rt._family_hardening_service = _HardeningService()

    summary = svc.summary(rt)
    mode = svc.set_mode(rt, "FULL_MULTI_STRATEGY")
    enabled = svc.enable_next(rt, "funding_arb")
    paused = svc.pause_family(rt, "funding_arb")
    reverted = svc.revert_family(rt, "funding_arb")
    quarantined = svc.quarantine_family(rt, "funding_arb", reason_code="operator_quarantine")
    blocked_runtime = _Runtime(paused=True, rollout=rollout)
    blocked_runtime._family_hardening_service = _HardeningService()
    blocked_mode = svc.set_mode(blocked_runtime, "FULL_MULTI_STRATEGY")
    blocked = svc.enable_next(blocked_runtime, "funding_arb")
    blocked_pause = svc.pause_family(blocked_runtime, "funding_arb")
    blocked_revert = svc.revert_family(blocked_runtime, "funding_arb")
    blocked_quarantine = svc.quarantine_family(
        blocked_runtime, "funding_arb", reason_code="operator_quarantine"
    )
    detail = svc.family_detail(rt, "funding_arb")

    assert summary["familyHardening"]["ok"] is True
    assert mode["familyHardening"]["ok"] is True
    assert enabled["hardening"]["family"] == "funding_arb"
    assert paused["hardening"]["family"] == "funding_arb"
    assert reverted["hardening"]["family"] == "funding_arb"
    assert quarantined["hardening"]["family"] == "funding_arb"
    assert blocked_mode["familyHardening"]["ok"] is True
    assert blocked["hardening"]["family"] == "funding_arb"
    assert blocked_pause["hardening"]["family"] == "funding_arb"
    assert blocked_revert["hardening"]["family"] == "funding_arb"
    assert blocked_quarantine["hardening"]["family"] == "funding_arb"
    assert detail["hardening"]["family"] == "funding_arb"


def test_launch_service_unavailable_family_actions_preserve_hardening_context():
    svc = LaunchService()
    rt = _Runtime(rollout=None)
    rt._family_hardening_service = _HardeningService()

    paused = svc.pause_family(rt, "funding_arb")
    reverted = svc.revert_family(rt, "funding_arb")
    quarantined = svc.quarantine_family(rt, "funding_arb", reason_code="operator_quarantine")
    detail = svc.family_detail(rt, "funding_arb")

    for out in (paused, reverted, quarantined, detail):
        assert out["status"] == "unavailable"
        assert out["reason_code"] == "launch_rollout_unavailable"
        assert out["hardening"]["family"] == "funding_arb"


class _BrokenHardeningService:
    def summary(self, runtime):
        raise RuntimeError("broken_summary")

    def family_state(self, runtime, family):
        raise RuntimeError("broken_family_state")


def test_launch_service_fail_closed_when_family_hardening_service_raises():
    svc = LaunchService()
    rollout = _StubRollout()
    rt = _Runtime(rollout=rollout)
    rt._family_hardening_service = _BrokenHardeningService()

    summary = svc.summary(rt)
    enabled = svc.enable_next(rt, "funding_arb")
    detail = svc.family_detail(rt, "funding_arb")

    assert summary["familyHardening"]["status"] == "unavailable"
    assert summary["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert summary["familyHardening"]["items"] == []
    assert summary["familyHardening"]["recovery_status"] == "family_hardening_restore_required"
    assert summary["familyHardening"]["recovery_reliability_class"] == "unavailable"
    assert summary["familyHardening"]["family_hardening_recovery_history_status"] == "degraded"

    assert enabled["hardening"]["status"] == "unavailable"
    assert enabled["hardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert enabled["hardening"]["family"] == "funding_arb"
    assert enabled["hardening"]["recovery_status"] == "family_hardening_restore_required"
    assert enabled["hardening"]["recovery_next_action"] == "restore_family_hardening"

    assert detail["hardening"]["status"] == "unavailable"
    assert detail["hardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert detail["hardening"]["family"] == "funding_arb"
    assert detail["hardening"]["recovery_reliability_reason_code"] == (
        "family_hardening_reliability_unavailable"
    )
