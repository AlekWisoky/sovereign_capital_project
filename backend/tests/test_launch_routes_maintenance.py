from __future__ import annotations

from victor_ai_bot.api_routes.launch_routes import (
    enable_next,
    pause_family,
    quarantine_family,
    revert_family,
    set_launch_mode,
)


class _LaunchService:
    def __init__(self):
        self.calls = []

    def set_mode(self, runtime, mode: str):
        self.calls.append(("set_mode", mode))
        return {"ok": True, "profile": {"mode": mode}}

    def enable_next(self, runtime, family: str):
        self.calls.append(("enable_next", family))
        return {"ok": True, "family": family or "recommended"}

    def pause_family(self, runtime, family: str):
        self.calls.append(("pause_family", family))
        return {"ok": True, "family": family}

    def revert_family(self, runtime, family: str):
        self.calls.append(("revert_family", family))
        return {"ok": True, "family": family}

    def quarantine_family(self, runtime, family: str, *, reason_code: str):
        self.calls.append(("quarantine_family", family, reason_code))
        return {"ok": True, "family": family, "reason_code": reason_code}


class _Runtime:
    def __init__(self):
        self._launch_service = _LaunchService()


class _UnavailableRuntime:
    _launch_service = None

    def family_hardening_state(self):
        return {"ok": True, "items": [{"family": "funding_arb"}]}


def test_launch_mode_requires_explicit_valid_mode_and_preserves_unavailable_context():
    rt = _Runtime()

    missing = set_launch_mode(body={}, rt=rt)
    blank = set_launch_mode(body={"mode": "   "}, rt=rt)
    invalid = set_launch_mode(body={"mode": "INVALID"}, rt=rt)
    unknown = set_launch_mode(body={"mode": "V1_ONLY", "extra": True}, rt=rt)
    valid = set_launch_mode(body={"mode": "FULL_MULTI_STRATEGY"}, rt=rt)

    assert missing["reason_code"] == "missing_mode"
    assert blank["reason_code"] == "invalid_string_value"
    assert invalid["reason_code"] == "invalid_launch_mode"
    assert set(invalid["details"]["allowed_modes"]) == {
        "FULL_MULTI_STRATEGY",
        "STAGED_MULTI_STRATEGY",
        "V1_ONLY",
        "V1_PLUS_STABLE_ALPHA",
    }
    assert unknown["reason_code"] == "unknown_request_fields"
    assert valid == {"ok": True, "profile": {"mode": "FULL_MULTI_STRATEGY"}}
    assert rt._launch_service.calls == [("set_mode", "FULL_MULTI_STRATEGY")]

    unavailable = set_launch_mode(body={"mode": "FULL_MULTI_STRATEGY"}, rt=_UnavailableRuntime())
    assert unavailable["reason_code"] == "launch_service_unavailable"
    assert unavailable["familyHardening"]["ok"] is True


def test_launch_family_mutations_require_explicit_non_empty_family():
    rt = _Runtime()

    missing_pause = pause_family(body={}, rt=rt)
    blank_revert = revert_family(body={"family": "  "}, rt=rt)
    unknown_pause = pause_family(body={"family": "funding_arb", "extra": True}, rt=rt)
    paused = pause_family(body={"family": "funding_arb"}, rt=rt)
    reverted = revert_family(body={"family": "funding_arb"}, rt=rt)
    quarantined = quarantine_family(
        body={"family": "funding_arb", "reason_code": "operator_quarantine"}, rt=rt
    )

    assert missing_pause["reason_code"] == "missing_family"
    assert blank_revert["reason_code"] == "invalid_string_value"
    assert unknown_pause["reason_code"] == "unknown_request_fields"
    assert paused == {"ok": True, "family": "funding_arb"}
    assert reverted == {"ok": True, "family": "funding_arb"}
    assert quarantined == {
        "ok": True,
        "family": "funding_arb",
        "reason_code": "operator_quarantine",
    }
    assert rt._launch_service.calls == [
        ("pause_family", "funding_arb"),
        ("revert_family", "funding_arb"),
        ("quarantine_family", "funding_arb", "operator_quarantine"),
    ]


def test_enable_next_preserves_recommended_family_behavior_but_rejects_explicit_blank_family():
    rt = _Runtime()

    missing = enable_next(body={}, rt=rt)
    blank = enable_next(body={"family": "   "}, rt=rt)
    unknown = enable_next(body={"extra": True}, rt=rt)
    explicit = enable_next(body={"family": "funding_arb"}, rt=rt)

    assert missing == {"ok": True, "family": "recommended"}
    assert blank["reason_code"] == "invalid_string_value"
    assert unknown["reason_code"] == "unknown_request_fields"
    assert explicit == {"ok": True, "family": "funding_arb"}
    assert rt._launch_service.calls == [
        ("enable_next", ""),
        ("enable_next", "funding_arb"),
    ]


def test_quarantine_rejects_blank_reason_code_and_preserves_unavailable_family_context():
    rt = _Runtime()

    blank_reason = quarantine_family(body={"family": "funding_arb", "reason_code": "   "}, rt=rt)
    unknown = quarantine_family(body={"family": "funding_arb", "reason_code": "operator", "extra": 1}, rt=rt)
    unavailable = quarantine_family(body={"family": "funding_arb"}, rt=_UnavailableRuntime())

    assert blank_reason["reason_code"] == "invalid_string_value"
    assert unknown["reason_code"] == "unknown_request_fields"
    assert unavailable["reason_code"] == "launch_service_unavailable"
    assert unavailable["hardening"]["family"] == "funding_arb"
