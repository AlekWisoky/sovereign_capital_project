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
    assert state["gas_cost_conversion_available"] is True
    assert state["repayment_valid"] is True
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


def test_build_profitability_state_preserves_signed_gross_diagnostic():
    from victor_ai_bot.profitability_state import build_profitability_state

    state = build_profitability_state(
        stage="scan",
        source="test",
        reason="non_positive_gross_profit",
        revalidated=True,
        stale=False,
        valid=False,
        gross_profit_wei=-123,
        profit_after_costs_wei=-456,
    )
    assert state["gross_profit_wei"] == "-123"
    assert state["profit_after_costs_wei"] == "-456"


@pytest.mark.asyncio
async def test_scan_revalidates_authoritative_state_after_notional_changes(monkeypatch):
    from victor_ai_bot.cache import PerBlockCache
    from victor_ai_bot.runtime_services import runtime_primary_scan_facade as scan_mod

    runtime = scan_mod.RuntimePrimaryScanFacade.__new__(
        scan_mod.RuntimePrimaryScanFacade
    )
    runtime.cfg = SimpleNamespace(
        chain=SimpleNamespace(
            name="ethereum",
            chain_id=1,
            weth="0x0000000000000000000000000000000000000001",
            usdc="",
            usdt="",
        ),
        execution=SimpleNamespace(
            usd_accounting_enabled=False,
            usd_stable_preference="usdc",
            flash_provider="aave",
            flashloan_fee_bps=90,
            gas_mode="standard",
            gas_presets=SimpleNamespace(standard_max_fee_gwei=25),
        ),
        safety=SimpleNamespace(minProfitAbs=0, minProfitBps=0, slippage_bps=50),
    )
    runtime.cache = PerBlockCache()

    opp = _opp(1_000_000, 1_020_000)
    opp.meta.update({
        "venues": ["univ3", "univ3"],
        "leg1": {"gas_estimate": 120_000},
        "leg2": {"gas_estimate": 120_000},
        "out1": "1_010_000",
        "out2": "1_020_000",
    })

    # Simulate an authoritative state produced for a previous 2x notional.
    opp.route.legs[0].amount_in = "2_000_000"
    opp.meta["out2"] = "2_100_000"
    old_state = revalidate_profitability_state(
        opp,
        runtime.cfg,
        stage="scan_after_fee_revalidation",
        source="test_previous_size",
        gas_cost_wei=1,
        gas_cost_in_profit_token_wei=1,
        quoted_amount_out_wei=2_100_000,
    )
    assert old_state["authoritative"] is True
    assert old_state["profit_after_costs_wei"] == "81999"
    opp.meta["canonical_after_fee_usd"] = {
        "verified": True,
        "source": "quote_derived_canonical_after_fee",
        "profit_token": opp.route.legs[0].token_in,
        "profit_after_costs_wei": "81999",
        "profit_after_costs_usd_micro": "99000000",
        "block_number": 122,
    }
    opp.meta["profit_after_gas_estimate_wei"] = "81999"
    opp.meta["profit_after_gas_estimate_usd_micro"] = "99000000"

    # The actual candidate now represents a different borrow amount and quote.
    opp.route.legs[0].amount_in = "1000000"
    opp.min_outs = ["1020000"]
    opp.expected_profit_raw = "20000"
    opp.meta.update({
        "out1": "1010000",
        "out2": "1020000",
        "requoted_amount_in": "1000000",
    })

    async def fake_gas_conversion(_rpc, *, gas_cost_wei, token_out, **_kwargs):
        assert int(gas_cost_wei) == 510_000
        assert token_out == opp.route.legs[0].token_in
        return 1_000

    monkeypatch.setattr(scan_mod, "gas_wei_to_token_wei", fake_gas_conversion)

    await runtime._annotate_canonical_after_fee_usd(
        opps=[opp],
        rpc=object(),
        current_block=123,
        cache=PerBlockCache(),
        observed_gas_price_wei=1,
        gas_price_integrity={"status": "consensus", "gas_price_wei": 1},
        flashloan_fee_observation={"ok": True, "provider": "aave", "fee_bps": 90},
    )

    refreshed = opp.meta["profitability"]
    assert refreshed["authoritative"] is True
    assert refreshed["amount_in_wei"] == "1000000"
    assert refreshed["amount_out_wei"] == "1020000"
    assert refreshed["flashloan_fee_wei"] == "9000"
    assert refreshed["gas_cost_wei"] == "510000"
    assert refreshed["gas_cost_profit_token_wei"] == "1000"
    assert refreshed["profit_after_costs_wei"] == "10000"
    assert "canonical_after_fee_usd" not in opp.meta
    assert "profit_after_gas_estimate_wei" not in opp.meta
    assert "profit_after_gas_estimate_usd_micro" not in opp.meta

