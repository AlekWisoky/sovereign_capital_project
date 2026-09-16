from types import SimpleNamespace

from victor_ai_bot.aqe.mev.router_context_producer import (
    decode_allowlisted_univ3_swap,
    produce_flash_arb_context_from_router,
)


ROUTER = "0x0000000000000000000000000000000000000010"
TOKEN_A = "0x0000000000000000000000000000000000000020"
TOKEN_B = "0x0000000000000000000000000000000000000030"
RECIPIENT = "0x0000000000000000000000000000000000000040"
PROFIT_TO = "0x0000000000000000000000000000000000000050"
VENUE_A = "0x0000000000000000000000000000000000000060"
VENUE_B = "0x0000000000000000000000000000000000000070"


def _word(value: int) -> str:
    return f"{int(value):064x}"


def _address_word(address: str) -> str:
    return address[2:].rjust(64, "0")


def _swap_tx(*, to: str = ROUTER, tx_hash: str = "0xabc") -> dict:
    payload = "".join(
        [
            _address_word(TOKEN_A),
            _address_word(TOKEN_B),
            _word(3000),
            _address_word(RECIPIENT),
            _word(9999999999),
            _word(1000),
            _word(950),
            _word(0),
        ]
    )
    return {
        "hash": tx_hash,
        "to": to,
        "input": "0x414bf389" + payload,
    }


def _base_opportunity():
    return SimpleNamespace(
        id="opp-1",
        strategy="two-leg:univ3->univ3",
        expected_profit_raw="25",
        route_id="route-1",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    dex="univ3",
                    venue=VENUE_A,
                    token_in=TOKEN_A,
                    token_out=TOKEN_B,
                    amount_in="1000",
                    min_out="950",
                    data="0x" + "00" * 32,
                ),
                SimpleNamespace(
                    dex="univ3",
                    venue=VENUE_B,
                    token_in=TOKEN_B,
                    token_out=TOKEN_A,
                    amount_in="950",
                    min_out="1005",
                    data="0x" + "00" * 32,
                ),
            ]
        ),
    )


def test_decode_allowlisted_univ3_exact_input_single():
    decoded = decode_allowlisted_univ3_swap(_swap_tx(), router=ROUTER)
    assert decoded is not None
    assert decoded["token_in"] == TOKEN_A
    assert decoded["token_out"] == TOKEN_B
    assert decoded["fee"] == 3000
    assert decoded["amount_in"] == 1000
    assert decoded["amount_out_minimum"] == 950


def test_decode_rejects_non_allowlisted_router_and_unknown_selector():
    assert decode_allowlisted_univ3_swap(_swap_tx(to=VENUE_A), router=ROUTER) is None
    tx = _swap_tx()
    tx["input"] = "0xdeadbeef" + tx["input"][10:]
    assert decode_allowlisted_univ3_swap(tx, router=ROUTER) is None


def test_context_uses_existing_two_leg_route_and_requires_explicit_simulation():
    kwargs = {
        "tx": _swap_tx(),
        "router": ROUTER,
        "base_opportunities": [_base_opportunity()],
        "provider": "aave",
        "profit_to": PROFIT_TO,
    }
    assert produce_flash_arb_context_from_router(**kwargs) is None

    context = produce_flash_arb_context_from_router(
        **kwargs,
        simulation_request={
            "fork_url": "https://example.invalid/rpc",
            "fork_block": 100,
            "transaction": {"to": "0x0000000000000000000000000000000000000090", "data": "0x"},
            "scenarios": [{
                "gas_multiplier": 1.0,
                "liquidity_multiplier": 1.0,
                "oracle_multiplier": 1.0,
                "economic_observation": {"account": PROFIT_TO, "assets": [{"address": "native", "decimals": 18, "price_usd": 1.0}]},
            }],
        },
    )
    assert context is not None
    assert context["strategy"] == "flash_arb"
    assert context["borrow_token"] == TOKEN_A
    assert context["amount_borrow"] == 1000
    assert context["expected_profit_raw"] == 25
    assert len(context["legs"]) == 2
    assert context["observed_router_call"]["fee"] == 3000
