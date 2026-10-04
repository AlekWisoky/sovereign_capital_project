from types import SimpleNamespace

import pytest

from victor_ai_bot.quote_slipstream import _calldata, _parse, quote_slipstream


def test_slipstream_calldata_uses_int24_tick_spacing():
    data = _calldata(
        "0x" + "11" * 20,
        "0x" + "22" * 20,
        100,
        123,
    )
    assert data.startswith("0x")
    assert len(data) > 10
    # selector + five ABI words
    assert len(bytes.fromhex(data[2:])) == 4 + 32 * 5


def test_slipstream_parse_requires_four_return_words():
    assert _parse("0x" + "00" * 96, 100) is None
    raw = b"".join([
        (123).to_bytes(32, "big"),
        (1).to_bytes(32, "big"),
        (0).to_bytes(32, "big"),
        (55_000).to_bytes(32, "big"),
    ])
    q = _parse("0x" + raw.hex(), 100)
    assert q is not None
    assert q.amount_out == 123
    assert q.gas_estimate == 55_000
    assert q.tick_spacing == 100
