import pytest

from victor_ai_bot.governance.kill_switch import KillSwitchStore
from victor_ai_bot.risk_engine.drawdown_state import DrawdownStateStore
from victor_ai_bot.risk_engine.portfolio_risk import compute_portfolio_risk
from victor_ai_bot.rl_training.reward import _safe_float, reward_function



def test_reward_function_tracks_realized_money_loop_terms():
    out = reward_function(
        realized_net_pnl=120.0,
        deployed_notional=1000.0,
        gas_cost=12.0,
        slippage_bias=5.0,
        interference_penalty=3.0,
        drawdown_contribution=8.0,
        concentration_penalty=6.0,
        capital_lock_penalty=4.0,
        stability_bonus=10.0,
        calibration_bonus=2.0,
    )
    assert out['reward'] > 0
    assert out['components']['gasCost'] > 0
    assert out['components']['stabilityBonus'] > 0
    assert out['normalizationDenom'] >= 1.0



def test_drawdown_store_hard_stop_and_gate(tmp_path):
    store = DrawdownStateStore(data_dir=str(tmp_path), chain='eth', intraday_drawdown_limit_pct=0.05, intraday_loss_limit_usd=50.0)
    store.observe(family='flashloan_atomic', route_family='flash', venue='uni', lane='PRIVATE', regime='balanced', realized_pnl_usd=100.0)
    store.observe(family='flashloan_atomic', route_family='flash', venue='uni', lane='PRIVATE', regime='balanced', realized_pnl_usd=-200.0)
    snap = store.snapshot()
    assert snap['hardStop']['active'] is True
    gate = store.gate(family='flashloan_atomic')
    assert gate['allowed'] is False
    assert gate['reason_codes']


def test_drawdown_store_recovers_from_corrupt_json_with_blank_state(tmp_path):
    risk_dir = tmp_path / 'risk'
    risk_dir.mkdir(parents=True)
    (risk_dir / 'drawdown_eth.json').write_text('{not-valid-json', encoding='utf-8')

    store = DrawdownStateStore(data_dir=str(tmp_path), chain='eth')

    snap = store.snapshot()
    assert snap['drawdownPct'] == 0.0
    assert snap['intradayLossUsd'] == 0.0
    assert snap['hardStop']['active'] is False


def test_drawdown_store_discards_invalid_sections_but_keeps_valid_hard_stop(tmp_path):
    risk_dir = tmp_path / 'risk'
    risk_dir.mkdir(parents=True)
    (risk_dir / 'drawdown_eth.json').write_text(
        '{\n'
        '  "equity_curve": {"bad": true},\n'
        '  "family_returns": [],\n'
        '  "hard_stop": {"active": 1, "reason_codes": ["intraday_loss_limit"], "triggered_ts_ms": "123"}\n'
        '}',
        encoding='utf-8',
    )

    store = DrawdownStateStore(data_dir=str(tmp_path), chain='eth')

    snap = store.snapshot()
    assert snap['familyDrawdown'] == {}
    assert snap['hardStop'] == {
        'active': True,
        'reason_codes': ['intraday_loss_limit'],
        'triggered_ts_ms': 123,
    }



def test_kill_switch_suppresses_family_on_fee_burn_and_stale_quotes(tmp_path):
    ks = KillSwitchStore(data_dir=str(tmp_path), chain='eth')
    for _ in range(6):
        ks.observe_outcome(
            family='flashloan_atomic',
            route_family='flash',
            venue='uni',
            lane='PRIVATE',
            ok=False,
            expected_edge_usd=8.0,
            realized_edge_usd=-3.0,
            slippage_drift_bps=45.0,
            stale=True,
            fee_burn_usd=15.0,
            rpc_pressure=0.8,
            chain='eth',
        )
    ev = ks.evaluate(family='flashloan_atomic', route_family='flash', venue='uni', chain='eth')
    assert ev['allowed'] is False
    assert ev['reason_codes']



def test_portfolio_risk_reports_var_es_and_stress():
    summary = {
        'strategy_allocations': {
            'flash_arb': {'allocatedUsd': 600.0},
            'funding_arb': {'allocatedUsd': 400.0},
        },
        'risk': {'riskScore': 0.4},
    }
    scorecards = {
        'families': [
            {'family': 'flash_arb', 'returnHistory': [0.01, -0.02, 0.015, -0.03, 0.02]},
            {'family': 'funding_arb', 'returnHistory': [0.005, 0.004, -0.006, 0.003, -0.002]},
        ]
    }
    drawdown = {'familyReturnHistory': {'flash_arb': [0.01, -0.02], 'funding_arb': [0.004, -0.002]}}
    risk = compute_portfolio_risk(capital_state=summary, covariance_penalties={}, engine_state={}, scorecards=scorecards, drawdown_state=drawdown)
    assert 'historicalSimulation' in risk and 'var95' in risk['historicalSimulation']
    assert 'regimeCovariance' in risk
    assert 'stressScenarios' in risk and 'gas_spike' in risk['stressScenarios']
    assert 'exposureLimits' in risk
    assert isinstance(risk['exposureLimits'], dict)


def test_reward_safe_float_keeps_expected_coercion_behavior():
    assert _safe_float('1.25') == 1.25
    assert _safe_float('bad', default=3.5) == 3.5


def test_reward_safe_float_does_not_swallow_unexpected_bug():
    class BadFloat:
        def __float__(self):
            raise RuntimeError('unexpected_float_bug')

    with pytest.raises(RuntimeError, match='unexpected_float_bug'):
        _safe_float(BadFloat())
