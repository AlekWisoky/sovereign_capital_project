from types import SimpleNamespace

from victor_ai_bot.arb_engine import build_edges


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(
            univ3_quoter_v2="",
            curve_pools=[],
            balancer_vault="",
            balancer_pools=[],
            aerodrome_router="",
            aerodrome_pools=[],
            slipstream_quoter_v2="",
            slipstream_pools=[],
            camelot_algebra_quoter_v2="0x0000000000000000000000000000000000000001",
            camelot_algebra_swap_router="0x0000000000000000000000000000000000000002",
            camelot_algebra_factory="0x0000000000000000000000000000000000000003",
            camelot_algebra_pools=[],
        ),
        flags=SimpleNamespace(enable_curve_autogen=True, enable_balancer_autogen=True),
    )


def test_build_edges_includes_discovered_camelot_reverse_pair():
    cfg = _cfg()
    pools = [{
        "pool": "0x00000000000000000000000000000000000000f2",
        "token_in": "0x0000000000000000000000000000000000000001",
        "token_out": "0x0000000000000000000000000000000000000002",
        "tick_spacing": 60,
        "factory": "0x0000000000000000000000000000000000000003",
    }]
    edges = build_edges(cfg, extra_camelot_algebra_pools=pools)
    assert len(edges) == 2
    assert {e.dex for e in edges} == {"camelot_algebra"}
    assert {(e.token_in, e.token_out) for e in edges} == {
        (pools[0]["token_in"], pools[0]["token_out"]),
        (pools[0]["token_out"], pools[0]["token_in"]),
    }
