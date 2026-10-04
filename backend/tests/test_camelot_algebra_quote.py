from victor_ai_bot.quote_camelot_algebra import _calldata, _parse


def test_camelot_algebra_quote_calldata_uses_struct_signature():
    data = _calldata(
        "0x0000000000000000000000000000000000000001",
        "0x0000000000000000000000000000000000000002",
        123,
    )
    assert data.startswith("0x")
    assert len(data) == 10 + 64 * 4


def test_camelot_algebra_quote_parses_dynamic_fee_and_gas():
    raw = (
        (456).to_bytes(32, "big")
        + (17).to_bytes(32, "big")
        + (999).to_bytes(32, "big")
        + (123456).to_bytes(32, "big")
    )
    q = _parse("0x" + raw.hex())
    assert q is not None
    assert q.amount_out == 456
    assert q.fee == 17
    assert q.gas_estimate == 123456
