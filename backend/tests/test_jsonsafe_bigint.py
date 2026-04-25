from victor_ai_bot.jsonsafe import to_json_safe

def test_bigint_hint_keys_stringify_even_small_ints():
    o = {
        "amount_in": 1,
        "reserve0": 2,
        "profit_wei": 3,
        "gas_cost": 4,
        "fee": 5,
        "min_out": 6,
        "latency_ms": 7,  # should remain int (not bigint field)
    }
    j = to_json_safe(o)
    assert j["amount_in"] == "1"
    assert j["reserve0"] == "2"
    assert j["profit_wei"] == "3"
    assert j["gas_cost"] == "4"
    assert j["fee"] == "5"
    assert j["min_out"] == "6"
    assert j["latency_ms"] == 7

def test_js_safe_threshold_stringify():
    big = 2**53 + 123
    j = to_json_safe({"x": big})
    assert j["x"] == str(big)
