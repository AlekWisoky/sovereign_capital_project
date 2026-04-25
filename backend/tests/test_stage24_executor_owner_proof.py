from __future__ import annotations

import pytest

from victor_ai_bot.executor_owner import fetch_executor_owner, validate_executor_owner_proof
from victor_ai_bot.rpc import RpcResult


class _RpcOwnerResult:
    async def eth_call(self, to, data, *, block="latest"):
        return RpcResult(
            True, result="0x" + ("0" * 24) + "3333333333333333333333333333333333333333"
        )


class _RpcOwnerString:
    async def eth_call(self, to, data, *, block="latest"):
        return "0x" + ("0" * 24) + "4444444444444444444444444444444444444444"


class _RpcOwnerMalformed:
    async def eth_call(self, to, data, *, block="latest"):
        return RpcResult(True, result="0x1234")


class _RpcBug:
    async def eth_call(self, to, data, *, block="latest"):
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_fetch_executor_owner_supports_rpcresult_and_legacy_string():
    assert await fetch_executor_owner(_RpcOwnerResult(), executor_address="0xabc") == "0x3333333333333333333333333333333333333333"
    assert await fetch_executor_owner(_RpcOwnerString(), executor_address="0xabc") == "0x4444444444444444444444444444444444444444"


@pytest.mark.asyncio
async def test_fetch_executor_owner_returns_none_for_failed_or_malformed_result():
    assert await fetch_executor_owner(_RpcOwnerMalformed(), executor_address="0xabc") is None


@pytest.mark.asyncio
async def test_validate_executor_owner_proof_returns_lookup_failed_or_mismatch():
    assert await validate_executor_owner_proof(
        _RpcOwnerMalformed(), executor_address="0xabc", signer_address="0x3333333333333333333333333333333333333333"
    ) == ("executor_owner_lookup_failed", None)
    assert await validate_executor_owner_proof(
        _RpcOwnerResult(), executor_address="0xabc", signer_address="0x5555555555555555555555555555555555555555"
    ) == ("executor_owner_mismatch", "0x3333333333333333333333333333333333333333")


@pytest.mark.asyncio
async def test_fetch_executor_owner_does_not_swallow_unexpected_rpc_bug():
    with pytest.raises(RuntimeError, match="boom"):
        await fetch_executor_owner(_RpcBug(), executor_address="0xabc")
