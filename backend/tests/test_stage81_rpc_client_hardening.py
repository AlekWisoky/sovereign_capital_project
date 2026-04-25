import asyncio

import aiohttp
import pytest

from victor_ai_bot.rpc import JsonRpcClient


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


class _Ctx:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        if self._exc is not None:
            raise self._exc
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Session:
    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    def post(self, *args, **kwargs):
        return _Ctx(self._response, self._exc)


@pytest.mark.asyncio
async def test_call_expected_client_error_degrades_to_rpc_result():
    client = JsonRpcClient("http://rpc")
    client._session = _Session(exc=aiohttp.ClientError("boom"))

    result = await client.call("eth_blockNumber")

    assert result.ok is False
    assert "boom" in str(result.error)
    assert result.latency_ms is not None


class _BuggySession:
    def post(self, *args, **kwargs):
        raise LookupError("unexpected_post_bug")


@pytest.mark.asyncio
async def test_call_unexpected_bug_propagates():
    client = JsonRpcClient("http://rpc")
    client._session = _BuggySession()

    with pytest.raises(LookupError, match="unexpected_post_bug"):
        await client.call("eth_blockNumber")


@pytest.mark.asyncio
async def test_batch_bad_response_id_is_skipped_safely():
    client = JsonRpcClient("http://rpc")
    client._session = _Session(response=_JsonResponse([{"id": "bad", "result": "0x1"}]))

    results = await client.batch([("eth_blockNumber", [])])

    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].error == "missing_batch_response"


@pytest.mark.asyncio
async def test_batch_expected_client_error_degrades_per_chunk():
    client = JsonRpcClient("http://rpc")
    client._session = _Session(exc=aiohttp.ClientError("batch_boom"))

    results = await client.batch([("eth_blockNumber", []), ("eth_chainId", [])])

    assert len(results) == 2
    assert all(r.ok is False for r in results)
    assert all("batch_boom" in str(r.error) for r in results)


@pytest.mark.asyncio
async def test_batch_unexpected_bug_propagates():
    client = JsonRpcClient("http://rpc")
    client._session = _BuggySession()

    with pytest.raises(LookupError, match="unexpected_post_bug"):
        await client.batch([("eth_blockNumber", [])])
