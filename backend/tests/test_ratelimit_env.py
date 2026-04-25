from __future__ import annotations

from victor_ai_bot.ratelimit import _env_int


def test_env_int_accepts_valid_integer(monkeypatch):
    monkeypatch.setenv("VICTOR_RL_HEAVY_MAX", "17")
    assert _env_int("VICTOR_RL_HEAVY_MAX", 12) == 17


def test_env_int_falls_back_for_invalid_values(monkeypatch):
    monkeypatch.setenv("VICTOR_RL_HEAVY_MAX", "1.5")
    assert _env_int("VICTOR_RL_HEAVY_MAX", 12) == 12

    monkeypatch.setenv("VICTOR_RL_HEAVY_MAX", "")
    assert _env_int("VICTOR_RL_HEAVY_MAX", 12) == 12

    monkeypatch.setenv("VICTOR_RL_HEAVY_MAX", "bad")
    assert _env_int("VICTOR_RL_HEAVY_MAX", 12) == 12
