from types import SimpleNamespace

from victor_ai_bot.quote_constant_product import _calldata, _parse
from victor_ai_bot.route_encoding import EncLeg, DEX_ID, route_id_hex
from victor_ai_bot.arb_engine import build_edges


def test_constant_product_quote_uses_canonical_get_amounts_out_abi():
    data = _calldata(
        "0x" + "01" * 20,
        "0x" + "02" * 20,
        123,
    )
    assert data.startswith("0x")
    assert len(data) > 10
    assert data[2:10] != "00000000"


def test_constant_product_quote_parser_reads_terminal_amount():
    raw = (
        b"\x00" * 32
        + (64).to_bytes(32, "big")
        + (2).to_bytes(32, "big")
        + (123).to_bytes(32, "big")
        + (456).to_bytes(32, "big")
    )
    q = _parse("0x" + raw.hex())
    assert q is not None
    assert q.amount_out == 456


def test_constant_product_edges_preserve_venue_and_pool_identity():
    router = "0x" + "aa" * 20
    pool = "0x" + "bb" * 20
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            univ3_quoter_v2="",
            v3_pairs=[],
            curve_pools=[],
            balancer_vault="",
            balancer_pools=[],
            aerodrome_router="",
            aerodrome_pools=[],
            slipstream_quoter_v2="",
            slipstream_pools=[],
            camelot_algebra_quoter_v2="",
            camelot_algebra_pools=[],
            camelot_v2_router="",
            camelot_v2_pools=[],
            constant_product_venues=[{"name": "uniswap_v2", "router": router}],
            constant_product_pools=[{
                "venue_name": "uniswap_v2",
                "router": router,
                "factory": "0x" + "cc" * 20,
                "pool": pool,
                "token_in": "0x" + "01" * 20,
                "token_out": "0x" + "02" * 20,
            }],
        ),
        flags=SimpleNamespace(enable_curve_autogen=False, enable_balancer_autogen=False),
    )
    edges = build_edges(cfg)
    assert len(edges) == 2
    assert {e.dex for e in edges} == {"constant_product"}
    assert {e.params["pool"] for e in edges} == {pool}


def test_constant_product_has_distinct_route_encoding_id():
    legs = [
        EncLeg(
            dex="constant_product",
            venue="0x" + "aa" * 20,
            token_in="0x" + "01" * 20,
            token_out="0x" + "02" * 20,
            aux="0x" + "00" * 12 + "cc" * 20,
        )
    ]
    assert DEX_ID["constant_product"] == 8
    assert route_id_hex(legs).startswith("0x")
