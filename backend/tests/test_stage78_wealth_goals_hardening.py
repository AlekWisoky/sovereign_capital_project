from __future__ import annotations

import pytest

from victor_ai_bot.wealth_goals import clamp_float, clamp_int, normalize_goal_payload, recommend_goal


class BadFloatType:
    def __float__(self):
        raise TypeError("bad float")


class ExplodingFloat:
    def __float__(self):
        raise RuntimeError("boom")


class BadIntType:
    def __int__(self):
        raise ValueError("bad int")


class ExplodingInt:
    def __int__(self):
        raise RuntimeError("boom")


def test_clamp_helpers_degrade_safely_for_expected_coercion_failures() -> None:
    assert clamp_float(BadFloatType(), 0.5, 100.0, 8.0) == 8.0
    assert clamp_int(BadIntType(), 1, 365, 30) == 30


def test_clamp_helpers_do_not_swallow_unexpected_bugs() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        clamp_float(ExplodingFloat(), 0.5, 100.0, 8.0)
    with pytest.raises(RuntimeError, match="boom"):
        clamp_int(ExplodingInt(), 1, 365, 30)


def test_normalize_goal_payload_preserves_conservative_fallbacks() -> None:
    payload = {
        "risk_tolerance": "wildly-unsafe",
        "timeframe_days": BadIntType(),
        "target_return_pct": BadFloatType(),
        "max_drawdown_pct": BadFloatType(),
        "capital_commitment_pct": BadFloatType(),
    }
    norm = normalize_goal_payload(payload)
    assert norm["risk_tolerance"] == "moderate"
    assert norm["timeframe_days"] == 30
    assert norm["target_return_pct"] == 8.0
    assert norm["max_drawdown_pct"] == 10.0
    assert norm["capital_commitment_pct"] == 25.0


def test_recommend_goal_still_returns_canonical_shape() -> None:
    rec = recommend_goal(current_return_pct=12.5, risk_tolerance="moderate", previous_target_pct=10.0)
    assert rec["risk_tolerance"] == "moderate"
    assert rec["target_return_pct"] >= 12.0
    assert rec["timeframe_days"] == 21
    assert rec["time_horizon_seconds"] == rec["timeframe_days"] * 86400
