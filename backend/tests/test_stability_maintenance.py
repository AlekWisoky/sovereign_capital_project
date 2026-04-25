from pathlib import Path

import victor_ai_bot.superstructure.stability as stability_mod
from victor_ai_bot.superstructure.stability import OrgStabilityMonitor


def test_stability_monitor_has_no_broad_exception_handlers():
    text = (Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'superstructure' / 'stability.py').read_text(encoding='utf-8')
    assert 'except Exception' not in text


def test_stability_compute_marks_bus_degradation(monkeypatch, tmp_path):
    mon = OrgStabilityMonitor(data_dir=str(tmp_path), chain='eth', window_s=120.0)

    def _boom(*args, **kwargs):
        raise RuntimeError('bus offline')

    monkeypatch.setattr(stability_mod.BUS, 'update', _boom)
    snap = mon.compute()
    state = mon.state()
    last = mon.last()

    assert snap.ok is True
    assert state['bus']['ok'] is False
    assert state['bus']['last_error_code'] == 'stability_bus_publish_failed'
    assert state['degraded'] is True
    assert last['runtime']['degraded'] is True


def test_stability_compute_marks_storage_degradation(monkeypatch, tmp_path):
    mon = OrgStabilityMonitor(data_dir=str(tmp_path), chain='eth', window_s=120.0)

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(stability_mod.os, 'open', _boom)
    snap = mon.compute()
    state = mon.state()

    assert snap.ok is True
    assert state['storage']['ok'] is False
    assert state['storage']['last_error_code'] == 'stability_write_failed'
    assert state['degraded'] is True


def test_stability_last_marks_snapshot_degradation(tmp_path):
    mon = OrgStabilityMonitor(data_dir=str(tmp_path), chain='eth', window_s=120.0)
    mon._last = object()  # type: ignore[assignment]

    last = mon.last()

    assert last['ok'] is False
    assert last['error'] == 'stability_last_failed'
    assert last['runtime']['snapshot']['ok'] is False
    assert last['runtime']['snapshot']['last_error_code'] == 'stability_last_failed'
    assert last['runtime']['degraded'] is True
