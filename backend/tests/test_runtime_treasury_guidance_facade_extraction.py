from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.runtime_services.runtime_treasury_guidance_facade as guidance_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_treasury_guidance_facade import (
    RuntimeTreasuryGuidanceFacade,
)

EXTRACTED_METHODS = {
    "_treasury_bankroll_state",
    "_apply_treasury_guidance",
}


class _Treasury:
    def __init__(self, *, state=None, exc: Exception | None = None):
        self.state = (
            state
            if state is not None
            else {
                "borrow_mult_target_cap": 1.5,
                "aggressiveness": {"aggressiveness_level": "HIGH"},
            }
        )
        self.exc = exc
        self.calls = []

    def pre_select_strategy(self, *, bankroll_state, volatility_regime):
        self.calls.append(
            {"bankroll_state": dict(bankroll_state), "volatility_regime": volatility_regime}
        )
        if self.exc is not None:
            raise self.exc
        return dict(self.state)


class _Runtime(RuntimeTreasuryGuidanceFacade):
    def __init__(self):
        self._bankroll = SimpleNamespace(
            state=SimpleNamespace(
                realized_profit_wei=11,
                last_amount_in_wei=22,
                success_streak=3,
                fail_streak=4,
            )
        )
        self._treasury = _Treasury()
        self.overlay_calls = []

    def _behave_strategy_overlay(self, *, behave_state, treasury_state, opps, current_block):
        self.overlay_calls.append(
            {
                "behave_state": dict(behave_state or {}),
                "treasury_state": dict(treasury_state or {}),
                "opps": list(opps),
                "current_block": current_block,
            }
        )
        return {**(behave_state or {}), "overlay_ok": True}


def test_runtime_bundle_inherits_extracted_treasury_guidance_facade():
    assert issubclass(RuntimeBundle, RuntimeTreasuryGuidanceFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_treasury_guidance_facade_preserves_preselect_and_overlay(monkeypatch):
    runtime = _Runtime()
    updates = []
    monkeypatch.setattr(
        guidance_mod.BUS, "update", lambda key, value: updates.append((key, dict(value)))
    )

    result = runtime._apply_treasury_guidance(
        behave_state={"enabled": True},
        regime_label="risk_on",
        opps=[SimpleNamespace(route_id="a")],
        current_block=123,
    )

    assert runtime._treasury.calls == [
        {
            "bankroll_state": {
                "realized_profit_wei": 11,
                "last_amount_in_wei": 22,
                "success_streak": 3,
                "fail_streak": 4,
                "updated_ts_ms": 0,
                "profit_updated_ts_ms": 0,
                "sizing_updated_ts_ms": 0,
            },
            "volatility_regime": "risk_on",
        }
    ]
    assert updates == [
        (
            "treasury",
            {"borrow_mult_target_cap": 1.5, "aggressiveness": {"aggressiveness_level": "HIGH"}},
        )
    ]
    assert result["treasury_state"]["borrow_mult_target_cap"] == 1.5
    assert result["behave_state"]["overlay_ok"] is True
    assert runtime.overlay_calls[0]["current_block"] == 123


def test_runtime_treasury_guidance_facade_is_operator_safe_on_bad_state(monkeypatch):
    runtime = _Runtime()
    runtime._treasury = _Treasury(exc=TypeError("bad treasury state"))
    updates = []
    monkeypatch.setattr(
        guidance_mod.BUS, "update", lambda key, value: updates.append((key, dict(value)))
    )

    original = {"enabled": True}
    result = runtime._apply_treasury_guidance(
        behave_state=original,
        regime_label="balanced",
        opps=[SimpleNamespace(route_id="b")],
        current_block=55,
    )

    assert result == {"treasury_state": None, "behave_state": original}
    assert updates == []
    assert runtime.overlay_calls == []


def test_runtime_treasury_guidance_facade_noops_without_treasury(monkeypatch):
    runtime = _Runtime()
    runtime._treasury = None
    updates = []
    monkeypatch.setattr(
        guidance_mod.BUS, "update", lambda key, value: updates.append((key, dict(value)))
    )

    original = {"enabled": False}
    result = runtime._apply_treasury_guidance(
        behave_state=original,
        regime_label="unknown",
        opps=[],
        current_block=1,
    )

    assert result == {"treasury_state": None, "behave_state": original}
    assert updates == []
