from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution_capture import final_quote


GOOD = "0x0000000000000000000000000000000000000011"
BAD = "0x0000000000000000000000000000000000000012"
USDC = "0x0000000000000000000000000000000000000013"


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(
            name="test",
            univ3_factory="0x0000000000000000000000000000000000000021",
            univ3_quoter_v2="0x0000000000000000000000000000000000000022",
            usdc=USDC,
            usdt="",
        ),
        execution=SimpleNamespace(usd_stable_preference="usdc"),
    )


def test_market_price_evidence_is_strict_by_default(monkeypatch):
    async def fake_decimals(_rpc, token, *, block):
        if str(token).lower() == BAD.lower():
            raise final_quote.FinalQuoteError("bad_token")
        return 6 if str(token).lower() == USDC.lower() else 18

    async def fake_best(*_args, **_kwargs):
        return 2000.0, 3000, 2_000_000_000

    monkeypatch.setattr(final_quote, "resolve_erc20_decimals", fake_decimals)
    monkeypatch.setattr(final_quote, "_best_v3_quote", fake_best)

    with pytest.raises(final_quote.FinalQuoteError, match="bad_token"):
        asyncio.run(
            final_quote.produce_market_price_evidence(
                object(),
                cfg=_cfg(),
                tokens=[(GOOD, "scan_input"), (BAD, "scan_input")],
                block_number=123,
            )
        )


def test_market_price_evidence_partial_mode_retains_independent_prices(monkeypatch):
    async def fake_decimals(_rpc, token, *, block):
        if str(token).lower() == BAD.lower():
            raise final_quote.FinalQuoteError("bad_token")
        return 6 if str(token).lower() == USDC.lower() else 18

    async def fake_best(*_args, **_kwargs):
        return 2000.0, 3000, 2_000_000_000

    monkeypatch.setattr(final_quote, "resolve_erc20_decimals", fake_decimals)
    monkeypatch.setattr(final_quote, "_best_v3_quote", fake_best)

    out = asyncio.run(
        final_quote.produce_market_price_evidence(
            object(),
            cfg=_cfg(),
            tokens=[(GOOD, "scan_input"), (BAD, "scan_input")],
            block_number=123,
            strict=False,
        )
    )

    assert GOOD.lower() in out
    assert BAD.lower() not in out
