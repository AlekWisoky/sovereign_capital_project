
from victor_ai_bot.jsonsafe import to_json_safe

def test_bigint_stringify():
    x = {"amountWei": 2**60, "ok": 1}
    y = to_json_safe(x)
    assert y["amountWei"] == str(2**60)
    assert y["ok"] == 1

def test_hint_stringify():
    x = {"gas": 12345}
    y = to_json_safe(x)
    assert y["gas"] == "12345"
