from __future__ import annotations

import pytest

from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.quote_balancer import (
    build_balancer_query_batchswap_calldata,
    quote_balancer_given_in_many,
)


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


def test_balancer_querybatchswap_calldata_uses_canonical_abi_offsets():
    pool_id = "0x" + "22" * 32
    token_in = "0x" + "33" * 20
    token_out = "0x" + "44" * 20
    amount_in = 123_456

    calldata = build_balancer_query_batchswap_calldata(
        pool_id,
        token_in,
        token_out,
        amount_in,
    )
    payload = bytes.fromhex(calldata[10:])  # exclude 4-byte function selector

    def word(offset: int) -> int:
        return int.from_bytes(payload[offset:offset + 32], "big")

    # queryBatchSwap arguments: kind, two dynamic offsets, then the four
    # inline static words of FundManagement. Offsets exclude the selector.
    assert word(0) == 0  # GIVEN_IN
    swaps_offset = word(32)
    assets_offset = word(64)
    assert swaps_offset == 7 * 32
    assert assets_offset == swaps_offset + 8 * 32
    assert len(payload) == assets_offset + 3 * 32

    # One dynamic BatchSwapStep tuple: array length, tuple offset, tuple body.
    assert word(swaps_offset) == 1
    assert word(swaps_offset + 32) == 32
    tuple_start = swaps_offset + 64
    assert payload[tuple_start:tuple_start + 32] == bytes.fromhex(pool_id[2:])
    assert word(tuple_start + 32) == 0  # assetInIndex
    assert word(tuple_start + 64) == 1  # assetOutIndex
    assert word(tuple_start + 96) == amount_in
    assert word(tuple_start + 128) == 32 * 5  # userData offset
    assert word(tuple_start + 160) == 0  # empty userData

    # FundManagement is inline and the asset address array is correctly located.
    assert [word(offset) for offset in (96, 128, 160, 192)] == [0, 0, 0, 0]
    assert word(assets_offset) == 2
    assert payload[assets_offset + 32:assets_offset + 64][-20:] == bytes.fromhex(token_in[2:])
    assert payload[assets_offset + 64:assets_offset + 96][-20:] == bytes.fromhex(token_out[2:])


def test_balancer_querybatchswap_rejects_malformed_pool_id_and_nonpositive_size():
    with pytest.raises(ValueError, match="exactly 32 bytes"):
        build_balancer_query_batchswap_calldata("0x1234", "0x" + "33" * 20, "0x" + "44" * 20, 1)
    with pytest.raises(ValueError, match="positive"):
        build_balancer_query_batchswap_calldata("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 0)
