from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot.aqe.meta.runtime import MetaStrategyRuntime


class _BadFloatRouteFail:
    def __float__(self):
        raise ValueError('bad_route_fail')


class _BuggyRouteFail:
    def __float__(self):
        raise KeyError('buggy_route_fail')


class _BadSafety:
    @property
    def minProfitAbs(self):
        raise ValueError('bad_safety')


class _BuggySafety:
    @property
    def minProfitAbs(self):
        raise KeyError('buggy_safety')


class _RuntimeForTelemetry:
    def __init__(self, *, route_fail, safety, opps=None):
        self._opps = list(opps or [SimpleNamespace(expected_profit_usd=1.0, meta={'unit_econ': {'gas_cost_usd_micro': 1_500_000}})])
        self.cfg = SimpleNamespace(safety=safety)
        self._route_fail = route_fail

    def metrics_state(self):
        return {'scan_ms': 10.0, 'fail_streak': 1.0}

    def _route_fail_rate(self):
        return self._route_fail


class _ApplyRuntime:
    def __init__(self, *, exc: Exception | None = None):
        self._exc = exc
        self.settings_calls = []
        self.safety_calls = []
        self.cfg = SimpleNamespace(safety=SimpleNamespace())

    def set_settings(self, **kwargs):
        self.settings_calls.append(kwargs)
        if self._exc is not None:
            raise self._exc

    def set_safety(self, **kwargs):
        self.safety_calls.append(kwargs)


@pytest.fixture()
def meta_runtime(tmp_path: Path) -> MetaStrategyRuntime:
    cfg = SimpleNamespace(enabled=True, mode='observe', tick_seconds=10.0, max_registry_items=10)
    return MetaStrategyRuntime(chain_name='base', data_dir=str(tmp_path), cfg=cfg)


def test_telemetry_from_runtime_degrades_for_expected_route_fail_and_safety(meta_runtime: MetaStrategyRuntime):
    rt = _RuntimeForTelemetry(route_fail=_BadFloatRouteFail(), safety=_BadSafety())
    telemetry = meta_runtime._telemetry_from_runtime(rt)
    assert telemetry['route_fail_rate'] == 0.0
    assert telemetry['gas_cost_usd'] == 0.0
    assert telemetry['expected_profit_usd'] == 0.0
    assert 'minProfitAbs' not in telemetry


def test_telemetry_from_runtime_does_not_swallow_unexpected_route_fail_bug(meta_runtime: MetaStrategyRuntime):
    rt = _RuntimeForTelemetry(route_fail=_BuggyRouteFail(), safety=SimpleNamespace(minProfitAbs='0', minProfitBps=0, slippage_bps=50))
    with pytest.raises(KeyError, match='buggy_route_fail'):
        meta_runtime._telemetry_from_runtime(rt)


def test_telemetry_from_runtime_does_not_swallow_unexpected_safety_bug(meta_runtime: MetaStrategyRuntime):
    rt = _RuntimeForTelemetry(route_fail=0.25, safety=_BuggySafety())
    with pytest.raises(KeyError, match='buggy_safety'):
        meta_runtime._telemetry_from_runtime(rt)


def test_apply_candidate_returns_apply_failed_for_expected_runtime_error(meta_runtime: MetaStrategyRuntime):
    cand_id = 'cand-1'
    meta_runtime.registry.save([{
        'id': cand_id,
        'settings_patch': {'auto_trading': True, 'submit_per_block': 1},
        'safety_patch': {'slippage_bps': 25},
        'lifecycle_stage': 'paper_trading',
    }])
    rt = _ApplyRuntime(exc=RuntimeError('set_failed'))
    result = meta_runtime.apply_candidate(rt, cand_id)
    assert result['ok'] is False
    assert result['error'] == 'apply_failed'
    assert 'set_failed' in result['detail']


def test_apply_candidate_does_not_swallow_unexpected_bug(meta_runtime: MetaStrategyRuntime):
    cand_id = 'cand-2'
    meta_runtime.registry.save([{
        'id': cand_id,
        'settings_patch': {'submit_per_block': 1},
        'safety_patch': {'slippage_bps': 25},
        'lifecycle_stage': 'paper_trading',
    }])
    rt = _ApplyRuntime(exc=KeyError('unexpected_apply_bug'))
    with pytest.raises(KeyError, match='unexpected_apply_bug'):
        meta_runtime.apply_candidate(rt, cand_id)


from victor_ai_bot.aqe.meta.registry import MetaRegistry


def test_meta_registry_recovers_from_corrupt_json(tmp_path: Path):
    path = tmp_path / 'meta_registry.json'
    path.write_text('{bad json', encoding='utf-8')
    registry = MetaRegistry(str(path))
    assert registry.load() == []


def test_meta_registry_sanitizes_malformed_persisted_rows(tmp_path: Path):
    path = tmp_path / 'meta_registry.json'
    path.write_text(
        __import__('json').dumps([
            {
                'id': 'cand-1',
                'description': 'alpha candidate',
                'score': '1.25',
                'genealogy_depth': '2',
                'settings_patch': {'submit_per_block': 1},
                'parent_ids': ['p-1', 7],
                'regime_tags': ['volatile', 3],
            },
            {
                'id': 'cand-2',
                'score': 'bad-score',
                'settings_patch': ['not-a-dict'],
                'mutation_history': 'not-a-list',
                'feature_tags': ['carry'],
            },
            {'description': 'missing-id'},
            'bad-row',
        ]),
        encoding='utf-8',
    )
    registry = MetaRegistry(str(path))
    rows = registry.load()
    assert len(rows) == 2
    assert rows[0]['id'] == 'cand-1'
    assert rows[0]['score'] == 1.25
    assert rows[0]['genealogy_depth'] == 2
    assert rows[0]['settings_patch'] == {'submit_per_block': 1}
    assert rows[0]['parent_ids'] == ['p-1', '7']
    assert rows[0]['regime_tags'] == ['volatile', '3']
    assert rows[1]['id'] == 'cand-2'
    assert 'score' not in rows[1]
    assert 'settings_patch' not in rows[1]
    assert 'mutation_history' not in rows[1]
    assert rows[1]['feature_tags'] == ['carry']


def test_telemetry_from_runtime_prefers_route_ready_verified_positive_opportunity(meta_runtime: MetaStrategyRuntime):
    invalid = SimpleNamespace(
        id='invalid',
        can_execute=True,
        expected_profit_usd=25.0,
        meta={
            'profit_after_costs': '9000000',
            'safety': {'profit_after_costs_wei': '9000000'},
            'unit_econ': {'gas_cost_usd_micro': 2_500_000},
            'execution_route_plan': {'executable': False, 'route_invalid_causes': ['route_plan_not_executable']},
        },
    )
    verified = SimpleNamespace(
        id='verified',
        can_execute=True,
        expected_profit_usd=7.0,
        meta={
            'profit_after_costs': '5000000',
            'safety': {'profit_after_costs_wei': '5000000'},
            'unit_econ': {'gas_cost_usd_micro': 1_500_000},
            'execution_route_plan': {'executable': True},
        },
    )
    rt = _RuntimeForTelemetry(
        route_fail=0.25,
        safety=SimpleNamespace(minProfitAbs='0', minProfitBps=0, slippage_bps=50),
        opps=[invalid, verified],
    )
    telemetry = meta_runtime._telemetry_from_runtime(rt)
    assert telemetry['route_fail_rate'] == 0.25
    assert telemetry['expected_profit_usd'] == 7.0
    assert telemetry['gas_cost_usd'] == 1.5


def test_telemetry_from_runtime_skips_profit_after_costs_mismatch(meta_runtime: MetaStrategyRuntime):
    mismatch = SimpleNamespace(
        id='mismatch',
        can_execute=True,
        expected_profit_usd=20.0,
        meta={
            'profit_after_costs': '9000000',
            'safety': {'profit_after_costs_wei': '8000000'},
            'unit_econ': {'gas_cost_usd_micro': 2_000_000},
            'execution_route_plan': {'executable': True},
        },
    )
    rt = _RuntimeForTelemetry(
        route_fail=0.1,
        safety=SimpleNamespace(minProfitAbs='0', minProfitBps=0, slippage_bps=50),
        opps=[mismatch],
    )
    telemetry = meta_runtime._telemetry_from_runtime(rt)
    assert telemetry['expected_profit_usd'] == 0.0
    assert telemetry['gas_cost_usd'] == 0.0
