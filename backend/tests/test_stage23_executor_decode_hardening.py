from __future__ import annotations

import pytest

from victor_ai_bot.abi_utils import decode_revert_data
from victor_ai_bot.executor_events import ARB_EXECUTED_TOPIC0, decode_arb_executed
from victor_ai_bot.executor_version import fetch_executor_version
from victor_ai_bot.rpc import RpcResult


class _RpcString:
    async def eth_call(self, to, data, *, block="latest"):
        return "0x" + (1).to_bytes(32, "big").hex() + (7).to_bytes(32, "big").hex()


class _RpcResultOk:
    async def eth_call(self, to, data, *, block="latest"):
        return RpcResult(ok=True, result="0x" + (2).to_bytes(32, "big").hex() + (9).to_bytes(32, "big").hex())


class _RpcResultErr:
    async def eth_call(self, to, data, *, block="latest"):
        return RpcResult(ok=False, error={"code": -32000})


class _RpcBug:
    async def eth_call(self, to, data, *, block="latest"):
        raise RuntimeError("unexpected bug")


class _BadLog(dict):
    def get(self, key, default=None):
        raise RuntimeError("unexpected get bug")


@pytest.mark.asyncio
async def test_fetch_executor_version_supports_rpcresult_and_legacy_string():
    assert await fetch_executor_version(_RpcString(), executor_address="0xabc") == (1, 7)
    assert await fetch_executor_version(_RpcResultOk(), executor_address="0xabc") == (2, 9)


@pytest.mark.asyncio
async def test_fetch_executor_version_returns_none_for_failed_or_malformed_result():
    assert await fetch_executor_version(_RpcResultErr(), executor_address="0xabc") is None

    class _RpcMalformed:
        async def eth_call(self, to, data, *, block="latest"):
            return RpcResult(ok=True, result="0xzz")

    assert await fetch_executor_version(_RpcMalformed(), executor_address="0xabc") is None


@pytest.mark.asyncio
async def test_fetch_executor_version_does_not_swallow_unexpected_rpc_bug():
    with pytest.raises(RuntimeError, match="unexpected bug"):
        await fetch_executor_version(_RpcBug(), executor_address="0xabc")


def test_decode_arb_executed_handles_valid_and_invalid_logs():
    route_id = "0x" + "11" * 32
    token_topic = "0x" + ("00" * 12) + ("22" * 20)
    data = (
        (123).to_bytes(32, "big")
        + (45).to_bytes(32, "big")
        + (3).to_bytes(32, "big")
    ).hex()
    log = {"topics": [ARB_EXECUTED_TOPIC0, route_id, token_topic], "data": "0x" + data}
    evt = decode_arb_executed(log)
    assert evt is not None
    assert evt.amount_borrowed == 123
    assert evt.profit == 45
    assert evt.provider == 3
    assert evt.token == "0x" + ("22" * 20)

    assert decode_arb_executed({"topics": [ARB_EXECUTED_TOPIC0], "data": "0x"}) is None
    assert decode_arb_executed({"topics": [ARB_EXECUTED_TOPIC0, route_id, token_topic], "data": "0xzz"}) is None


def test_decode_arb_executed_does_not_swallow_unexpected_bug():
    with pytest.raises(RuntimeError, match="unexpected get bug"):
        decode_arb_executed(_BadLog())


def test_decode_revert_data_invalid_hex_and_error_string_decode():
    assert decode_revert_data("0xzz").kind == "Unknown"

    msg = "executor vetoed"
    msg_bytes = msg.encode("utf-8")
    padded = msg_bytes + (b"\x00" * ((32 - (len(msg_bytes) % 32)) % 32))
    payload = (
        bytes.fromhex("08c379a0")
        + (32).to_bytes(32, "big")
        + len(msg_bytes).to_bytes(32, "big")
        + padded
    )
    dec = decode_revert_data("0x" + payload.hex())
    assert dec.kind == "Error"
    assert dec.message == msg
