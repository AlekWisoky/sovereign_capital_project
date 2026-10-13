from types import SimpleNamespace

from victor_ai_bot.quote_constant_product import _calldata, _parse
from victor_ai_bot.route_encoding import EncLeg, DEX_ID, route_id_hex
from victor_ai_bot.arb_engine import build_edges, _route_universe_snapshot


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
        (32).to_bytes(32, "big")
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



def test_route_universe_reports_uniswap_v2_and_sushiswap_v2_separately():
    token_a = "0x" + "01" * 20
    token_b = "0x" + "02" * 20
    uni_router = "0x" + "aa" * 20
    sushi_router = "0x" + "bb" * 20
    uni_factory = "0x" + "cc" * 20
    sushi_factory = "0x" + "dd" * 20
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            token_universe=[token_a, token_b],
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
            constant_product_venues=[
                {"name": "uniswap_v2", "router": uni_router},
                {"name": "sushiswap_v2", "router": sushi_router},
            ],
            constant_product_pools=[
                {"venue_name": "uniswap_v2", "router": uni_router,
                 "factory": uni_factory, "pool": "0x" + "11" * 20,
                 "token_in": token_a, "token_out": token_b},
                {"venue_name": "sushiswap_v2", "router": sushi_router,
                 "factory": sushi_factory, "pool": "0x" + "22" * 20,
                 "token_in": token_a, "token_out": token_b},
            ],
        ),
        flags=SimpleNamespace(enable_curve_autogen=False, enable_balancer_autogen=False),
    )

    snapshot = _route_universe_snapshot(cfg, build_edges(cfg))

    assert snapshot["edges_by_dex"]["constant_product"] == 4
    assert snapshot["edges_by_family"]["uniswap_v2"] == 2
    assert snapshot["edges_by_family"]["sushiswap_v2"] == 2



def test_balancer_edge_builder_diagnostics_identify_missing_vault_gate():
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
            constant_product_venues=[],
            constant_product_pools=[],
        ),
        flags=SimpleNamespace(enable_curve_autogen=True, enable_balancer_autogen=True),
    )
    diagnostics = {}
    discovered = [{
        "pool_id": "0x" + "ab" * 32,
        "token_in": "0x" + "01" * 20,
        "token_out": "0x" + "02" * 20,
        "pool": "0x" + "03" * 20,
    }]

    edges = build_edges(cfg, extra_balancer_pools=discovered, diagnostics=diagnostics)

    assert edges == []
    assert diagnostics["input_pool_counts_by_family"]["balancer"] == 1
    assert diagnostics["blocked_by_configuration"]["balancer"] == "balancer_vault_missing"
    assert diagnostics["family_prerequisites"]["balancer"]["feature_enabled"] is True
    assert diagnostics["family_prerequisites"]["balancer"]["vault_configured"] is False


def test_constant_product_edge_builder_diagnostics_identify_configured_venue_mismatch():
    configured_router = "0x" + "aa" * 20
    discovered_router = "0x" + "bb" * 20
    cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            token_universe=[],
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
            constant_product_venues=[{"name": "uniswap_v2", "router": configured_router}],
            constant_product_pools=[],
        ),
        flags=SimpleNamespace(enable_curve_autogen=False, enable_balancer_autogen=False),
    )
    discovered = [{
        "venue_name": "uniswap_v2",
        "router": discovered_router,
        "factory": "0x" + "cc" * 20,
        "pool": "0x" + "dd" * 20,
        "token_in": "0x" + "01" * 20,
        "token_out": "0x" + "02" * 20,
    }]
    diagnostics = {}

    edges = build_edges(
        cfg, extra_constant_product_pools=discovered, diagnostics=diagnostics
    )

    assert edges == []
    assert diagnostics["input_pool_counts_by_family"]["constant_product"] == 1
    assert diagnostics["pool_validation_rejections_by_family"]["constant_product"] == {
        "venue_not_configured": 1
    }
