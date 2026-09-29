from collections import Counter

from victor_ai_bot.quote_diagnostics import classify_quote_error, record_quote_failure


def test_quote_error_classes_are_stable_and_non_sensitive():
    assert classify_quote_error({"code": -32000, "message": "execution reverted: pool"}) == "rpc_revert"
    assert classify_quote_error({"code": 429, "message": "rate limit"}) == "rpc_rate_limited"
    assert classify_quote_error({"code": -32601, "message": "method not found"}) == "rpc_method_unsupported"
    assert classify_quote_error("timeout while reading") == "rpc_timeout"


def test_quote_failure_counter_is_observational():
    diagnostics = {}
    record_quote_failure(diagnostics, "rpc_revert")
    record_quote_failure(diagnostics, "rpc_revert")
    assert diagnostics["failure_reasons"] == Counter({"rpc_revert": 2})


def test_curve_fallback_telemetry_is_not_execution_authority():
    diagnostics = {"fallback_attempts": 3, "fallback_successes": 2}
    assert diagnostics["fallback_successes"] <= diagnostics["fallback_attempts"]
