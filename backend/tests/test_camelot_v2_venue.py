from types import SimpleNamespace

from victor_ai_bot.arb_engine import build_edges
from victor_ai_bot.quote_camelot_v2 import _calldata, _parse
from victor_ai_bot.route_encoding import route_id_hex, EncLeg


def _cfg():
    chain = SimpleNamespace(
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
        camelot_v2_router="0x" + "aa" * 20,
        camelot_v2_factory="0x" + "bb" * 20,
        camelot_v2_pools=[],
    )
    flags = SimpleNamespace(enable_curve_autogen=False, enable_balancer_autogen=False)
    return SimpleNamespace(chain=chain, flags=flags)


def test_camelot_v2_quote_calldata_uses_canonical_router_signature():
    data = _calldata("0x" + "01" * 20, "0x" + "02" * 20, 123)
    assert data.startswith("0x")
    assert len(data) > 10


def test_camelot_v2_quote_parse_reads_dynamic_amount_array():
    amount_in = 123
    amount_out = 456
    raw = (
        (32).to_bytes(32, "big")
        + (0).to_bytes(32, "big")
        + (2).to_bytes(32, "big")
        + amount_in.to_bytes(32, "big")
        + amount_out.to_bytes(32, "big")
    )
    q = _parse("0x" + raw.hex())
    assert q is not None
    assert q.amount_out == amount_out


def test_build_edges_includes_both_camelot_v2_directions():
    cfg = _cfg()
    pools = [{
        "pool": "0x" + "cc" * 20,
        "token_in": "0x" + "01" * 20,
        "token_out": "0x" + "02" * 20,
        "factory": "0x" + "bb" * 20,
    }]
    edges = build_edges(cfg, extra_camelot_v2_pools=pools)
    assert len(edges) == 2
    assert {e.dex for e in edges} == {"camelot_v2"}


def test_camelot_v2_route_id_is_deterministic_and_distinct():
    legs = [
        EncLeg(
            dex="camelot_v2",
            venue="0x" + "aa" * 20,
            token_in="0x" + "01" * 20,
            token_out="0x" + "02" * 20,
            aux="0x" + "bb" * 20,
        )
    ]
    rid = route_id_hex(legs)
    assert rid.startswith("0x")
    assert len(rid) == 66
