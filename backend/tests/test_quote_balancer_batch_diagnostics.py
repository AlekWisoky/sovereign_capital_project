from __future__ import annotations

import pytest

from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.quote_balancer import quote_balancer_given_in_many


class _BatchRpc:
    def __init__(self, results):
        self.results = results

    async def eth_call_batch(self, calls):
        return list(self.results)


@pytest.mark.asyncio
async def test_balancer_batch_quote_records_rpc_failure_diagnostics():
    rpc = _BatchRpc([RpcResult(False, error={"code": -32016, "message": "rate limit"})])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {"rpc_rate_limited": 1}


@pytest.mark.asyncio
async def test_balancer_batch_quote_records_parse_failure_diagnostics():
    rpc = _BatchRpc([RpcResult(True, result="0x")])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {"invalid_quote_result": 1}
