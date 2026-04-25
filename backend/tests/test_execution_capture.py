from types import SimpleNamespace

import pytest
import victor_ai_bot.execution_capture.decision_engine as decision_engine_module

from victor_ai_bot.execution_capture.envelope import build_opportunity_envelope
from victor_ai_bot.execution_capture.scoring import compute_capture_score
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore
from victor_ai_bot.execution_capture.decision_engine import ExecutionDecisionEngine
from victor_ai_bot.execution_capture.template_cache import RouteTemplateCache
from victor_ai_bot.execution_capture.models import ExecutionLane


class Leg(SimpleNamespace):
    pass


def make_opp(mev=0.2, profit_usd=12.0, gas_usd=2.0):
    legs = [
        Leg(venue='univ3', token_in='WETH', token_out='USDC'),
        Leg(venue='curve', token_in='USDC', token_out='WETH'),
    ]
    return SimpleNamespace(
        id='opp1',
        route_id='route1',
        strategy='flashloan_atomic',
        expected_profit_usd=str(profit_usd),
        route=SimpleNamespace(legs=legs),
        meta={
            'margin_ratio': 0.18,
            'gas_ratio': 0.2,
            'p_success': 0.82,
            'aqe': {'mev_risk': mev},
            'unit_econ': {'gas_cost_usd_micro': int(gas_usd * 1_000_000)},
        },
    )


def test_capture_score_prefers_positive_realized_value(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    env = build_opportunity_envelope(make_opp(), chain_id=1, regime='balanced')
    score = compute_capture_score(env, store.combined_feedback(route_family=env.route_family, venues=env.venues, lane='PUBLIC'))
    assert score.success_probability > 0.5
    assert score.expected_realized_value > 0.0


def test_lane_routing_private_for_fragile_mev(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=store, template_cache=RouteTemplateCache(data_dir=str(tmp_path), chain='eth'))
    decision = engine.evaluate(make_opp(mev=0.88, profit_usd=25.0, gas_usd=1.5), chain_id=1, regime='high_volatility')
    assert decision.lane in {ExecutionLane.PRIVATE, ExecutionLane.PROTECTED}
    assert decision.action == 'trade'


def test_drop_when_value_too_low(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=store, template_cache=RouteTemplateCache(data_dir=str(tmp_path), chain='eth'))
    decision = engine.evaluate(make_opp(mev=0.5, profit_usd=0.2, gas_usd=1.0), chain_id=1, regime='balanced')
    assert decision.action == 'drop'
    assert decision.drop_reason


def test_telemetry_feedback_improves_signal(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    for _ in range(5):
        store.record(route_family='flash|u|w', venues=['univ3'], lane='PRIVATE', relay='relay', rpc='rpc', success=True, drop=False, revert=False, stale=False, timeout=False, slippage_delta_bps=2.0, realized_pnl_usd=4.0, expected_pnl_usd=5.0, quote_drift_bps=1.0, latency_ms=120.0)
    fb = store.combined_feedback(route_family='flash|u|w', venues=['univ3'], lane='PRIVATE')
    assert fb['route_success_rate'] >= 0.9
    assert fb['venue_quality'] > 0.8


class _BadFloat:
    def __float__(self):
        raise RuntimeError("borrow_mult failure")


def test_borrow_mult_runtime_error_is_not_swallowed(tmp_path, monkeypatch):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=store, template_cache=RouteTemplateCache(data_dir=str(tmp_path), chain='eth'))

    original_resilience = decision_engine_module.evaluate_flashloan_resilience
    original_size = decision_engine_module.choose_flashloan_size

    def _patched_resilience(**kwargs):
        data = dict(original_resilience(**kwargs) or {})
        data.setdefault('provider_priority', ['aave'])
        return data

    def _patched_size(**kwargs):
        data = dict(original_size(**kwargs) or {})
        data['borrow_mult'] = _BadFloat()
        return data

    monkeypatch.setattr(decision_engine_module, 'evaluate_flashloan_resilience', _patched_resilience)
    monkeypatch.setattr(decision_engine_module, 'choose_flashloan_size', _patched_size)

    with pytest.raises(RuntimeError, match='borrow_mult failure'):
        engine.evaluate(make_opp(mev=0.2, profit_usd=25.0, gas_usd=1.0), chain_id=1, regime='balanced')

class _BadEdgeFloat:
    def __float__(self):
        raise RuntimeError('edge learning failure')


def test_edge_learning_runtime_error_is_not_swallowed(tmp_path):
    store = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(
        telemetry=store,
        template_cache=RouteTemplateCache(data_dir=str(tmp_path), chain='eth'),
    )
    engine.edge_learning = SimpleNamespace(
        predict=lambda **kwargs: SimpleNamespace(
            success_probability=_BadEdgeFloat(),
            freshness_decay_factor=1.0,
            quality_adjustment_factor=1.0,
            reliability_factor=1.0,
            competition_probability=0.0,
            expected_slippage_bias=0.0,
            data_sufficiency=1.0,
        )
    )

    with pytest.raises(RuntimeError, match='edge learning failure'):
        engine.evaluate(make_opp(mev=0.2, profit_usd=25.0, gas_usd=1.0), chain_id=1, regime='balanced')
