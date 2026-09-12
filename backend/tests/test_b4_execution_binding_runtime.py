from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution_capture.b4_execution_binding import (
    bind_final_quote_to_execution,
)
from victor_ai_bot.execution_capture.final_quote import FinalQuote
from victor_ai_bot.runtime_services import runtime_execute_wrapper_facade as wrapper_module
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import (
    AutoExecutionDispatchContext,
)


class _RpcContext:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_b42_binding_proves_quote_to_raw_amount_before_production_execute(monkeypatch):
    opp = SimpleNamespace(
        route_id="route-b42",
        route=SimpleNamespace(
            legs=[SimpleNamespace(amount_in=1, token_in="0xasset")]
        ),
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
    cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=0, slippage_bps=50),
        execution=SimpleNamespace(),
    )
    quote = FinalQuote(
        quote_id="quote-b42",
        quoted_at_ms=1234567890,
        block_number=900,
        token="0xasset",
        raw_amount=10**18,
        asset_decimals=18,
        asset_price_usd=2500.0,
        price_source="test",
        route_id="route-b42",
        decision_id="decision-b42",
        correlation_id="correlation-b42",
        stable_token="0xusdc",
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
        captured["amount_borrow"] = args[3].route.legs[0].amount_in
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
    runtime._record_exec = lambda *args, **kwargs: None

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
    assert captured["decision_size_mult"] == 1.5
    assert captured["decision_borrow_mult"] == 1.25
    assert opp.meta["b4_execution_quote"]["quote_id"] == "quote-b42"
    assert opp.meta["canonical_lineage"]["sizing_id"] == "sizing-b42"
    assert opp.meta["canonical_lineage"]["quote_id"] == "quote-b42"


@pytest.mark.asyncio
async def test_b42_binding_rejects_missing_sizing_lineage_before_requote(monkeypatch):
    opp = SimpleNamespace(
        route_id="route-b42",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in=1, token_in="0xasset")]),
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
