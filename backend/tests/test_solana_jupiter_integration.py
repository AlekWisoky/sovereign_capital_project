import asyncio

import pytest

from victor_ai_bot.runtime_services.solana_jupiter import (
    JupiterQuote,
    JupiterQuoteHTTPError,
    after_cost_profit_usd,
    economic_frontier,
)
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
    assert quote.error_message == ""


def test_jupiter_client_uses_explicit_discovery_taker(monkeypatch):
    monkeypatch.setenv("JUPITER_API_KEY", "test-key")
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_TAKER", "11111111111111111111111111111111")
    from victor_ai_bot.runtime_services.solana_jupiter import JupiterSwapV2Client
    client = JupiterSwapV2Client()
    assert client.default_taker == "11111111111111111111111111111111"


def test_after_cost_profit_is_dimensionally_bounded_by_explicit_costs():
    quote = JupiterQuote(
        input_mint="SOL", output_mint="USDC", in_amount=100, out_amount=200,
        router="metis", request_id="r", fee_bps=10, fee_mint="USDC",
        platform_fee_bps=10, platform_fee_amount=2, transaction_available=False,
        mode="ultra", error_code=None, error_message="",
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


def test_solana_shadow_quote_telemetry_does_not_overcount_first_quote_failure(monkeypatch):
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_ENABLED", "1")
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_TAKER", "11111111111111111111111111111111")
    service = JupiterShadowService()

    async def failing_quote(**kwargs):
        raise ValueError("first_quote_failed")

    monkeypatch.setattr(service.client, "quote", failing_quote)

    import asyncio
    row, attempts, successes, reason = asyncio.run(service._discover_direction(
        input_mint="USDC", output_mint="SOL", input_decimals=6,
        symbol="SOL/USDC", usd=100.0,
        network={"usd": 0.01}, jupiter_first=True,
    ))
    assert row is None
    assert attempts == 1
    assert successes == 0
    assert reason == "ValueError"


@pytest.mark.asyncio
async def test_solana_shadow_discovers_quote_derived_cross_venue_edge_without_execution(monkeypatch):
    from victor_ai_bot.runtime_services.solana_jupiter import JupiterQuote
    from victor_ai_bot.runtime_services.solana_raydium import RaydiumQuote

    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_ENABLED", "1")
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_TAKER", "11111111111111111111111111111111")
    service = JupiterShadowService()
    service.client.api_key = "test-key"
    monkeypatch.setattr(service, "_pair_universe", lambda: [("USDC", "SOL", 6, 9, "SOL/USDC")])
    monkeypatch.setattr(service, "_sizes", lambda: [100.0])
    async def sol_price():
        return 100.0
    monkeypatch.setattr(service, "_sol_price_usd", sol_price)
    async def network_cost(price):
        return {"available": True, "usd": 0.01, "lamports": 100000, "source": "test", "verified": False}
    monkeypatch.setattr(service, "_network_cost_usd", network_cost)

    async def j_quote(*, input_mint, output_mint, amount, taker=None):
        if input_mint == "USDC":
            return JupiterQuote("USDC", "SOL", amount, 1_000_000_000, "metis", "j", 10, "USDC", 0, 0, False, "ultra", None, "")
        return JupiterQuote("SOL", "USDC", amount, 102_000_000, "metis", "p", 10, "USDC", 0, 0, False, "ultra", None, "")

    async def r_quote(*, input_mint, output_mint, amount):
        out_amount = 1_010_000_000 if input_mint == "USDC" else 101_000_000
        return RaydiumQuote(input_mint, output_mint, amount, out_amount, 0.01, (), "r")

    monkeypatch.setattr(service.client, "quote", j_quote)
    monkeypatch.setattr(service.raydium, "quote", r_quote)

    result = await service.discover()
    assert result["discovery"]["cross_venue_routes"] == 2
    assert {row["route_id"] for row in result["candidates"]} == {
        "solana:SOL/USDC:jupiter-to-raydium",
        "solana:SOL/USDC:raydium-to-jupiter",
    }
    assert all(row["quote_derived"] is True for row in result["candidates"])
    assert result["candidates"][0]["after_cost_profit_usd"] > 0
    assert result["candidates"][0]["authoritative"] is False
    assert result["execution_authority"] is False


def test_jupiter_http_failure_preserves_status_without_body():
    exc = JupiterQuoteHTTPError(429)
    assert exc.status_code == 429
    assert str(exc) == "http_429"


@pytest.mark.asyncio
async def test_solana_shadow_preserves_jupiter_http_status(monkeypatch):
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_ENABLED", "1")
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_TAKER", "11111111111111111111111111111111")
    service = JupiterShadowService()

    async def failing_quote(**kwargs):
        from victor_ai_bot.runtime_services.solana_jupiter import JupiterQuoteHTTPError
        raise JupiterQuoteHTTPError(400)

    monkeypatch.setattr(service.client, "quote", failing_quote)
    row, attempts, successes, reason = await service._discover_direction(
        input_mint="USDC", output_mint="SOL", input_decimals=6,
        symbol="SOL/USDC", usd=100.0,
        network={"usd": 0.01}, jupiter_first=True,
    )
    assert row is None
    assert attempts == 1
    assert successes == 0
    assert reason == "http_400"

@pytest.mark.asyncio
async def test_snapshot_refresh_schedules_one_background_discovery(monkeypatch):
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_ENABLED", "1")
    monkeypatch.setenv("VICTOR_SOLANA_JUPITER_REFRESH_INTERVAL_S", "15")
    service = JupiterShadowService()
    service.enabled = True
    service.client = type("Client", (), {"configured": True, "default_taker": "test-taker"})()
    calls = 0
    finished = asyncio.Event()

    async def fake_discover():
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        service._last = {**service._last, "status": "healthy", "execution_authority": False}
        finished.set()
        return service.snapshot()

    monkeypatch.setattr(service, "discover", fake_discover)

    first = service.snapshot_or_schedule_refresh()
    second = service.snapshot_or_schedule_refresh()
    assert first["refresh"]["started_by_this_read"] is True
    assert second["refresh"]["started_by_this_read"] is False
    assert second["refresh"]["in_progress"] is True

    await asyncio.wait_for(finished.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert calls == 1
    assert service.snapshot()["status"] == "healthy"
    assert service.snapshot()["execution_authority"] is False

