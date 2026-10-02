from types import SimpleNamespace

import pytest

from victor_ai_bot.flashloan_providers import observe_flashloan_fee_bps
from victor_ai_bot.profitability_state import revalidate_profitability_state
from victor_ai_bot.models import Opportunity, Route, RouteLeg


class _Rpc:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def eth_call(self, to, data, block="latest", **kwargs):
        self.calls.append((to, data, block))
        return self.results.pop(0)


def _ok(value: int):
    return SimpleNamespace(ok=True, result="0x" + int(value).to_bytes(32, "big").hex())


def _cfg(provider="aave"):
    return SimpleNamespace(
        chain=SimpleNamespace(
            aave_v3_pool="0x" + "aa" * 20,
            balancer_vault="0x" + "bb" * 20,
        ),
        execution=SimpleNamespace(flash_provider=provider, flashloan_fee_bps=9),
        safety=SimpleNamespace(minProfitAbs=0, minProfitBps=0),
    )


@pytest.mark.asyncio
async def test_aave_flashloan_premium_is_read_from_pool():
    rpc = _Rpc([_ok(5)])
    observed = await observe_flashloan_fee_bps(rpc, _cfg(), "aave", block="0x123")
    assert observed["ok"] is True
    assert observed["fee_bps"] == 5
    assert observed["source"] == "aave_pool_FLASHLOAN_PREMIUM_TOTAL"
    assert rpc.calls[0][0] == _cfg().chain.aave_v3_pool


@pytest.mark.asyncio
async def test_balancer_flashloan_fee_is_read_from_protocol_fee_collector():
    collector = "0x" + "cc" * 20
    rpc = _Rpc([_ok(int(collector, 16)), _ok(0)])
    observed = await observe_flashloan_fee_bps(rpc, _cfg("balancer"), "balancer")
    assert observed["ok"] is True
    assert observed["fee_bps"] == 0
    assert observed["fee_collector"] == collector
    assert len(rpc.calls) == 2


@pytest.mark.asyncio
async def test_aave_rpc_failure_does_not_silently_claim_authoritative_fee():
    rpc = _Rpc([SimpleNamespace(ok=False, result=None, error="boom")])
    observed = await observe_flashloan_fee_bps(rpc, _cfg(), "aave")
    assert observed["ok"] is False
    assert observed["reason"] == "flashloan_premium_rpc_unavailable"


def test_revalidation_accepts_provider_native_fee_override():
    opp = Opportunity(
        id="opp",
        chain="eth",
        strategy="two-leg:univ3->univ3",
        expected_profit_raw="100",
        expected_profit_usd="0",
        route=Route(
            legs=[
                RouteLeg(
                    dex="univ3",
                    venue="router",
                    token_in="0x" + "11" * 20,
                    token_out="0x" + "22" * 20,
                    amount_in="1000",
                    min_out="1100",
                    data="0x",
                )
            ]
        ),
        min_outs=["1100"],
        route_id="route",
        meta={"gas_cost_estimate_wei": "1"},
    )
    state = revalidate_profitability_state(
        opp,
        _cfg(),
        stage="test",
        source="test",
        gas_cost_wei=1,
        quoted_amount_out_wei=1100,
        flashloan_fee_bps_override=500,
    )
    assert state["flashloan_fee_wei"] == "50"
