from __future__ import annotations

from victor_ai_bot.sentry_config import init_sentry, sentry_settings, set_sentry_trade_context


def test_sentry_is_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_sentry_settings_use_release_and_safe_sampling(monkeypatch):
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SENTRY_RELEASE", "release-123")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.05")
    monkeypatch.setenv("SENTRY_PROFILES_SAMPLE_RATE", "0.01")
    monkeypatch.setenv("SENTRY_ENABLE_LOGS", "1")

    settings = sentry_settings()

    assert settings == {
        "environment": "production",
        "release": "release-123",
        "traces_sample_rate": 0.05,
        "profiles_sample_rate": 0.01,
        "enable_logs": True,
    }


def test_sentry_sampling_values_are_clamped(monkeypatch):
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "9")
    monkeypatch.setenv("SENTRY_PROFILES_SAMPLE_RATE", "-1")

    settings = sentry_settings()

    assert settings["traces_sample_rate"] == 1.0
    assert settings["profiles_sample_rate"] == 0.0


def test_trade_context_is_safe_without_sentry(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    set_sentry_trade_context(
        decision_id="decision-1",
        correlation_id="corr-1",
        execution_id="execution-1",
        outcome_id="outcome-1",
        opportunity_id="opp-1",
        route_id="route-1",
        sizing_id="sizing-1",
        action="EXECUTE",
        mode="auto",
    )
