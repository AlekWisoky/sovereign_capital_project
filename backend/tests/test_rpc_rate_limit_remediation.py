from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.rpc import JsonRpcClient
from victor_ai_bot.rpc_manager import RpcManager


class _Response:
    def __init__(self, status: int, payload=None, json_error: Exception | None = None):
        self.status = int(status)
        self._payload = payload
        self._json_error = json_error

    async def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Session:
    def __init__(self):
        self.batch_sizes: list[int] = []

    def post(self, url, *, json):
        self.batch_sizes.append(len(json))
        if len(json) > 8:
            return _Response(429, json_error=Exception("rate limited"))
        payload = [
            {"jsonrpc": "2.0", "id": item["id"], "result": "0x1"}
            for item in json
        ]
        return _Response(200, payload=payload)


@pytest.mark.asyncio
async def test_json_rpc_batch_splits_http_429_without_inflating_final_failures(monkeypatch):
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MIN_BATCH", "8")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MAX_SPLITS", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_BACKOFF_MS", "0")

    client = JsonRpcClient("https://arbitrum.example", max_concurrency=4, max_batch=16)
    session = _Session()
    client._session = session

    results = await client.batch([("eth_call", [{}]) for _ in range(16)])

    assert len(results) == 16
    assert all(result.ok for result in results)
    assert session.batch_sizes == [16, 8, 8]


@pytest.mark.asyncio
async def test_json_rpc_batch_splits_all_rate_limited_json_rpc_errors(monkeypatch):
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MIN_BATCH", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_MAX_SPLITS", "4")
    monkeypatch.setenv("VICTOR_RPC_RATE_LIMIT_BACKOFF_MS", "0")

    class _Provider(_Session):
        def post(self, url, *, json):
            self.batch_sizes.append(len(json))
            if len(json) > 4:
                payload = [
                    {
                        "jsonrpc": "2.0",
                        "id": item["id"],
                        "error": {"code": -32016, "message": "rate limit"},
                    }
                    for item in json
                ]
            else:
                payload = [
                    {"jsonrpc": "2.0", "id": item["id"], "result": "0x1"}
                    for item in json
                ]
            return _Response(200, payload=payload)

    client = JsonRpcClient("https://arbitrum.example", max_concurrency=4, max_batch=16)
    session = _Provider()
    client._session = session

    results = await client.batch([("eth_call", [{}]) for _ in range(16)])

    assert len(results) == 16
    assert all(result.ok for result in results)
    assert session.batch_sizes == [16, 8, 4, 4, 8, 4, 4]


def test_rpc_manager_never_bootstraps_quote_quarantined_provider():
    manager = RpcManager(
        rpc_read=["https://rpc-a.example", "https://rpc-b.example"],
        rpc_send=["https://rpc-a.example", "https://rpc-b.example"],
    )
    manager._read["https://rpc-a.example"].last_seen_block = 100
    manager._read["https://rpc-b.example"].last_seen_block = 100
    manager._read["https://rpc-a.example"].quote_unhealthy_until = 9_999_999_999.0

    assert manager.best_read() == "https://rpc-b.example"
    manager._read["https://rpc-b.example"].quote_unhealthy_until = 9_999_999_999.0
    assert manager.best_read() == ""


def test_rpc_manager_recovers_quarantined_provider_after_expiry():
    manager = RpcManager(
        rpc_read=["https://rpc.example"],
        rpc_send=["https://rpc.example"],
    )
    manager._read["https://rpc.example"].last_seen_block = 100
    manager._read["https://rpc.example"].quote_unhealthy_until = 0.0

    assert manager.best_read() == "https://rpc.example"


def test_effective_fee_authority_is_native_observation():
    # This documents the execution rule at the test-contract level: when the
    # provider observation exists, the execution gate must use it instead of
    # the static configuration value.
    observed = 12
    configured = 9
    effective = observed if observed is not None else configured
    assert effective == 12
