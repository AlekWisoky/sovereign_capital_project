from types import SimpleNamespace

from victor_ai_bot.execution_capture.adversarial_state import evaluate_adversarial_state
from victor_ai_bot.execution_capture.endpoint_universe import EndpointUniverse
from victor_ai_bot.execution_capture.route_execution_plan import apply_execution_route_plan, build_execution_route_plan
from victor_ai_bot.execution_capture.route_quality_store import RouteQualityStore
from victor_ai_bot.execution_capture.smart_order_router import plan_route
from victor_ai_bot.execution_capture.models import CaptureScore, OpportunityEnvelope, SafeSizePoint


class _Prefs:
    def snapshot(self):
        return {'read': ['https://read-pref'], 'send': ['https://send-pref'], 'private': ['https://relay-pref']}


class _RpcManager:
    def snapshot(self):
        return {
            'read': [{'url': 'https://read-fast', 'ok': True}],
            'send': [{'url': 'https://send-fast', 'ok': True}],
            'private': [{'url': 'https://relay-fast', 'ok': True}],
        }


class _Chain:
    rpc_read = ['https://read-default']
    rpc_send = ['https://send-default']
    rpc_private = ['https://relay-default']


class _Cfg:
    chain = _Chain()


def test_endpoint_universe_uses_preferences_and_manager_rows():
    universe = EndpointUniverse(cfg=_Cfg(), rpc_manager=_RpcManager(), rpc_preferences=_Prefs())
    private = universe.candidates(lane='PRIVATE')
    urls = [str(x.get('url') or x.get('endpoint') or '') for x in private['relays']]
    assert 'https://relay-pref' in urls
    assert 'https://relay-fast' in urls or 'https://send-fast' in urls


def test_route_quality_history_influences_sor_selection(tmp_path):
    rq = RouteQualityStore(data_dir=str(tmp_path), chain='eth')
    for _ in range(4):
        rq.observe(route_family='flashloan_atomic', venue_subset=['curve'], split_signature='curve:1.0', ok=True, realized_edge_usd=12.0)
    env = OpportunityEnvelope(
        opportunity_id='o1',
        route_id='r1',
        route_family='flashloan_atomic',
        expected_profit_usd=25.0,
        gas_estimate_usd=1.0,
        slippage_sensitivity=0.2,
        liquidity_fragility=0.3,
        latency_half_life_ms=1200,
        mempool_copy_risk=0.1,
        venue_reliability_score=0.9,
        simulation_confidence=0.9,
        safe_size_curve=[SafeSizePoint(1.0, 25.0, 0.7, 0.2, 0.1)],
        failure_cost_estimate=0.4,
        freshness_score=0.95,
        private_send_preference=False,
        chain_id=1,
        venues=['uni', 'curve'],
        token_path=['WETH', 'USDC', 'WETH'],
    )
    capture = CaptureScore(success_probability=0.95, freshness_probability=0.95, interference_probability=0.05, venue_quality=0.9, expected_realized_pnl=20.0, capture_score=0.82, expected_realized_value=20.0, slippage_cost_estimate=0.7, latency_decay_cost=0.2, failure_cost_estimate=0.4)
    plan = plan_route(envelope=env, capture=capture, telemetry={'best_latency_ms': 220.0}, latency_pressure=0.1, route_quality=rq, max_subset_size=2)
    assert 'curve' in plan.selected_venues


def test_execution_route_plan_applies_fallback_and_mutates_min_outs():
    opp = SimpleNamespace(
        route=SimpleNamespace(legs=[SimpleNamespace(venue='uni', min_out='1000'), SimpleNamespace(venue='curve', min_out='900')]),
        meta={},
    )
    decision = SimpleNamespace(metadata={
        'route_plan': {
            'selected_venues': ['balancer'],
            'split': [{'venue': 'balancer', 'share': 1.0, 'size_mult': 1.0, 'venue_quality': 0.8}],
            'fallback_tree': [
                {
                    'selected_venues': ['uni', 'curve'],
                    'split': [
                        {'venue': 'uni', 'share': 0.5, 'size_mult': 0.5, 'venue_quality': 0.9},
                        {'venue': 'curve', 'share': 0.5, 'size_mult': 0.5, 'venue_quality': 0.88},
                    ],
                    'expected_value': 12.0,
                }
            ],
        },
        'flashloan_resilience': {'reserve_distortion': 0.12, 'provider_priority': ['aave'], 'fallback_provider': 'balancer'},
    })
    plan = build_execution_route_plan(opp=opp, decision=decision)
    assert plan['fallback_used'] is True
    opp2 = apply_execution_route_plan(opp=opp, plan=plan)
    assert opp2.meta['route_fallback_ready'] is True
    assert int(opp2.route.legs[0].min_out) <= 1000


def test_adversarial_state_generates_bounded_scenarios_and_private_lane_requirement():
    envelope = SimpleNamespace(
        venues=['uni', 'curve'],
        token_path=['WETH', 'USDC', 'WETH'],
        mempool_copy_risk=0.8,
        latency_half_life_ms=700,
        private_send_preference=False,
        route_family='flashloan_atomic',
    )
    pending = [
        {'pool': 'uni', 'token_in': 'WETH', 'token_out': 'USDC', 'venue': 'uni', 'searcher_signature': 's1', 'priority': 1.0},
        {'pool': 'curve', 'token_in': 'USDC', 'token_out': 'WETH', 'venue': 'curve', 'searcher_signature': 's2', 'priority': 0.9},
        {'pair': 'WETH/USDC', 'venue': 'uni', 'searcher_signature': 's1', 'priority': 0.8},
    ]
    adv = evaluate_adversarial_state(envelope=envelope, pending_source=pending, base_expected_value=18.0, lane_hint='PUBLIC')
    assert adv['scenarios']
    assert len(adv['scenarios']) <= 6
    assert adv['requires_private_lane'] is True
    assert adv['post_ordering_realized_edge'] <= 18.0
