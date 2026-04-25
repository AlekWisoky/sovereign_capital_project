from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_core.bootstrap import make_runtime_lifespan


class _OkRuntime:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


class _FailingStartRuntime:
    def start(self) -> None:
        raise RuntimeError('start_failed')

    async def stop(self) -> None:
        return None


class _FailingStopRuntime:
    def start(self) -> None:
        return None

    async def stop(self) -> None:
        raise OSError('stop_failed')


@pytest.mark.asyncio
async def test_lifespan_records_successful_start_and_stop(monkeypatch):
    monkeypatch.setenv('VICTOR_AUTOSTART', '1')
    runtime = _OkRuntime()
    app = SimpleNamespace(state=SimpleNamespace(runtime=runtime))

    async with make_runtime_lifespan()(app):
        lifecycle = app.state.runtime_lifecycle
        assert lifecycle['autostart']['status'] == 'enabled'
        assert lifecycle['start']['status'] == 'ok'
        assert runtime.started is True

    lifecycle = app.state.runtime_lifecycle
    assert lifecycle['stop']['status'] == 'ok'
    assert runtime.stopped is True


@pytest.mark.asyncio
async def test_lifespan_records_start_failure_without_crashing(monkeypatch):
    monkeypatch.setenv('VICTOR_AUTOSTART', '1')
    app = SimpleNamespace(state=SimpleNamespace(runtime=_FailingStartRuntime()))

    async with make_runtime_lifespan()(app):
        lifecycle = app.state.runtime_lifecycle
        assert lifecycle['start']['status'] == 'failed'
        assert lifecycle['start']['error_type'] == 'RuntimeError'
        assert lifecycle['start']['error'] == 'start_failed'

    assert app.state.runtime_lifecycle['stop']['status'] == 'ok'


@pytest.mark.asyncio
async def test_lifespan_records_stop_failure_without_crashing(monkeypatch):
    monkeypatch.setenv('VICTOR_AUTOSTART', '0')
    app = SimpleNamespace(state=SimpleNamespace(runtime=_FailingStopRuntime()))

    async with make_runtime_lifespan()(app):
        lifecycle = app.state.runtime_lifecycle
        assert lifecycle['autostart']['status'] == 'disabled'
        assert lifecycle['start']['status'] == 'skipped'

    lifecycle = app.state.runtime_lifecycle
    assert lifecycle['stop']['status'] == 'failed'
    assert lifecycle['stop']['error_type'] == 'OSError'
    assert lifecycle['stop']['error'] == 'stop_failed'


@pytest.mark.asyncio
async def test_lifespan_records_missing_runtime_as_skipped_stop(monkeypatch):
    monkeypatch.delenv('VICTOR_AUTOSTART', raising=False)
    app = SimpleNamespace(state=SimpleNamespace())

    async with make_runtime_lifespan()(app):
        assert app.state.runtime_lifecycle['start']['status'] == 'skipped'

    assert app.state.runtime_lifecycle['stop']['status'] == 'skipped'
