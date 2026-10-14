from __future__ import annotations

import pytest

from victor_ai_bot.rpc import RpcResult
from victor_ai_bot.quote_balancer import (
    BalancerQuote,
    build_balancer_query_batchswap_calldata,
    quote_balancer_given_in,
    quote_balancer_given_in_many,
)


class _BatchRpc:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def eth_call_batch(self, calls):
        self.calls.extend(calls)
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


@pytest.mark.asyncio
async def test_malformed_balancer_request_does_not_abort_valid_batch_sibling():
    # queryBatchSwap returns an ABI-encoded int256[]: offset 32, length 2,
    # deltas [100, -120], matching the exact-input request for 100 units.
    encoded = (
        (32).to_bytes(32, "big")
        + (2).to_bytes(32, "big")
        + (100).to_bytes(32, "big")
        + ((1 << 256) - 120).to_bytes(32, "big")
    )
    rpc = _BatchRpc([RpcResult(True, result="0x" + encoded.hex())])
    diagnostics = {}
    valid_pool_id = "0x" + "22" * 32
    token_in = "0x" + "33" * 20
    token_out = "0x" + "44" * 20

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [
            ("0x1234", token_in, token_out, 100),
            (valid_pool_id, token_in, token_out, 100),
        ],
        diagnostics=diagnostics,
    )

    assert quotes == [None, BalancerQuote(amount_out=120)]
    assert len(rpc.calls) == 1
    assert rpc.calls[0]["data"] == build_balancer_query_batchswap_calldata(
        valid_pool_id, token_in, token_out, 100
    )
    assert diagnostics["failure_reasons"] == {"invalid_balancer_request": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_result",
    [
        # Declares three deltas but only returns two. The old permissive
        # decoder treated the missing third word as zero and could accept the
        # otherwise plausible second delta as an amountOut.
        "0x" + (
            (32).to_bytes(32, "big")
            + (3).to_bytes(32, "big")
            + (0).to_bytes(32, "big")
            + ((1 << 256) - 120).to_bytes(32, "big")
        ).hex(),
        # Canonical ABI output for a single int256[] return has no trailing
        # words outside the declared array.
        "0x" + (
            (32).to_bytes(32, "big")
            + (2).to_bytes(32, "big")
            + (0).to_bytes(32, "big")
            + ((1 << 256) - 120).to_bytes(32, "big")
            + (999).to_bytes(32, "big")
        ).hex(),
    ],
)
async def test_balancer_batch_rejects_truncated_or_noncanonical_return(
    malformed_result,
):
    rpc = _BatchRpc([RpcResult(True, result=malformed_result)])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {"invalid_quote_result": 1}


@pytest.mark.asyncio
async def test_single_balancer_quote_invalid_request_is_local_failure():
    class _NoCallRpc:
        async def eth_call(self, *_args, **_kwargs):
            raise AssertionError("malformed request must not reach RPC")

    diagnostics = {}
    quote = await quote_balancer_given_in(
        _NoCallRpc(),
        "0x" + "11" * 20,
        "0x1234",
        "0x" + "33" * 20,
        "0x" + "44" * 20,
        100,
        diagnostics=diagnostics,
    )

    assert quote is None
    assert diagnostics["failure_reasons"] == {"invalid_balancer_request": 1}


def _query_batch_swap_error(deltas):
    body = len(deltas).to_bytes(32, "big")
    for value in deltas:
        body += (int(value) % (1 << 256)).to_bytes(32, "big")
    return "0xfa61cc12" + body.hex()


@pytest.mark.asyncio
async def test_balancer_querybatchswap_decodes_documented_queryerror_revert():
    # Vault queryBatchSwap intentionally reverts with QueryError(int256[]).
    # The payload is selector + raw array length + signed deltas (no ABI offset).
    encoded = _query_batch_swap_error([100, -120])
    rpc = _BatchRpc([
        RpcResult(
            False,
            error={
                "code": -32000,
                "message": "execution reverted",
                "data": {"originalError": {"data": encoded}},
            },
        )
    ])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [BalancerQuote(amount_out=120)]
    assert diagnostics["query_revert_decoded"] == 1
    assert diagnostics.get("failure_reasons", {}) == {}


@pytest.mark.asyncio
async def test_single_balancer_quote_decodes_documented_queryerror_revert():
    encoded = _query_batch_swap_error([100, -120])

    class _SingleRpc:
        async def eth_call(self, _vault, _data):
            return RpcResult(
                False,
                error={"code": -32000, "message": "execution reverted: " + encoded},
            )

    diagnostics = {}
    quote = await quote_balancer_given_in(
        _SingleRpc(),
        "0x" + "11" * 20,
        "0x" + "22" * 32,
        "0x" + "33" * 20,
        "0x" + "44" * 20,
        100,
        diagnostics=diagnostics,
    )

    assert quote == BalancerQuote(amount_out=120)
    assert diagnostics["query_revert_decoded"] == 1
    assert diagnostics.get("failure_reasons", {}) == {}


@pytest.mark.asyncio
async def test_non_query_balancer_revert_is_not_accepted_as_a_quote():
    rpc = _BatchRpc([
        RpcResult(
            False,
            error={
                "code": -32000,
                "message": "execution reverted",
                "data": "0xdeadbeef" + "00" * 64,
            },
        )
    ])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {"rpc_revert": 1}
    assert diagnostics.get("query_revert_decoded", 0) == 0


@pytest.mark.asyncio
async def test_malformed_balancer_queryerror_payload_fails_closed():
    # Correct selector, but the declared length requires three values and only
    # two are present. Never infer missing deltas or turn this into a quote.
    malformed = "0xfa61cc12" + (
        (3).to_bytes(32, "big")
        + (100).to_bytes(32, "big")
        + ((1 << 256) - 120).to_bytes(32, "big")
    ).hex()
    rpc = _BatchRpc([
        RpcResult(False, error={"code": -32000, "message": "execution reverted", "data": malformed})
    ])
    diagnostics = {}

    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {
        "invalid_query_batch_swap_revert_data": 1
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("is_query_revert", [False, True])
async def test_balancer_quote_rejects_asset_deltas_for_different_input_amount(
    is_query_revert,
):
    # The output is positive and the encoding is well-formed, but the input
    # delta is 99 while this quote was requested for 100. Never bind this output
    # to the wrong size candidate or allow it to win the size optimum.
    if is_query_revert:
        result = RpcResult(
            False,
            error={
                "code": -32000,
                "message": "execution reverted",
                "data": _query_batch_swap_error([99, -120]),
            },
        )
    else:
        ordinary = (
            (32).to_bytes(32, "big")
            + (2).to_bytes(32, "big")
            + (99).to_bytes(32, "big")
            + ((1 << 256) - 120).to_bytes(32, "big")
        )
        result = RpcResult(True, result="0x" + ordinary.hex())

    rpc = _BatchRpc([result])
    diagnostics = {}
    quotes = await quote_balancer_given_in_many(
        rpc,
        "0x" + "11" * 20,
        [("0x" + "22" * 32, "0x" + "33" * 20, "0x" + "44" * 20, 100)],
        diagnostics=diagnostics,
    )

    assert quotes == [None]
    assert diagnostics["failure_reasons"] == {"unexpected_input_delta": 1}
    assert diagnostics.get("query_revert_decoded", 0) == 0
