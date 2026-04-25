import ast
import asyncio
import json
from pathlib import Path

import aiohttp
import pytest

import victor_ai_bot.aqe.mev.mempool as mempool_module
from victor_ai_bot.aqe.mev.mempool import MempoolMonitor

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'aqe' / 'mev'


class _FakeTask:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        return True


class _FakeMsg:
    def __init__(self, msg_type, data=''):
        self.type = msg_type
        self.data = data


class _FakeWebSocket:
    def __init__(self, messages):
        self._messages = list(messages)
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def send_str(self, payload: str):
        self.sent.append(payload)

    async def receive(self, timeout=None):
        if not self._messages:
            raise asyncio.CancelledError
        return self._messages.pop(0)


class _FakeClientSession:
    def __init__(self, ws):
        self._ws = ws

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    def ws_connect(self, *args, **kwargs):
        return self._ws


@pytest.mark.asyncio
async def test_stop_cancels_task_without_swallowing():
    monitor = MempoolMonitor(ws_url='ws://demo')
    monitor._task = _FakeTask()

    await monitor.stop()

    assert monitor._task.cancelled is True


@pytest.mark.asyncio
async def test_run_records_expected_ws_errors(monkeypatch):
    monitor = MempoolMonitor(ws_url='ws://demo', reconnect_backoff_s=0.01)

    async def _boom():
        raise RuntimeError('offline')

    async def _sleep(_delay):
        monitor._stop.set()

    monkeypatch.setattr(monitor, '_connect_once', _boom)
    monkeypatch.setattr(mempool_module.asyncio, 'sleep', _sleep)

    await monitor._run()

    assert monitor.status.connected is False
    assert monitor.status.last_error == 'ws_error:RuntimeError:offline'


@pytest.mark.asyncio
async def test_run_does_not_swallow_programmer_bug(monkeypatch):
    monitor = MempoolMonitor(ws_url='ws://demo')

    async def _bug():
        raise NameError('unexpected bug')

    monkeypatch.setattr(monitor, '_connect_once', _bug)

    with pytest.raises(NameError):
        await monitor._run()


@pytest.mark.asyncio
async def test_connect_once_drops_oldest_and_ignores_malformed_payload(monkeypatch):
    monitor = MempoolMonitor(ws_url='ws://demo', max_queue=1)
    monitor.q.put_nowait('0xold')
    fake_ws = _FakeWebSocket(
        [
            _FakeMsg(aiohttp.WSMsgType.TEXT, json.dumps({'result': '0xsub'})),
            _FakeMsg(aiohttp.WSMsgType.TEXT, '{bad json'),
            _FakeMsg(aiohttp.WSMsgType.TEXT, json.dumps({'params': {'result': '0xnew'}})),
            _FakeMsg(aiohttp.WSMsgType.CLOSED),
        ]
    )

    monkeypatch.setattr(mempool_module.aiohttp, 'ClientSession', lambda timeout=None: _FakeClientSession(fake_ws))

    with pytest.raises(RuntimeError, match='ws_closed'):
        await monitor._connect_once()

    assert monitor.status.connected is True
    assert monitor.q.qsize() == 1
    assert list(monitor.q._queue) == ['0xnew']


@pytest.mark.asyncio
async def test_connect_once_ignores_queue_empty_during_evict(monkeypatch):
    monitor = MempoolMonitor(ws_url='ws://demo', max_queue=1)
    monitor.q.put_nowait('0xold')
    fake_ws = _FakeWebSocket(
        [
            _FakeMsg(aiohttp.WSMsgType.TEXT, json.dumps({'result': '0xsub'})),
            _FakeMsg(aiohttp.WSMsgType.TEXT, json.dumps({'params': {'result': '0xnew'}})),
            _FakeMsg(aiohttp.WSMsgType.CLOSED),
        ]
    )

    def _raise_queue_empty():
        raise asyncio.QueueEmpty

    monkeypatch.setattr(monitor.q, 'get_nowait', _raise_queue_empty)
    monkeypatch.setattr(mempool_module.aiohttp, 'ClientSession', lambda timeout=None: _FakeClientSession(fake_ws))

    with pytest.raises(RuntimeError, match='ws_closed'):
        await monitor._connect_once()

    assert monitor.q.qsize() == 1
    assert list(monitor.q._queue) == ['0xold']


def test_mev_mempool_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'mempool.py').read_text(encoding='utf-8'))
    broad = []
    for node in ast.walk(module):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if node.type is None:
            broad.append('bare except')
            continue
        if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
            broad.append('except Exception')
    assert broad == []
