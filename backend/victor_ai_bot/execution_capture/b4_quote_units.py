from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any, Mapping


class QuoteUnitSizingError(ValueError):
    """Raised when a final quote cannot safely produce raw asset units."""


def _decimal(value: Any, error: str = "quote_value_invalid") -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteUnitSizingError(error) from exc
    if not number.is_finite():
        raise QuoteUnitSizingError("quote_value_non_finite")
    return number


def _decimals(value: Any) -> int:
    decimals = _decimal(value, "asset_decimals_invalid")
    if decimals != decimals.to_integral_value() or not 0 <= decimals <= 255:
        raise QuoteUnitSizingError("asset_decimals_invalid")
    return int(decimals)


def _positive_decimal(value: Any, error: str) -> Decimal:
    number = _decimal(value)
    if number <= 0:
        raise QuoteUnitSizingError(error)
    return number


def _nonnegative_decimal(value: Any, error: str) -> Decimal:
    number = _decimal(value)
    if number < 0:
        raise QuoteUnitSizingError(error)
    return number


def _raw_units(notional: Decimal, price: Decimal, decimals: int) -> int:
    units = ((notional / price) * (Decimal(10) ** decimals)).to_integral_value(
        rounding=ROUND_FLOOR
    )
    if units < 0:
        raise QuoteUnitSizingError("raw_units_negative")
    return int(units)


def usd_notional_to_raw_units(
    usd_notional: float | int | str,
    *,
    asset_price_usd: float | int | str,
    asset_decimals: int,
) -> int:
    """Convert a final quoted USD notional to conservative raw asset units.

    This is a pure quote-bound conversion. It neither fetches prices nor grants
    execution authority. Flooring ensures the raw amount cannot exceed the
    approved economic notional at the supplied quote.
    """
    decimals = _decimals(asset_decimals)
    notional = _nonnegative_decimal(usd_notional, "usd_notional_negative")
    price = _positive_decimal(asset_price_usd, "asset_price_usd_invalid")
    return _raw_units(notional, price, decimals)


def raw_units_to_usd_notional(
    raw_units: int,
    *,
    asset_price_usd: float | int | str,
    asset_decimals: int,
) -> float:
    """Convert final raw units back to quoted USD economic value."""
    decimals = _decimals(asset_decimals)
    try:
        units = int(raw_units)
    except (TypeError, ValueError) as exc:
        raise QuoteUnitSizingError("raw_units_invalid") from exc
    if units < 0:
        raise QuoteUnitSizingError("raw_units_negative")
    price = _positive_decimal(asset_price_usd, "asset_price_usd_invalid")
    value = (Decimal(units) * price) / (Decimal(10) ** decimals)
    if value < 0:
        raise QuoteUnitSizingError("quoted_usd_value_invalid")
    return float(value)


def quote_context_from_mapping(quote: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize final-quote fields without inventing missing values."""
    if not isinstance(quote, Mapping):
        return {}
    return {
        "quote_id": str(quote.get("quote_id") or quote.get("quoteId") or ""),
        "asset_price_usd": quote.get("asset_price_usd", quote.get("assetPriceUsd")),
        "asset_decimals": quote.get("asset_decimals", quote.get("assetDecimals")),
        "quoted_at_ms": quote.get("quoted_at_ms", quote.get("quotedAtMs")),
        "block_number": quote.get("block_number", quote.get("blockNumber")),
    }


def _quote_price_error(price: Any) -> str | None:
    if price is None:
        return "asset_price_usd_missing"
    try:
        number = float(price)
    except (TypeError, ValueError):
        return "asset_price_usd_invalid"
    if number <= 0 or not __import__("math").isfinite(number):
        return "asset_price_usd_invalid"
    return None


def _quote_decimals_error(decimals: Any) -> str | None:
    if decimals is None:
        return "asset_decimals_missing"
    try:
        value = int(decimals)
    except (TypeError, ValueError):
        return "asset_decimals_invalid"
    return None if 0 <= value <= 255 else "asset_decimals_invalid"


def validate_quote_context(quote: Mapping[str, Any] | None) -> tuple[bool, tuple[str, ...]]:
    """Validate the minimum quote contract required for raw-unit conversion."""
    normalized = quote_context_from_mapping(quote)
    errors = tuple(
        error
        for error in (
            _quote_price_error(normalized.get("asset_price_usd")),
            _quote_decimals_error(normalized.get("asset_decimals")),
        )
        if error is not None
    )
    return (not errors, errors)
