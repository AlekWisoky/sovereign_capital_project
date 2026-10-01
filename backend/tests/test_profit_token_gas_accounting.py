from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.profitability_state import revalidate_profitability_state
from victor_ai_bot.safety import check_profit_and_repay


def _cfg():
    return SimpleNamespace(
        safety=SimpleNamespace(minProfitAbs=0, minProfitBps=0),
        execution=SimpleNamespace(flashloan_fee_bps=90),
    )


def _opp(amount_in: int, amount_out: int):
    return SimpleNamespace(
        expected_profit_raw=str(amount_out - amount_in),
        expected_profit_usd="0",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    amount_in=str(amount_in),
                    token_in="0x0000000000000000000000000000000000000002",
                )
            ]
        ),
        min_outs=[str(amount_out)],
        route_id="route-non-weth",
        meta={"leg1": {}, "leg2": {}, "venues": ["univ3", "univ3"]},
    )


def test_safety_subtracts_gas_in_profit_token_units_not_native_wei():
    result = check_profit_and_repay(
        amount_in_wei=1_000_000,
        amount_out_wei=1_020_000,
        min_profit_abs_wei=0,
        min_profit_bps=0,
        flashloan_fee_bps=90,
        gas_cost_wei=10**12,
        gas_cost_profit_token_wei=1_000,
    )

    assert result.ok is True
    assert result.flashloan_fee_wei == 9_000
    assert result.gas_cost_wei == 10**12
    assert result.gas_cost_profit_token_wei == 1_000
    assert result.profit_after_costs_wei == 10_000


def test_revalidation_accepts_non_weth_profit_token_gas_conversion():
    opp = _opp(1_000_000, 1_020_000)
    state = revalidate_profitability_state(
        opp,
        _cfg(),
        stage="scan_after_fee_revalidation",
        source="test",
        gas_cost_wei=10**12,
        gas_cost_in_profit_token_wei=1_000,
        quoted_amount_out_wei=1_020_000,
    )

    assert state["revalidated"] is True
    assert state["authoritative"] is True
    assert state["gas_cost_wei"] == str(10**12)
    assert state["gas_cost_profit_token_wei"] == "1000"
    assert state["profit_after_costs_wei"] == "10000"


@pytest.mark.asyncio
async def test_scan_revalidation_wires_converted_gas_into_profitability(monkeypatch):
    from victor_ai_bot.runtime_services import runtime_primary_scan_facade as scan_mod

    class _Rpc:
        async def gas_price(self):
            return 1

    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        execution=SimpleNamespace(
            usd_accounting_enabled=False,
            usd_stable_preference="usdc",
            flashloan_fee_bps=90,
            gas_mode="standard",
            gas_presets=SimpleNamespace(standard_max_fee_gwei=25),
        ),
        safety=SimpleNamespace(minProfitAbs=0, minProfitBps=0),
        chain=SimpleNamespace(weth="0x0000000000000000000000000000000000000001"),
    )
    runtime.cache = None

    opp = _opp(1_000_000, 1_020_000)
    opp.meta.update({
        "venues": ["univ3", "univ3"],
        "leg1": {"gas_estimate": 120_000},
        "leg2": {"gas_estimate": 120_000},
        "out1": "2",
        "out2": "1020000",
    })

    async def fake_gas_conversion(*_args, **_kwargs):
        return 1_000

    monkeypatch.setattr(scan_mod, "gas_wei_to_token_wei", fake_gas_conversion)

    await runtime._annotate_canonical_after_fee_usd(
        opps=[opp],
        rpc=_Rpc(),
        current_block=123,
        cache=None,
    )

    state = opp.meta["profitability"]
    assert state["authoritative"] is True
    assert state["gas_cost_profit_token_wei"] == "1000"
    assert state["profit_after_costs_wei"] == "10000"
