from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import math
from typing import Any, Mapping


class QuoteUnitSizingError(ValueError):
    """Raised when a final quote cannot safely produce raw asset units."""


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise QuoteUnitSizingError("quote_value_invalid") from exc
    if not number.is_finite():
        raise QuoteUnitSizingError("quote_value_non_finite")
    return number


def _decimals(value: Any) -> int:
    try:
        decimals = int(value)
    except (TypeError, ValueError) as exc:
        raise QuoteUnitSizingError("asset_decimals_invalid") from exc
    if decimals < 0 or decimals > 255:
        raise QuoteUnitSizingError("asset_decimals_invalid")
    return decimals


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
    notional = _decimal(usd_notional)
    price = _decimal(asset_price_usd)
    if notional < 0:
        raise QuoteUnitSizingError("usd_notional_negative")
    if price <= 0:
        raise QuoteUnitSizingError("asset_price_usd_invalid")
    if notional == 0:
        return 0

    raw = (notional / price) * (Decimal(10) ** decimals)
    units = raw.to_integral_value(rounding=ROUND_FLOOR)
    if units < 0:
        raise QuoteUnitSizingError("raw_units_negative")
    try:
        return int(units)
    except (OverflowError, ValueError) as exc:
        raise QuoteUnitSizingError("raw_units_invalid") from exc


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
    price = _decimal(asset_price_usd)
    if price <= 0:
        raise QuoteUnitSizingError("asset_price_usd_invalid")
    value = (Decimal(units) * price) / (Decimal(10) ** decimals)
    if not value.is_finite() or value < 0:
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


def validate_quote_context(quote: Mapping[str, Any] | None) -> tuple[bool, tuple[str, ...]]:
    """Validate the minimum quote contract required for raw-unit conversion."""
    normalized = quote_context_from_mapping(quote)
    errors: list[str] = []
    price = normalized.get("asset_price_usd")
    decimals = normalized.get("asset_decimals")
    if price is None:
        errors.append("asset_price_usd_missing")
    else:
        try:
            value = float(price)
            if not math.isfinite(value) or value <= 0:
                errors.append("asset_price_usd_invalid")
        except (TypeError, ValueError):
            errors.append("asset_price_usd_invalid")
    if decimals is None:
        errors.append("asset_decimals_missing")
    else:
        try:
            value = int(decimals)
            if value < 0 or value > 255:
                errors.append("asset_decimals_invalid")
        except (TypeError, ValueError):
            errors.append("asset_decimals_invalid")
    return (not errors, tuple(errors))
