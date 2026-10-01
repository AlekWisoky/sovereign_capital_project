from __future__ import annotations

import asyncio
from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_primary_scan_facade as scan_mod


WETH = "0x0000000000000000000000000000000000000001"
USDC = "0x0000000000000000000000000000000000000002"
WBTC = "0x0000000000000000000000000000000000000003"


def test_scan_notional_is_normalized_by_token_decimals_and_price(monkeypatch):
    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(
            token_universe=[WETH, USDC, WBTC],
            weth=WETH,
        )
    )

    async def fake_market_price_evidence(*_args, **_kwargs):
        return {
            WETH.lower(): {"decimals": 18, "price_usd": 4000.0},
            USDC.lower(): {"decimals": 6, "price_usd": 1.0},
            WBTC.lower(): {"decimals": 8, "price_usd": 100000.0},
        }

    monkeypatch.setattr(
        scan_mod,
        "produce_market_price_evidence",
        fake_market_price_evidence,
    )

    amounts, telemetry = asyncio.run(
        runtime._build_token_scan_amounts(
            object(),
            current_block=123,
            base_amount_in=10**16,
            cache=object(),
        )
    )

    assert amounts[WETH.lower()] == 10**16
    assert amounts[USDC.lower()] == 40_000_000
    assert amounts[WBTC.lower()] == 40_000
    assert telemetry["source"] == "quote_derived_usd_notional"
    assert telemetry["reference_notional_usd"] == 40.0


def test_scan_notional_does_not_reuse_reference_raw_units_when_price_missing(monkeypatch):
    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(
            token_universe=[WETH, USDC],
            weth=WETH,
        )
    )

    async def fake_market_price_evidence(*_args, **_kwargs):
        return {
            WETH.lower(): {"decimals": 18, "price_usd": 4000.0},
        }

    monkeypatch.setattr(
        scan_mod,
        "produce_market_price_evidence",
        fake_market_price_evidence,
    )

    amounts, telemetry = asyncio.run(
        runtime._build_token_scan_amounts(
            object(),
            current_block=123,
            base_amount_in=10**16,
            cache=object(),
        )
    )

    assert amounts == {WETH.lower(): 10**16}
    assert USDC in telemetry["unpriced_tokens"]
