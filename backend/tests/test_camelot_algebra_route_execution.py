from victor_ai_bot.route_encoding import EncLeg, route_id_hex


def test_camelot_algebra_route_id_is_deterministic_and_distinct():
    legs = [
        EncLeg(
            dex="camelot_algebra",
            venue="0x0000000000000000000000000000000000000003",
            token_in="0x0000000000000000000000000000000000000001",
            token_out="0x0000000000000000000000000000000000000002",
        )
    ]
    rid = route_id_hex(legs)
    assert rid.startswith("0x") and len(rid) == 66
