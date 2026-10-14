from types import SimpleNamespace

import pytest

from victor_ai_bot import usd_pricing


@pytest.mark.asyncio
async def test_gas_conversion_uses_configured_stable_bridge_when_direct_pair_missing(monkeypatch):
    calls = []

    async def fake_quote(
        _rpc, *, quoter_v2, token_in, token_out, amount_in, block_tag, cache=None
    ):
        calls.append((token_in, token_out, int(amount_in), block_tag))
        prices = {
            ("weth", "profit-token"): None,
            ("weth", "usdc"): 125_000,
            ("usdc", "profit-token"): 875,
        }
        return prices.get((token_in, token_out))

    monkeypatch.setattr(usd_pricing, "_quote_best_univ3_out", fake_quote)
    chain = SimpleNamespace(
        weth="WETH",
        usdc="USDC",
        usdt="",
        univ3_quoter_v2="quoter",
    )

    result = await usd_pricing.gas_wei_to_token_wei(
        object(),
        chain=chain,
        gas_cost_wei=10**15,
        token_out="profit-token",
        block_number=123,
    )

    assert result == 875
    assert calls == [
        ("weth", "profit-token", 10**15, "0x7b"),
        ("weth", "usdc", 10**15, "0x7b"),
        ("usdc", "profit-token", 125_000, "0x7b"),
    ]


@pytest.mark.asyncio
async def test_gas_conversion_prefers_a_positive_direct_quote(monkeypatch):
    calls = []

    async def fake_quote(
        _rpc, *, quoter_v2, token_in, token_out, amount_in, block_tag, cache=None
    ):
        calls.append((token_in, token_out))
        if (token_in, token_out) == ("weth", "profit-token"):
            return 321
        return None

    monkeypatch.setattr(usd_pricing, "_quote_best_univ3_out", fake_quote)
    chain = SimpleNamespace(
        weth="weth", usdc="usdc", usdt="usdt", univ3_quoter_v2="quoter",
    )

    result = await usd_pricing.gas_wei_to_token_wei(
        object(), chain=chain, gas_cost_wei=10**15,
        token_out="profit-token", block_number=456,
    )

    assert result == 321
    assert calls == [("weth", "profit-token")]


@pytest.mark.asyncio
async def test_gas_conversion_fails_closed_when_no_complete_quote_path_exists(monkeypatch):
    async def fake_quote(
        _rpc, *, quoter_v2, token_in, token_out, amount_in, block_tag, cache=None
    ):
        if (token_in, token_out) == ("weth", "usdc"):
            return 125_000
        # No direct WETH->profit-token quote and no stable->profit-token quote.
        return None

    monkeypatch.setattr(usd_pricing, "_quote_best_univ3_out", fake_quote)
    chain = SimpleNamespace(
        weth="weth", usdc="usdc", usdt="", univ3_quoter_v2="quoter",
    )

    result = await usd_pricing.gas_wei_to_token_wei(
        object(), chain=chain, gas_cost_wei=10**15,
        token_out="profit-token", block_number=456,
    )

    assert result is None
