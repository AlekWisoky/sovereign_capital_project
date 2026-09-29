import asyncio

import aiohttp
import pytest

from victor_ai_bot.rpc_manager import EndpointStats, RpcManager


class _BuggyStopEvent:
    def set(self):
        return None


class _SafeTask:
    async def __await_impl(self):
        raise asyncio.TimeoutError()

    def __await__(self):
        return self.__await_impl().__await__()


class _ProbeRpc:
    def __init__(self, url, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def block_number(self):
        return None


@pytest.mark.asyncio
async def test_rpc_manager_stop_swallows_expected_timeout(monkeypatch):
    mgr = RpcManager(rpc_read=['http://r'], rpc_send=['http://s'])
    mgr._task = _SafeTask()
    mgr._stop = _BuggyStopEvent()
    await mgr.stop()


@pytest.mark.asyncio
async def test_rpc_manager_stop_does_not_swallow_unexpected_bug(monkeypatch):
    class _BuggyTask:
        async def __await_impl(self):
            raise LookupError('task bug')

        def __await__(self):
            return self.__await_impl().__await__()

    mgr = RpcManager(rpc_read=['http://r'], rpc_send=['http://s'])
    mgr._task = _BuggyTask()
    mgr._stop = _BuggyStopEvent()
    with pytest.raises(LookupError):
        await mgr.stop()


@pytest.mark.asyncio
async def test_probe_one_marks_expected_failures_unhealthy(monkeypatch):
    monkeypatch.setattr('victor_ai_bot.rpc_manager.JsonRpcClient', _ProbeRpc)
    mgr = RpcManager(rpc_read=['http://r'], rpc_send=['http://s'])
    stats = EndpointStats('http://r')
    await mgr._probe_one('http://r', stats)
    assert stats.ok is False
    assert stats.failures == 1
    assert 'block_number failed' in (stats.last_error or '')


@pytest.mark.asyncio
async def test_probe_one_handles_expected_client_error(monkeypatch):
    class _ClientErrorRpc(_ProbeRpc):
        async def block_number(self):
            raise aiohttp.ClientError('down')

    monkeypatch.setattr('victor_ai_bot.rpc_manager.JsonRpcClient', _ClientErrorRpc)
    mgr = RpcManager(rpc_read=['http://r'], rpc_send=['http://s'])
    stats = EndpointStats('http://r')
    await mgr._probe_one('http://r', stats)
    assert stats.ok is False
    assert stats.failures == 1
    assert 'down' in (stats.last_error or '')


@pytest.mark.asyncio
async def test_probe_one_does_not_swallow_unexpected_bug(monkeypatch):
    class _BuggyRpc(_ProbeRpc):
        async def block_number(self):
            raise LookupError('boom')

    monkeypatch.setattr('victor_ai_bot.rpc_manager.JsonRpcClient', _BuggyRpc)
    mgr = RpcManager(rpc_read=['http://r'], rpc_send=['http://s'])
    stats = EndpointStats('http://r')
    with pytest.raises(LookupError):
        await mgr._probe_one('http://r', stats)


@pytest.mark.asyncio
async def test_rpc_manager_loop_awaits_stop_event_without_leaking_coroutine():
    mgr = RpcManager(
        rpc_read=['http://r'],
        rpc_send=['http://s'],
        probe_interval_s=60.0,
    )

    async def _probe_and_stop(url, stats):
        mgr._stop.set()

    mgr._probe_one = _probe_and_stop
    await mgr._loop()
    assert mgr._stop.is_set()


def test_quote_rate_limit_temporarily_demotes_selected_read_provider():
    mgr = RpcManager(
        rpc_read=["https://rpc-a.example", "https://rpc-b.example"],
        rpc_send=["https://rpc-a.example"],
    )
    mgr._read["https://rpc-a.example"].last_seen_block = 100
    mgr._read["https://rpc-b.example"].last_seen_block = 100
    assert mgr.best_read() == "https://rpc-a.example"
    mgr.observe_quote_telemetry(
        "https://rpc-a.example",
        requests=10,
        successes=2,
        failure_reasons={"rpc_rate_limited": 8},
    )
    assert mgr.best_read() == "https://rpc-b.example"
    snap = mgr.snapshot()
    row = next(x for x in snap["read"] if x["url"] == "https://rpc-a.example")
    assert row["quote_failures"] == 8
    assert row["quote_last_error"] == "rpc_rate_limited"


def test_quote_reverts_do_not_demote_rpc_provider():
    mgr = RpcManager(
        rpc_read=["https://rpc-a.example", "https://rpc-b.example"],
        rpc_send=["https://rpc-a.example"],
    )
    mgr._read["https://rpc-a.example"].last_seen_block = 100
    mgr._read["https://rpc-b.example"].last_seen_block = 100
    mgr.observe_quote_telemetry(
        "https://rpc-a.example",
        requests=10,
        successes=2,
        failure_reasons={"rpc_revert": 8},
    )
    assert mgr.best_read() == "https://rpc-a.example"
    row = next(x for x in mgr.snapshot()["read"] if x["url"] == "https://rpc-a.example")
    assert row["quote_failures"] == 0
    assert row["quote_last_error"] is None
