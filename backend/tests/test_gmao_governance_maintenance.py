from __future__ import annotations

import os

from victor_ai_bot.superstructure.runtime import SuperstructureRuntime
from victor_ai_bot.caq_kds.bus import BUS


def _make_runtime(tmp_path):
    runtime = SuperstructureRuntime(
        cfg={
            'enabled': True,
            'human_enabled': True,
            'enable_stability_monitor': False,
            'gmao_enabled': True,
        },
        chain='eth',
        data_dir=str(tmp_path),
    )
    assert runtime.governance is not None
    return runtime


def test_gmao_governance_reports_invalid_state_json(tmp_path):
    state_dir = tmp_path / 'superstructure'
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / 'governance_state_eth.json').write_text('{bad json', encoding='utf-8')

    runtime = _make_runtime(tmp_path)
    snap = runtime.governance.snapshot()
    storage = snap['storage']

    assert storage['state']['load']['ok'] is False
    assert storage['state']['load']['lastErrorCode'] == 'state_load_invalid_json'
    assert storage['degraded'] is True


def test_gmao_governance_reports_command_center_guardrail_failure(monkeypatch, tmp_path):
    runtime = _make_runtime(tmp_path)

    monkeypatch.setattr(BUS, 'snapshot', lambda: {'reliability': {'data': {'max_drawdown': 0.9}}})

    def _boom(*args, **kwargs):
        raise ValueError('command unavailable')

    assert runtime.command is not None
    monkeypatch.setattr(runtime.command, 'set_exploration_cap', _boom)

    out = runtime.governance.wrapper_execution(
        core_command='rebalance',
        agent_id='agent-1',
        risk_level=0.2,
        proposal_id='p-1',
    )
    snap = runtime.governance.snapshot()
    storage = snap['storage']

    assert out['allow'] is False
    assert out['risk_emergency_mode'] == 'ON'
    assert storage['command']['ok'] is False
    assert storage['command']['lastErrorCode'] == 'command_center_update_failed'
    assert storage['degraded'] is True


def test_gmao_governance_reports_bus_publish_failure(monkeypatch, tmp_path):
    runtime = _make_runtime(tmp_path)

    monkeypatch.setattr(BUS, 'snapshot', lambda: {})

    def _boom(bucket: str, payload: dict) -> None:
        raise ValueError(f'boom:{bucket}')

    monkeypatch.setattr(BUS, 'update', _boom)

    out = runtime.governance.wrapper_execution(
        core_command='status',
        agent_id='agent-2',
        risk_level=0.1,
        proposal_id='p-2',
    )
    snap = runtime.governance.snapshot()
    storage = snap['storage']

    assert out['ok'] is True
    assert storage['bus']['publish']['ok'] is False
    assert storage['bus']['publish']['lastErrorCode'] == 'governance_publish_failed'
    assert storage['degraded'] is True
