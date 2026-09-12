from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.calldata_builder import build_execute_calldata
from victor_ai_bot.execution_capture.b4_execution_binding import bind_final_quote_to_execution
from victor_ai_bot.execution_capture.final_quote import FinalQuote
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade as wrapper_module
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import AutoExecutionDispatchContext

ASSET = "0x1111111111111111111111111111111111111111"
USDC = "0x2222222222222222222222222222222222222222"
VENUE = "0x3333333333333333333333333333333333333333"
PROFIT_TO = "0x0000000000000000000000000000000000000001"


class _RpcContext:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_b42_binding_proves_quote_to_raw_amount_at_calldata_boundary(monkeypatch):
    opp = SimpleNamespace(
        route_id="route-b42",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(
                    amount_in=1,
                    token_in=ASSET,
                    dex="univ3",
                    venue=VENUE,
                    token_out=USDC,
                    min_out="250000000",
                    data="0x",
                )
            ]
        ),
        min_outs=["250000000"],
        meta={
            "brain": {
                "canonical_decision_id": "decision-b42",
                "correlation_id": "correlation-b42",
                "sizing_id": "sizing-b42",
            },
            "canonical_lineage": {
                "decision_id": "decision-b42",
                "correlation_id": "correlation-b42",
                "sizing_id": "sizing-b42",
                "approved_notional_usd": 250_000.0,
            },
        },
    )
    decision = SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-b42",
            "correlation_id": "correlation-b42",
            "sizing_id": "sizing-b42",
        },
        size_mult=1.5,
        borrow_mult=1.25,
    )
    quote = FinalQuote(
        quote_id="quote-b42",
        quoted_at_ms=1234567890,
        block_number=900,
        token=ASSET,
        raw_amount=10**18,
        asset_decimals=18,
        asset_price_usd=2500.0,
        price_source="test",
        route_id="route-b42",
        decision_id="decision-b42",
        correlation_id="correlation-b42",
        stable_token=USDC,
        stable_decimals=6,
        stable_amount_out_raw=250_000_000,
        fee=3000,
    )

    async def fake_quote(*args, **kwargs):
        return quote

    async def fake_requote(*args, **kwargs):
        args[3].route.legs[0].amount_in = kwargs["new_amount_in"]
        return args[3]

    monkeypatch.setattr(
        "victor_ai_bot.execution_capture.b4_execution_binding.produce_final_quote",
        fake_quote,
    )
    monkeypatch.setattr(
        "victor_ai_bot.execution_capture.b4_execution_binding.requote_opportunity",
        fake_requote,
    )

    captured = {}

    async def fake_execute(*args, **kwargs):
        bound_opp = args[3]
        leg = bound_opp.route.legs[0]
        calldata, _ = build_execute_calldata(
            provider="aave",
            borrow_token=leg.token_in,
            amount_borrow=int(leg.amount_in),
            min_profit=1,
            profit_to=PROFIT_TO,
            deadline=901,
            legs=[
                {
                    "dex": leg.dex,
                    "venue": leg.venue,
                    "token_in": leg.token_in,
                    "token_out": leg.token_out,
                    "min_out": int(leg.min_out),
                    "aux": leg.data or "0x",
                }
            ],
        )
        captured["calldata"] = calldata
        captured["amount_borrow"] = int(leg.amount_in)
        captured["decision_size_mult"] = getattr(kwargs["decision"], "size_mult")
        captured["decision_borrow_mult"] = getattr(kwargs["decision"], "borrow_mult")
        return SimpleNamespace(ok=True, dry_run=True, submitted=False, plan={})

    monkeypatch.setattr(
        wrapper_module,
        "_compat_execution_wrapper_symbols",
        lambda: (_RpcContext, fake_execute),
    )

    runtime = wrapper_module.RuntimeExecuteWrapperFacade()
    runtime.cfg = SimpleNamespace(
        execution=SimpleNamespace(gas_mode="standard", send_mode="public"),
    )
    runtime.metrics = SimpleNamespace(gas_mode="standard", send_mode="public")
    runtime.cache = object()
    runtime._last_submitted_block = -1
    runtime._execution_service = None

    async def _record_exec(*args, **kwargs):
        return None

    runtime._record_exec = _record_exec

    prep = AutoExecutionDispatchContext(
        opportunity=opp,
        force_dry=True,
        old_gas_mode="standard",
        old_send_mode="public",
        read_url="read",
        send_url="send",
    )

    await runtime._run_prepared_auto_execution(
        opp=opp,
        bn=900,
        decision=decision,
        prep=prep,
    )

    assert captured["amount_borrow"] == 100_000_000_000_000_000_000
    assert captured["amount_borrow"] != 1
    assert captured["decision_size_mult"] == 1.0
    assert captured["decision_borrow_mult"] == 1.0
    assert captured["calldata"].startswith("0x")
    assert decision.size_mult == 1.5
    assert decision.borrow_mult == 1.25
    assert opp.meta["b4_execution_quote"]["quote_id"] == "quote-b42"
    assert opp.meta["canonical_lineage"]["sizing_id"] == "sizing-b42"
    assert opp.meta["canonical_lineage"]["quote_id"] == "quote-b42"


@pytest.mark.asyncio
async def test_b42_binding_rejects_missing_sizing_lineage_before_requote(monkeypatch):
    opp = SimpleNamespace(
        route_id="route-b42",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in=1, token_in=ASSET)]),
        meta={
            "canonical_lineage": {
                "decision_id": "decision-b42",
                "correlation_id": "correlation-b42",
            }
        },
    )
    decision = SimpleNamespace(
        metadata={
            "canonical_decision_id": "decision-b42",
            "correlation_id": "correlation-b42",
        }
    )

    with pytest.raises(ValueError, match="sizing_id_required"):
        await bind_final_quote_to_execution(
            rpc_read=object(),
            cfg=SimpleNamespace(safety=SimpleNamespace(max_borrow_amount=0, slippage_bps=50)),
            cache=object(),
            opp=opp,
            decision=decision,
            block_number=900,
        )
