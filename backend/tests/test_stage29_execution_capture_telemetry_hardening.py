import json
from pathlib import Path

import pytest

from victor_ai_bot.execution_capture import telemetry as telemetry_mod
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore


def test_invalid_json_load_degrades_to_blank_state(tmp_path):
    path = tmp_path / "execution_capture"
    path.mkdir(parents=True, exist_ok=True)
    (path / "telemetry_eth.json").write_text('{not json', encoding='utf-8')

    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')

    assert store.summary('route_family', 'missing')['attempts'] == 0.0
    assert store.analytics_series() == {'laneSuccess': [], 'venueQuality': []}


def test_unexpected_json_loader_bug_is_not_swallowed(tmp_path, monkeypatch):
    path = tmp_path / "execution_capture"
    path.mkdir(parents=True, exist_ok=True)
    (path / "telemetry_eth.json").write_text('{}', encoding='utf-8')

    def boom(*args, **kwargs):
        raise KeyboardInterrupt('unexpected')

    monkeypatch.setattr(telemetry_mod.json, 'load', boom)

    with pytest.raises(KeyboardInterrupt):
        ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')


def test_malformed_numeric_fields_degrade_per_field(tmp_path):
    path = tmp_path / "execution_capture"
    path.mkdir(parents=True, exist_ok=True)
    payload = {
        'updated_ts': 1,
        'lane': {
            'PRIVATE': {
                'attempts': 'bad',
                'sample_count': None,
                'successes': '2x',
                'stales': {},
                'timeouts': [],
                'reverts': object().__class__.__name__,
                'drops': 'nanx',
                'slippage_delta_bps_sum': 'oops',
                'quote_drift_bps_sum': 'oops',
                'latency_ms_sum': 'oops',
                'realized_pnl_usd_sum': 'oops',
                'expected_pnl_usd_sum': 'oops',
            }
        },
    }
    (path / "telemetry_eth.json").write_text(json.dumps(payload), encoding='utf-8')

    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    summary = store.summary('lane', 'PRIVATE')

    assert summary['attempts'] == 0.0
    assert summary['success_rate'] == 0.65
    assert summary['avg_latency_ms'] == 0.0
    assert summary['avg_realized_pnl_usd'] == 0.0
