
from victor_ai_bot.ethabi import selector

def test_balanceof_selector():
    # keccak("balanceOf(address)")[:4] = 0x70a08231
    assert selector("balanceOf(address)").hex() == "70a08231"
