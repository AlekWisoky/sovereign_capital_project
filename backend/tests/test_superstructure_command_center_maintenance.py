from __future__ import annotations

import os

from victor_ai_bot.superstructure.command_center import CommandCenter
from victor_ai_bot.superstructure.runtime import SuperstructureRuntime


def test_command_center_reports_audit_append_failure(monkeypatch, tmp_path):
    cc = CommandCenter(data_dir=str(tmp_path), chain='eth')

    def _boom(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(os, 'open', _boom)
    cc.set_risk_multiplier(0.5)
    snap = cc.snapshot()
    assert snap['risk_multiplier'] == 0.5
    assert snap['storage']['audit']['ok'] is False
    assert snap['storage']['audit']['last_error_code'] == 'audit_append_failed'
    assert snap['storage']['degraded'] is True


def test_command_center_reports_bus_publish_failure(monkeypatch, tmp_path):
    cc = CommandCenter(data_dir=str(tmp_path), chain='eth')

    def _boom(bucket: str, payload: dict) -> None:
        raise ValueError(f'boom:{bucket}')

    monkeypatch.setattr(cc, '_publish', _boom)
    cc.set_directive({'mode': 'safe'}, ttl_s=60)
    snap = cc.snapshot()
    assert snap['directive']['mode'] == 'safe'
    assert snap['storage']['bus']['ok'] is False
    assert snap['storage']['bus']['last_error_code'] == 'bus_publish_failed'
    assert snap['storage']['degraded'] is True


def test_superstructure_runtime_state_surfaces_command_center_storage(monkeypatch, tmp_path):
    runtime = SuperstructureRuntime(
        cfg={
            'enabled': True,
            'human_enabled': True,
            'enable_stability_monitor': False,
            'gmao_enabled': False,
        },
        chain='eth',
        data_dir=str(tmp_path),
    )
    assert runtime.command is not None

    def _boom(*args, **kwargs):
        raise OSError('readonly fs')

    monkeypatch.setattr(os, 'open', _boom)
    runtime.command.set_exploration_cap(0.2)
    state = runtime.state()
    storage = state['command_center']['storage']
    assert state['command_center']['exploration_cap'] == 0.2
    assert storage['audit']['ok'] is False
    assert storage['audit']['last_error_code'] == 'audit_append_failed'
    assert storage['degraded'] is True
