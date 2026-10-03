import pytest

from victor_ai_bot.runtime_services.solana_jupiter import JupiterQuote, after_cost_profit_usd, economic_frontier
from victor_ai_bot.runtime_services.jupiter_shadow import JupiterShadowService


def test_jupiter_quote_parses_quote_only_response():
    quote = JupiterQuote.from_response(
        {
            "inputMint": "SOL",
            "outputMint": "USDC",
            "inAmount": "100000000",
            "outAmount": "20000000",
            "router": "metis",
            "requestId": "req-1",
            "feeBps": 10,
            "feeMint": "USDC",
            "platformFee": {"amount": "20", "feeBps": 10},
            "transaction": None,
            "mode": "ultra",
        }
    )
    assert quote.out_amount == 20_000_000
    assert quote.router == "metis"
    assert quote.transaction_available is False
    assert quote.platform_fee_amount == 20


def test_after_cost_profit_is_dimensionally_bounded_by_explicit_costs():
    quote = JupiterQuote(
        input_mint="SOL", output_mint="USDC", in_amount=100, out_amount=200,
        router="metis", request_id="r", fee_bps=10, fee_mint="USDC",
        platform_fee_bps=10, platform_fee_amount=2, transaction_available=False,
        mode="ultra", error_code=None,
    )
    assert after_cost_profit_usd(
        input_usd=10.0, output_usd=20.0, quote=quote, network_cost_usd=1.0
    ) == pytest.approx(8.8)


def test_economic_frontier_never_extrapolates():
    frontier = economic_frontier([
        {"amount": 10, "after_cost_profit_usd": 0.5},
        {"amount": 20, "after_cost_profit_usd": 0.9},
        {"amount": 40, "after_cost_profit_usd": 0.2},
    ])
    assert frontier["best_observed"]["amount"] == 20
    assert frontier["extrapolated"] is False


def test_jupiter_shadow_is_fail_closed_without_enablement(monkeypatch):
    monkeypatch.delenv("VICTOR_SOLANA_JUPITER_ENABLED", raising=False)
    service = JupiterShadowService()
    assert service.snapshot()["status"] == "disabled"
    assert service.snapshot()["execution_authority"] is False


@pytest.mark.asyncio
async def test_solana_shadow_discovers_quote_derived_cross_venue_edge_without_execution(monkeypatch):
    from victor_ai_bot.runtime_services.solana_jupiter import JupiterQuote
    from victor_ai_bot.runtime_services.solana_raydium import RaydiumQuote

    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_ENABLED", "1")
    service = JupiterShadowService()
    service.client.api_key = "test-key"
    monkeypatch.setattr(service, "_pair_universe", lambda: [("USDC", "SOL", 6, 9, "SOL/USDC")])
    monkeypatch.setattr(service, "_sizes", lambda: [100.0])
    monkeypatch.setattr(service, "_sol_price_usd", lambda: pytest.approx(100.0))
    monkeypatch.setattr(
        service,
        "_network_cost_usd",
        lambda price: {"available": True, "usd": 0.01, "lamports": 100000, "source": "test", "verified": False},
    )

    async def j_quote(*, input_mint, output_mint, amount, taker=None):
        if input_mint == "USDC":
            return JupiterQuote("USDC", "SOL", amount, 1_000_000_000, "metis", "j", 10, "USDC", 0, 0, False, "ultra", None)
        return JupiterQuote("SOL", "USDC", amount, 100_000_000, "metis", "p", 10, "USDC", 0, 0, False, "ultra", None)

    async def r_quote(*, input_mint, output_mint, amount):
        return RaydiumQuote(input_mint, output_mint, amount, 101_000_000, 0.01, (), "r")

    monkeypatch.setattr(service.client, "quote", j_quote)
    monkeypatch.setattr(service.raydium, "quote", r_quote)

    result = await service.discover()
    assert result["discovery"]["cross_venue_routes"] == 1
    assert result["candidates"][0]["quote_derived"] is True
    assert result["candidates"][0]["after_cost_profit_usd"] > 0
    assert result["candidates"][0]["authoritative"] is False
    assert result["execution_authority"] is False
