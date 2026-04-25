from types import SimpleNamespace

from victor_ai_bot.aqe.meta.predictor import predict_candidate_success
from victor_ai_bot.execution_capture.decision_engine import ExecutionDecisionEngine
from victor_ai_bot.execution_capture.simulation_realism import simulate_execution_realism
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore
from victor_ai_bot.execution_capture.template_cache import RouteTemplateCache
from victor_ai_bot.regime_engine import classify_market, regime_adjustments


class Leg(SimpleNamespace):
    pass


def make_opp(route_strategy='flashloan_atomic', mev=0.2, profit_usd=12.0, gas_usd=2.0):
    legs = [
        Leg(venue='univ3', token_in='WETH', token_out='USDC'),
        Leg(venue='curve', token_in='USDC', token_out='WETH'),
    ]
    return SimpleNamespace(
        id='opp1',
        route_id='route1',
        strategy=route_strategy,
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


def test_simulation_realism_penalizes_stress():
    store = ExecutionTelemetryStore(data_dir='/tmp', chain='eth')
    engine = ExecutionDecisionEngine(telemetry=store, template_cache=RouteTemplateCache(data_dir='/tmp', chain='eth'))
    opp = make_opp(mev=0.75, profit_usd=25.0, gas_usd=3.0)
    env = engine.evaluate(opp, chain_id=1, regime='high_volatility')
    realism = env.metadata['simulation_realism']
    assert realism['mev_competition_penalty'] > 0.3
    assert realism['success_multiplier'] < 1.0


def test_regime_engine_shapes_family_bias():
    market = classify_market(volatility=0.8, liquidity=0.7, volume=0.6, gas=0.2, spreads=0.4, trend=0.0)
    assert market.regime == 'high_volatility'
    adj_mev = regime_adjustments(route_family='mev_search|builder|WETH>USDC', regime=market.regime)
    adj_funding = regime_adjustments(route_family='funding_arb|binance|BTC', regime=market.regime)
    assert adj_mev['value_multiplier'] > adj_funding['value_multiplier']
    assert adj_mev['preferred_lane'] == 'PRIVATE'


def test_meta_predictor_uses_family_and_regime_memory():
    candidate = {
        'strategy_family': 'oracle_drift',
        'diversity_metrics': {'novelty_score': 0.4, 'correlation_penalty': 0.05},
        'stress_report': {'robustness_score': 0.85},
        'validation': {'passed': True},
        'lifecycle_stage': 'shadow_live',
    }
    rows = [
        {'strategy_family': 'oracle_drift', 'regime_tags': ['balanced'], 'score': 8.0},
        {'strategy_family': 'oracle_drift', 'regime_tags': ['balanced'], 'score': 6.0},
        {'strategy_family': 'funding_arb', 'regime_tags': ['bear'], 'score': -2.0},
    ]
    pred = predict_candidate_success(candidate=candidate, memory_rows=rows, regime='balanced')
    assert pred['predicted_success'] > 0.6
    assert pred['prediction_confidence'] >= 0.35


def test_regime_safe_float_accepts_numeric_string():
    from victor_ai_bot.regime_engine import _safe_float

    assert _safe_float("1.25") == 1.25


def test_regime_safe_float_falls_back_on_bad_value():
    from victor_ai_bot.regime_engine import _safe_float

    assert _safe_float("bad", default=3.5) == 3.5


def test_regime_safe_float_does_not_swallow_runtime_error():
    import pytest

    from victor_ai_bot.regime_engine import _safe_float

    class Explodes:
        def __float__(self):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        _safe_float(Explodes())
