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

@pytest.mark.asyncio
async def test_batch_supported_chunks_run_concurrently_and_preserve_order():
    class _ConcurrentSession:
        def __init__(self):
            self.active = 0
            self.max_active = 0

        def post(self, *args, **kwargs):
            return _ConcurrentCtx(self, kwargs["json"])

    class _ConcurrentCtx:
        def __init__(self, owner, payload):
            self.owner = owner
            self.payload = payload

        async def __aenter__(self):
            self.owner.active += 1
            self.owner.max_active = max(self.owner.max_active, self.owner.active)
            await asyncio.sleep(0.01)
            return _JsonResponse([
                {"id": req["id"], "result": hex(req["id"])}
                for req in self.payload
            ])

        async def __aexit__(self, exc_type, exc, tb):
            self.owner.active -= 1
            return False

    session = _ConcurrentSession()
    client = JsonRpcClient(
        "http://rpc",
        max_concurrency=4,
        max_batch=2,
        max_batch_concurrency=2,
    )
    client._session = session

    results = await client.batch([
        ("eth_blockNumber", []),
        ("eth_chainId", []),
        ("eth_gasPrice", []),
        ("eth_blockNumber", []),
        ("eth_chainId", []),
        ("eth_gasPrice", []),
    ])

    assert [r.result for r in results] == ["0x1", "0x2", "0x3", "0x4", "0x5", "0x6"]
    assert session.max_active == 2



@pytest.mark.asyncio
async def test_batch_http_429_splits_large_batch_without_inflating_failures(monkeypatch):
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MIN_BATCH", "8")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MAX_SPLITS", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_BACKOFF_MS", "0")

    class _Response:
        def __init__(self, status, payload=None, json_error=None):
            self.status = status
            self.payload = payload
            self.json_error = json_error

        async def json(self):
            if self.json_error is not None:
                raise self.json_error
            return self.payload

    class _RateLimitSession:
        def __init__(self):
            self.batch_sizes = []

        def post(self, *args, **kwargs):
            payload = kwargs["json"]
            self.batch_sizes.append(len(payload))
            if len(payload) > 8:
                return _Ctx(
                    response=_Response(
                        429, json_error=aiohttp.ClientError("rate limited")
                    )
                )
            return _Ctx(
                response=_Response(
                    200,
                    payload=[
                        {"id": req["id"], "result": hex(req["id"])}
                        for req in payload
                    ],
                )
            )

    session = _RateLimitSession()
    client = JsonRpcClient("http://rpc", max_concurrency=4, max_batch=16)
    client._session = session

    results = await client.batch([("eth_call", [{}]) for _ in range(16)])

    assert len(results) == 16
    assert all(result.ok for result in results)
    assert session.batch_sizes == [16, 8, 8]


@pytest.mark.asyncio
async def test_batch_json_rpc_rate_limit_error_splits_only_fully_limited_batch(monkeypatch):
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MIN_BATCH", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MAX_SPLITS", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_BACKOFF_MS", "0")

    class _Response:
        def __init__(self, payload):
            self.status = 200
            self.payload = payload

        async def json(self):
            return self.payload

    class _Session:
        def __init__(self):
            self.batch_sizes = []

        def post(self, *args, **kwargs):
            payload = kwargs["json"]
            self.batch_sizes.append(len(payload))
            if len(payload) > 4:
                body = [
                    {
                        "id": req["id"],
                        "error": {"code": -32016, "message": "rate limit"},
                    }
                    for req in payload
                ]
            else:
                body = [
                    {"id": req["id"], "result": hex(req["id"])}
                    for req in payload
                ]
            return _Ctx(response=_Response(body))

    session = _Session()
    client = JsonRpcClient("http://rpc", max_concurrency=4, max_batch=16)
    client._session = session

    results = await client.batch([("eth_call", [{}]) for _ in range(16)])

    assert len(results) == 16
    assert all(result.ok for result in results)
    assert session.batch_sizes == [16, 8, 4, 4, 8, 4, 4]
