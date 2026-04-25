from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.system_truth import build_system_truth


class _EvolutionRuntime:
    def meta_state(self):
        raise ValueError('meta_state_unavailable')


def test_system_truth_excludes_private_helper_modules_and_exposes_canonical_counts():
    truth = build_system_truth()

    assert '_route_helpers' not in truth['api_route_modules']
    assert truth['runtime_service_module_count'] == truth['runtime_service_count']
    assert truth['api_route_module_count'] == len(truth['api_route_modules'])
    assert truth['runtime_service_module_count'] == len(truth['runtime_services'])


def test_generated_docs_match_live_truth_for_service_inventory_counts():
    docs_truth = json.loads(
        (Path(__file__).resolve().parents[2] / 'docs' / 'generated' / 'system_truth.json').read_text(encoding='utf-8')
    )
    truth = build_system_truth()

    assert docs_truth['api_route_modules'] == truth['api_route_modules']
    assert docs_truth['api_route_module_count'] == truth['api_route_module_count']
    assert docs_truth['runtime_services'] == truth['runtime_services']
    assert docs_truth['runtime_service_count'] == truth['runtime_service_count']
    assert docs_truth['runtime_service_module_count'] == truth['runtime_service_module_count']


def test_evolution_route_returns_deterministic_error_payload(monkeypatch):
    monkeypatch.setattr(app.state, 'runtime', _EvolutionRuntime(), raising=False)
    client = TestClient(app)

    resp = client.get('/api/evolution/state')

    assert resp.status_code == 200
    assert resp.json() == {
        'ok': False,
        'status': 'degraded',
        'reason_code': 'meta_state_failed',
        'reason': 'meta_state_failed',
        'error': 'meta_state_failed',
        'enabled': False,
    }
