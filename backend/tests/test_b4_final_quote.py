from __future__ import annotations

from types import SimpleNamespace

import pytest

import victor_ai_bot.execution_capture.final_quote as final_quote
from victor_ai_bot.execution_capture.final_quote import (
    FinalQuoteError,
    FinalQuoteRequest,
    produce_final_quote,
)
from victor_ai_bot.execution_capture.institutional_sizing import (
    CapitalAuthoritySizingContext,
    EconomicsSizingContext,
    ExecutionSizingContext,
    GovernanceSizingContext,
    InstitutionalSizingContract,
    LiquiditySizingContext,
    SettlementSizingContext,
    WealthGoalSizingContext,
)
from victor_ai_bot.execution_capture.institutional_sizing_kernel import calculate_institutional_size


class FakeRpc:
    def __init__(self, decimals: dict[str, int]):
        self.decimals = {key.lower(): value for key, value in decimals.items()}

    async def eth_call(self, to: str, data: str, *, block: str = "latest", **kwargs):
        selector = data[:10].lower()
        if selector == "0x313ce567":  # decimals()
            value = self.decimals.get(to.lower())
            if value is None:
                return SimpleNamespace(ok=False, result=None, error="missing")
            return SimpleNamespace(ok=True, result="0x" + int(value).to_bytes(32, "big").hex())
        return SimpleNamespace(ok=True, result="0x" + (1).to_bytes(32, "big").hex())


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            univ3_factory="0xfactory",
            univ3_quoter_v2="0xquoter",
            usdc="0xusdc",
        ),
        execution=SimpleNamespace(usd_stable_preference="usdc"),
    )


def _opp():
    return SimpleNamespace(
        route_id="route-final-1",
        route=SimpleNamespace(legs=[SimpleNamespace(token_in="0xasset")]),
        meta={
            "canonical_lineage": {
                "decision_id": "decision-final-1",
                "correlation_id": "corr-final-1",
            }
        },
    )


def _decision():
    return SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-final-1",
            "correlation_id": "corr-final-1",
        }
    )


def _quote_request(rpc, cfg, opp, decision, block_number):
    return FinalQuoteRequest(
        rpc=rpc,
        cfg=cfg,
        opp=opp,
        decision=decision,
        block_number=block_number,
    )


@pytest.mark.asyncio
async def test_final_quote_resolves_decimals_and_direct_v3_usd_reference(monkeypatch):
    rpc = FakeRpc({"0xasset": 18, "0xusdc": 6})

    async def pool(request):
        return "0xpool" if request.fee == 3000 else None

    async def quote(*args, **kwargs):
        return SimpleNamespace(amount_out=2_500_000_000, gas_estimate=100_000)

    monkeypatch.setattr(final_quote, "_resolve_v3_pool", pool)
    monkeypatch.setattr(final_quote, "quote_exact_input_single", quote)

    result = await produce_final_quote(_quote_request(rpc, _cfg(), _opp(), _decision(), 123456))

    assert result.asset_decimals == 18
    assert result.stable_decimals == 6
    assert result.asset_price_usd == pytest.approx(2500.0)
    assert result.raw_amount == 10**18
    assert result.stable_amount_out_raw == 2_500_000_000
    assert result.block_number == 123456
    assert result.decision_id == "decision-final-1"
    assert result.correlation_id == "corr-final-1"
    assert result.route_id == "route-final-1"
    assert result.quote_id.startswith("quote-")


@pytest.mark.asyncio
async def test_final_quote_rejects_cross_trade_lineage(monkeypatch):
    rpc = FakeRpc({"0xasset": 18, "0xusdc": 6})

    async def pool(request):
        return None

    monkeypatch.setattr(final_quote, "_resolve_v3_pool", pool)

    opp = _opp()
    decision = _decision()
    decision.metadata["canonical_decision_id"] = "different-decision"

    with pytest.raises(FinalQuoteError, match="decision_lineage_conflict"):
        await produce_final_quote(_quote_request(rpc, _cfg(), opp, decision, 1))


@pytest.mark.asyncio
async def test_final_quote_fails_closed_without_v3_usd_reference(monkeypatch):
    rpc = FakeRpc({"0xasset": 18, "0xusdc": 6})

    async def pool(request):
        return None

    monkeypatch.setattr(final_quote, "_resolve_v3_pool", pool)

    with pytest.raises(FinalQuoteError, match="v3_usd_reference_pool_unavailable"):
        await produce_final_quote(_quote_request(rpc, _cfg(), _opp(), _decision(), 2))


def _contract(max_raw: int = 0):
    return InstitutionalSizingContract(
        contract_version="institutional-v1",
        strategy_family="flash_arb",
        capital_source="flashloan",
        requested_notional_usd=250_000.0,
        target_notional_usd=250_000.0,
        base_borrow_amount_wei=0,
        max_borrow_amount_wei=max_raw,
        liquidity=LiquiditySizingContext(
            available_usd=500_000.0,
            depth_usd=500_000.0,
            pool_depth_cap_usd=500_000.0,
        ),
        execution=ExecutionSizingContext(
            expected_pipeline_latency_ms=100.0,
            latency_half_life_ms=1000.0,
            endpoint_quality=1.0,
            venue_reliability=1.0,
            simulation_confidence=1.0,
            freshness_score=1.0,
        ),
        economics=EconomicsSizingContext(
            expected_gross_profit_usd=1000.0,
            expected_net_profit_usd=500.0,
            min_profit_usd=1.0,
            min_profit_bps=1.0,
            success_probability=0.99,
            margin_ratio=0.01,
        ),
        capital=CapitalAuthoritySizingContext(
            status="ok",
            freshness="fresh",
            authority_id="cap-auth-quote",
            deployable_usd=2_000_000.0,
            drawdown_buffer_usd=0.0,
            prime_available=True,
            prime_capacity_usd=2_000_000.0,
            prime_utilization=0.0,
            prime_reserved_usd=0.0,
        ),
        wealth_goal=WealthGoalSizingContext(
            capital_commitment_pct=30.0,
            aggressiveness_cap=1.0,
            max_drawdown_pct=10.0,
            drawdown_pct=0.0,
        ),
        governance=GovernanceSizingContext(
            admitted=True,
            reason_code="ok",
            strategy_family="flash_arb",
            capital_source="flashloan",
            live_authority=False,
            execution_allowed=False,
            max_deployable_pct=0.35,
        ),
        settlement=SettlementSizingContext(),
        metadata={"behavior_change": "none"},
    )


def test_quote_bound_raw_conversion_preserves_canonical_sizing_id():
    contract = _contract()
    base = calculate_institutional_size(contract)
    quoted = calculate_institutional_size(
        contract,
        final_quote={
            "quote_id": "quote-1",
            "asset_price_usd": 2500.0,
            "asset_decimals": 18,
            "block_number": 123,
        },
    )

    assert quoted.sizing_id == base.sizing_id
    assert quoted.approved_notional_usd == pytest.approx(base.approved_notional_usd)
    assert quoted.approved_borrow_amount_raw == 100_000_000_000_000_000_000


def test_quote_bound_raw_cap_does_not_create_second_sizing_identity():
    contract = _contract(max_raw=50_000_000_000_000_000_000)
    base = calculate_institutional_size(contract)
    quoted = calculate_institutional_size(
        contract,
        final_quote={
            "quote_id": "quote-cap",
            "asset_price_usd": 2500.0,
            "asset_decimals": 18,
            "block_number": 124,
        },
    )

    assert quoted.sizing_id == base.sizing_id
    assert quoted.approved_notional_usd == pytest.approx(base.approved_notional_usd)
    assert quoted.approved_borrow_amount_raw == 50_000_000_000_000_000_000
    assert "max_borrow_amount_raw" in quoted.constraints_applied
