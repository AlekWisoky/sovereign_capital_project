from __future__ import annotations

from victor_ai_bot.api_routes.launch_routes import (
    enable_next,
    family_detail,
    launch_state,
    pause_family,
    quarantine_family,
    revert_family,
    set_launch_mode,
)


class _Runtime:
    _launch_service = None

    def family_hardening_state(self):
        return {
            "ok": True,
            "items": [
                {
                    "family": "funding_arb",
                    "controls": {"no_trade_reason_codes": ["family_cap_zero"]},
                }
            ],
        }


def test_launch_routes_preserve_hardening_context_when_launch_service_is_unavailable():
    rt = _Runtime()

    state = launch_state(rt=rt)
    mode = set_launch_mode(body={"mode": "FULL_MULTI_STRATEGY"}, rt=rt)
    enabled = enable_next(body={"family": "funding_arb"}, rt=rt)
    paused = pause_family(body={"family": "funding_arb"}, rt=rt)
    reverted = revert_family(body={"family": "funding_arb"}, rt=rt)
    quarantined = quarantine_family(
        body={"family": "funding_arb", "reason_code": "operator_quarantine"}, rt=rt
    )
    detail = family_detail("funding_arb", rt=rt)

    assert state["status"] == "unavailable"
    assert state["reason_code"] == "launch_service_unavailable"
    assert state["familyHardening"]["ok"] is True

    assert mode["status"] == "unavailable"
    assert mode["reason_code"] == "launch_service_unavailable"
    assert mode["familyHardening"]["ok"] is True

    for out in (paused, reverted, quarantined, detail):
        assert out["status"] == "unavailable"
        assert out["reason_code"] == "launch_service_unavailable"
        assert out["hardening"]["family"] == "funding_arb"

    assert enabled["status"] == "unavailable"
    assert enabled["reason_code"] == "launch_service_unavailable"
    assert enabled["familyHardening"]["ok"] is True


class _BrokenRuntime:
    _launch_service = None

    def family_hardening_state(self):
        raise RuntimeError("broken_hardening")


def test_launch_routes_fail_closed_when_family_hardening_state_raises():
    rt = _BrokenRuntime()

    state = launch_state(rt=rt)
    detail = family_detail("funding_arb", rt=rt)

    assert state["status"] == "unavailable"
    assert state["reason_code"] == "launch_service_unavailable"
    assert state["familyHardening"]["status"] == "unavailable"
    assert state["familyHardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert state["familyHardening"]["items"] == []
    assert state["familyHardening"]["recovery_status"] == "family_hardening_restore_required"
    assert state["familyHardening"]["recovery_reliability_class"] == "unavailable"
    assert state["familyHardening"]["family_hardening_recovery_history_status"] == "degraded"

    assert detail["status"] == "unavailable"
    assert detail["reason_code"] == "launch_service_unavailable"
    assert detail["hardening"]["status"] == "unavailable"
    assert detail["hardening"]["reason_code"] == "family_hardening_service_unavailable"
    assert detail["hardening"]["family"] == "funding_arb"
    assert detail["hardening"]["recovery_next_action"] == "restore_family_hardening"
