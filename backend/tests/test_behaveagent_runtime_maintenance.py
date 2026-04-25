from __future__ import annotations

from pathlib import Path

import victor_ai_bot.behaveagent.calibration as calibration_mod
from victor_ai_bot.behaveagent.config import BehaveAgentConfig
from victor_ai_bot.behaveagent.runtime import BehaveAgentRuntime


def _cfg(tmp_path: Path, **overrides):
    base = dict(
        enabled=True,
        regime_memory_path=str(tmp_path / 'regime_memory.json'),
        strategy_memory_path=str(tmp_path / 'strategy_memory.json'),
        reasoning_log_dir=str(tmp_path / 'reasoning'),
    )
    base.update(overrides)
    return BehaveAgentConfig(**base)


def test_behaveagent_report_state_exposes_invalid_storage_files(tmp_path):
    (tmp_path / 'regime_memory.json').write_text('{bad json', encoding='utf-8')
    (tmp_path / 'strategy_memory.json').write_text('{bad json', encoding='utf-8')

    runtime = BehaveAgentRuntime(_cfg(tmp_path), data_dir=str(tmp_path))
    state = runtime.report_state()

    assert state['storage']['degraded'] is True
    assert state['storage']['regime_memory']['load']['reasonCode'] == 'regime_memory_invalid_json'
    assert state['storage']['strategy_memory']['load']['reasonCode'] == 'strategy_memory_invalid_json'


def test_behaveagent_report_state_exposes_reasoning_log_append_failure(tmp_path):
    runtime = BehaveAgentRuntime(_cfg(tmp_path), data_dir=str(tmp_path))
    bad_path = tmp_path / 'reasoning-blocked'
    bad_path.mkdir()
    runtime.logger.path = str(bad_path)

    out = runtime.governance_check(
        intent_id='abc',
        tier='standard',
        risk_profile='low',
        decision_factors={'a': 1, 'b': 2},
        simulation_result={'ok': True},
    )
    state = runtime.report_state()

    assert out['ok'] is True
    assert state['storage']['degraded'] is True
    assert state['storage']['reasoning_log']['append']['reasonCode'] == 'reasoning_append_failed'


def test_behaveagent_report_state_exposes_calibration_save_failure(monkeypatch, tmp_path):
    runtime = BehaveAgentRuntime(_cfg(tmp_path), data_dir=str(tmp_path))
    runtime.analyze_market(features={'basefee_gwei': 10.0, 'mev_risk': 0.1, 'pending_rate': 10.0, 'volatility_proxy': 0.2})

    def _boom(src: str, dst: str) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(calibration_mod.os, 'replace', _boom)
    runtime.observe_outcome(strategy_type='dex_flash_2leg', reward=1.5, ok=True)
    state = runtime.report_state()

    assert state['storage']['degraded'] is True
    assert state['storage']['calibration']['save']['reasonCode'] == 'calibration_save_failed'
