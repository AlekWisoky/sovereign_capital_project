from types import SimpleNamespace

from victor_ai_bot.route_encoding import EncLeg, route_id_hex
from victor_ai_bot.calldata_builder import build_execute_calldata


def test_slipstream_route_id_and_calldata_are_canonical():
    token0 = "0x" + "11" * 20
    token1 = "0x" + "22" * 20
    router = "0x" + "33" * 20
    legs = [{
        "dex": "slipstream",
        "venue": router,
        "token_in": token0,
        "token_out": token1,
        "min_out": 1000,
        "aux": "0x" + (100).to_bytes(32, "big").hex(),
    }]
    calldata, rid = build_execute_calldata(
        provider="aave",
        borrow_token=token0,
        amount_borrow=1000,
        min_profit=1,
        profit_to=token0,
        deadline=2_000_000_000,
        legs=legs,
    )
    assert calldata.startswith("0x")
    assert rid == route_id_hex([EncLeg("slipstream", router, token0, token1, legs[0]["aux"])])
    assert len(calldata) > 10
