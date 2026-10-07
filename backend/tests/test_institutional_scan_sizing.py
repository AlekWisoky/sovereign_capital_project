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


def test_scan_notional_bridges_bounded_research_frontier_without_mutating_execution_universe(monkeypatch):
    research = "0x0000000000000000000000000000000000000004"
    unpriced_research = "0x0000000000000000000000000000000000000005"
    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(
            token_universe=[WETH, USDC],
            weth=WETH,
        )
    )
    runtime._discovery = SimpleNamespace(
        research_frontier_tokens=lambda _cfg, cap=None: [
            research,
            unpriced_research,
        ][: int(cap or 8)]
    )

    async def fake_market_price_evidence(*_args, **_kwargs):
        assert _kwargs["strict"] is False
        return {
            WETH.lower(): {"decimals": 18, "price_usd": 4000.0},
            USDC.lower(): {"decimals": 6, "price_usd": 1.0},
            research.lower(): {"decimals": 18, "price_usd": 2000.0},
        }

    monkeypatch.setenv("VICTOR_RESEARCH_TOKEN_SCAN_CAP", "2")
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

    assert amounts[research.lower()] == 20_000_000_000_000_000
    assert unpriced_research.lower() not in amounts
    assert telemetry["configured_tokens"] == 2
    assert telemetry["research_tokens_considered"] == 2
    assert telemetry["research_tokens_priced"] == 1
    assert telemetry["research_tokens_unpriced"] == [unpriced_research]
    assert (
        telemetry["research_token_scan_notional_source"]
        == "bounded_research_frontier_quote_derived_usd"
    )
    assert telemetry["research_token_execution_universe_mutated"] is False
    assert runtime.cfg.chain.token_universe == [WETH, USDC]


def test_scan_notional_partial_market_evidence_preserves_priced_configured_tokens(monkeypatch):
    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(
            token_universe=[WETH, USDC, WBTC],
            weth=WETH,
        )
    )
    runtime._discovery = None

    async def fake_market_price_evidence(*_args, **_kwargs):
        return {
            WETH.lower(): {"decimals": 18, "price_usd": 4000.0},
            USDC.lower(): {"decimals": 6, "price_usd": 1.0},
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
    assert amounts[USDC.lower()] == 4 * 10**7
    assert WBTC in telemetry["unpriced_tokens"]
    assert telemetry["configured_tokens_priced"] == 2
