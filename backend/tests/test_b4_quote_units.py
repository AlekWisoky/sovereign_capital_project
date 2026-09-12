from __future__ import annotations

import pytest

from victor_ai_bot.execution_capture.b4_quote_units import (
    QuoteUnitSizingError,
    usd_notional_to_raw_units,
    validate_quote_context,
)


def test_usd_notional_to_raw_units_uses_final_quote_and_floors():
    raw = usd_notional_to_raw_units(
        250_000,
        asset_price_usd="2500.00",
        asset_decimals=18,
    )
    assert raw == 100_000_000_000_000_000_000


def test_conversion_never_rounds_above_approved_notional():
    raw = usd_notional_to_raw_units(
        "100.01",
        asset_price_usd="3.00",
        asset_decimals=2,
    )
    assert raw == 3333
    assert raw * 3 <= 100.01 * 100


@pytest.mark.parametrize(
    ("usd_notional", "asset_price_usd", "asset_decimals", "error"),
    [
        ("100", "0", 18, "asset_price_usd_invalid"),
        ("100", "-1", 18, "asset_price_usd_invalid"),
        ("100", "2500", -1, "asset_decimals_invalid"),
        ("100", "2500", 256, "asset_decimals_invalid"),
        ("-1", "2500", 18, "usd_notional_negative"),
        ("nan", "2500", 18, "quote_value_non_finite"),
    ],
)
def test_conversion_fails_closed_on_invalid_quote(
    usd_notional, asset_price_usd, asset_decimals, error
):
    with pytest.raises(QuoteUnitSizingError, match=error):
        usd_notional_to_raw_units(
            usd_notional,
            asset_price_usd=asset_price_usd,
            asset_decimals=asset_decimals,
        )


def test_quote_context_requires_price_and_decimals():
    valid, errors = validate_quote_context(
        {"quote_id": "q1", "asset_price_usd": 2500, "asset_decimals": 18}
    )
    assert valid is True
    assert errors == ()

    valid, errors = validate_quote_context({"quote_id": "q2"})
    assert valid is False
    assert errors == ("asset_price_usd_missing", "asset_decimals_missing")


def test_quote_context_accepts_camel_case_runtime_fields():
    valid, errors = validate_quote_context(
        {"quoteId": "q3", "assetPriceUsd": "2500", "assetDecimals": "18"}
    )
    assert valid is True
    assert errors == ()
