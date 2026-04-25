import builtins
import sqlite3
from pathlib import Path

import pytest

from victor_ai_bot.telemetry.events import TelemetryEvent
from victor_ai_bot.telemetry.store import TelemetryStore


def test_append_degrades_safely_when_sqlite_persist_fails(tmp_path):
    store = TelemetryStore(data_dir=str(tmp_path), chain='eth')

    def boom(**kwargs):
        raise sqlite3.OperationalError('db_locked')

    store._repo.insert = boom
    store.append(TelemetryEvent(event_type='decision', chain='eth', ts_ms=1, payload={'route_family': 'rf'}))

    rows = store.tail(limit=5)
    assert len(rows) == 1
    assert rows[0]['event_type'] == 'decision'
    assert rows[0]['payload']['route_family'] == 'rf'


def test_append_does_not_swallow_unexpected_repo_bug(tmp_path):
    store = TelemetryStore(data_dir=str(tmp_path), chain='eth')

    def boom(**kwargs):
        raise AssertionError('unexpected_repo_bug')

    store._repo.insert = boom
    with pytest.raises(AssertionError, match='unexpected_repo_bug'):
        store.append(TelemetryEvent(event_type='decision', chain='eth', ts_ms=1, payload={'route_family': 'rf'}))


def test_trim_safely_ignores_oserror(tmp_path, monkeypatch):
    store = TelemetryStore(data_dir=str(tmp_path), chain='eth')

    def bad_open(*args, **kwargs):
        raise OSError('io_blocked')

    monkeypatch.setattr(builtins, 'open', bad_open)
    store._trim_if_needed()


def test_trim_does_not_swallow_unexpected_bug(tmp_path, monkeypatch):
    store = TelemetryStore(data_dir=str(tmp_path), chain='eth')
    real_open = builtins.open

    def weird_open(*args, **kwargs):
        if args and args[0] == store.path:
            raise AssertionError('unexpected_trim_bug')
        return real_open(*args, **kwargs)

    monkeypatch.setattr(builtins, 'open', weird_open)
    with pytest.raises(AssertionError, match='unexpected_trim_bug'):
        store._trim_if_needed()
