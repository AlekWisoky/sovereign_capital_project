from __future__ import annotations

from victor_ai_bot.anomaly_breakers import gas_spike_detected, AnomalyBreaker
from victor_ai_bot.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


def test_gas_spike_detected_basic() -> None:
    hist = [10.0, 12.0, 11.0, 13.0]
    assert gas_spike_detected(history_gwei=hist, current_gwei=50.0, mult=2.5, min_abs_gwei=40.0) is True
    assert gas_spike_detected(history_gwei=hist, current_gwei=20.0, mult=2.5, min_abs_gwei=40.0) is False


def test_anomaly_breaker_rpc_error_streak() -> None:
    b = AnomalyBreaker(window=20)
    # 4 errors: not tripped yet
    tripped = False
    for _ in range(4):
        tripped = b.observe_rpc_error(ok=False, threshold=5)
    assert tripped is False
    # 5th error trips
    assert b.observe_rpc_error(ok=False, threshold=5) is True
    # success resets
    assert b.observe_rpc_error(ok=True, threshold=5) is False
    assert b.state.rpc_error_streak == 0


def test_circuit_breaker_trips_on_failures() -> None:
    cb = CircuitBreaker(CircuitBreakerConfig(max_consecutive_failures=3, max_consecutive_reverts=2, cooldown_s=1))
    cb.record_result(ok=False, reason="simulation_revert")
    assert cb.is_tripped() is False
    cb.record_result(ok=False, reason="simulation_revert")
    assert cb.is_tripped() is True  # revert streak reached


def test_circuit_breaker_from_env_invalid_values_fall_back_to_defaults(monkeypatch) -> None:
    monkeypatch.setenv("VICTOR_CB_MAX_FAILURES", "bad")
    monkeypatch.setenv("VICTOR_CB_MAX_REVERTS", "")
    monkeypatch.setenv("VICTOR_CB_COOLDOWN_S", "1.5")

    cb = CircuitBreaker.from_env()

    assert cb.cfg.max_consecutive_failures == 5
    assert cb.cfg.max_consecutive_reverts == 3
    assert cb.cfg.cooldown_s == 60


def test_circuit_breaker_from_env_accepts_valid_integer_values(monkeypatch) -> None:
    monkeypatch.setenv("VICTOR_CB_MAX_FAILURES", "7")
    monkeypatch.setenv("VICTOR_CB_MAX_REVERTS", "4")
    monkeypatch.setenv("VICTOR_CB_COOLDOWN_S", "15")

    cb = CircuitBreaker.from_env()

    assert cb.cfg.max_consecutive_failures == 7
    assert cb.cfg.max_consecutive_reverts == 4
    assert cb.cfg.cooldown_s == 15
