from types import SimpleNamespace

from victor_ai_bot.agents.attribution import AgentAttributionStore
from victor_ai_bot.agents.weighting import AgentWeightingGovernor
from victor_ai_bot.execution_capture.decision_engine import ExecutionDecisionEngine
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore
from victor_ai_bot.execution_capture.template_cache import RouteTemplateCache
from victor_ai_bot.runtime_services.telemetry_service import TelemetryService
from victor_ai_bot.telemetry.store import TelemetryStore
from victor_ai_bot.strategies.family_scorecards import FamilyScorecardStore
from victor_ai_bot.treasury.allocation_engine import allocate_capital


class Leg(SimpleNamespace):
    pass


def make_opp():
    legs = [Leg(venue='univ3', token_in='WETH', token_out='USDC'), Leg(venue='curve', token_in='USDC', token_out='WETH')]
    return SimpleNamespace(
        id='opp-e2e',
        route_id='route-e2e',
        strategy='flashloan_atomic',
        expected_profit_usd='18.0',
        route=SimpleNamespace(legs=legs),
        meta={'margin_ratio': 0.2, 'gas_ratio': 0.15, 'p_success': 0.84, 'aqe': {'mev_risk': 0.25}, 'unit_econ': {'gas_cost_usd_micro': 1_500_000}, 'strategy_family': 'flashloan_atomic', 'route_family': 'flashloan_atomic|univ3>curve|WETH>WETH'},
    )


def test_end_to_end_decision_to_feedback(tmp_path):
    cap = allocate_capital(estimated_capital_wei=10_000_000, drawdown_pct=2.0, regime='balanced', aggressiveness_level='MODERATE')
    assert cap['family_allocations_wei']['flashloan_atomic'] > 0

    telemetry = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=telemetry, template_cache=RouteTemplateCache(data_dir=str(tmp_path), chain='eth'))
    opp = make_opp()
    decision = engine.evaluate(opp, chain_id=1, regime='balanced')
    assert decision.action in {'trade', 'drop'}

    tstore = TelemetryStore(data_dir=str(tmp_path), chain='eth')
    tsvc = TelemetryService(store=tstore)
    tsvc.record('decision', {'route_family': opp.meta['route_family'], 'strategy_family': opp.meta['strategy_family'], 'projected_realized_edge_usd': decision.expected_realized_value, 'actual_realized_edge_usd': 0.0, 'ok': decision.action == 'trade', 'dropped': decision.action == 'drop'}, chain='eth')

    family = FamilyScorecardStore(str(tmp_path / 'family.json'))
    realized = 5.5 if decision.action == 'trade' else 0.0
    family.observe(family='flashloan_atomic', realized_pnl_usd=realized, gas_cost_usd=1.5, ok=decision.action == 'trade', regime='balanced')

    attrib = AgentAttributionStore(path=str(tmp_path / 'attrib.json'))
    attrib.append({'contributors': [{'agent': 'RiskAgent', 'followed': True, 'realized_pnl_impact_usd': realized * 0.2, 'precision_hit': decision.action == 'trade'}]})
    gov = AgentWeightingGovernor(path=str(tmp_path / 'weights.json'))
    gov.observe(agent='RiskAgent', regime='balanced', followed=True, predicted_signal=1.0, realized_edge_usd=realized)

    assert family.snapshot()['families'][0]['family'] == 'flashloan_atomic'
    assert attrib.summary()['agents'][0]['agent'] == 'RiskAgent'
    assert gov.weights_for(regime='balanced', agents=['RiskAgent'])['RiskAgent'] > 0
    assert len(tsvc.store.tail(limit=5)) == 1
