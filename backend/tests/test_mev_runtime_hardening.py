import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

import victor_ai_bot.aqe.mev.runtime as mev_runtime_module
from victor_ai_bot.aqe.mev.models import MEVConfig
from victor_ai_bot.aqe.mev.runtime import MEVRuntime

ROOT = Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'aqe' / 'mev'


class _FakeMonitor:
    def __init__(self, hashes):
        self._hashes = list(hashes)
        self.status = SimpleNamespace(connected=True, ws_url='ws://demo', last_error='')

    async def stop(self):
        return None

    async def iter_hashes(self):
        for item in self._hashes:
            yield item


class _FakeRpcClient:
    def __init__(self, txd):
        self._txd = txd

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_tx_by_hash(self, tx_hash):
        return dict(self._txd)


def _runtime(*, txd, hashes=None) -> MEVRuntime:
    runtime = MEVRuntime(cfg=MEVConfig(enabled=True, max_pending=4), ws_urls=['ws://demo'], rpc_http_url='http://rpc')
    runtime._monitor = _FakeMonitor(hashes or ['0xabc'])
    return runtime


@pytest.mark.asyncio
async def test_parse_failures_are_recorded_and_contained(monkeypatch):
    runtime = _runtime(txd={'to': '0x1', 'nonce': '0xzz', 'input': '0x1234'})
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient({'to': '0x1', 'nonce': '0xzz', 'input': '0x1234'}))

    await runtime._loop()

    assert runtime._last_error.startswith('parse_failed:ValueError:')
    assert runtime.state()['pending_count'] == 0


@pytest.mark.asyncio
async def test_bus_update_value_error_is_safely_ignored(monkeypatch):
    txd = {
        'to': '0x1111111111111111111111111111111111111111',
        'from': '0x2222222222222222222222222222222222222222',
        'nonce': '0x1',
        'value': '0x0',
        'gas': '0x5208',
        'gasPrice': '0x3b9aca00',
        'input': '0x38ed1739',
    }
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('ignore me')))

    await runtime._loop()

    st = runtime.state()
    assert st['pending_count'] == 1
    assert st['last_error'] == ''


@pytest.mark.asyncio
async def test_bus_update_programmer_bug_is_not_swallowed(monkeypatch):
    txd = {
        'to': '0x1111111111111111111111111111111111111111',
        'from': '0x2222222222222222222222222222222222222222',
        'nonce': '0x1',
        'value': '0x0',
        'gas': '0x5208',
        'gasPrice': '0x3b9aca00',
        'input': '0x38ed1739',
    }
    runtime = _runtime(txd=txd)
    monkeypatch.setattr(mev_runtime_module, 'JsonRpcClient', lambda *args, **kwargs: _FakeRpcClient(txd))
    monkeypatch.setattr(mev_runtime_module.BUS, 'update', lambda *args, **kwargs: (_ for _ in ()).throw(NameError('bus bug')))

    with pytest.raises(NameError):
        await runtime._loop()


@pytest.mark.asyncio
async def test_stop_cancels_task_without_swallowing(monkeypatch):
    runtime = _runtime(txd={'to': '0x1'})

    class _FakeTask:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True
            return True

    runtime._task = _FakeTask()
    await runtime.stop()
    assert runtime._task.cancelled is True


def test_mev_runtime_module_has_no_broad_exception_handlers():
    module = ast.parse((ROOT / 'runtime.py').read_text(encoding='utf-8'))
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
