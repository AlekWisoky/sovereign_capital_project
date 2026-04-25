
from types import SimpleNamespace

from victor_ai_bot.execution_capture.pending_state_context import build_pending_state_context
from victor_ai_bot.execution_capture.adversarial_state import evaluate_adversarial_state
from victor_ai_bot.execution_capture.route_execution_plan import build_execution_route_plan, apply_execution_route_plan
from victor_ai_bot.execution_capture.endpoint_universe import EndpointUniverse


class _Runtime:
    def mev_state(self):
        return {'sample_pending': [{'hash': '0xabc', 'from': '0x1', 'prio_fee': 30_000_000_000, 'tags': ['dex', 'token']}]}
    def blockspace_state(self):
        return {'summary': {'competition_pressure': 0.33}}
    _pending = {'0x2': {'tx_hash': '0x2', 'tokens': ['WETH', 'USDC'], 'venues': ['uni'], 'pairs': ['WETH/USDC'], 'priority': 0.8}}


def _opp():
    return SimpleNamespace(route=SimpleNamespace(legs=[SimpleNamespace(venue='uni', token_in='WETH', token_out='USDC', min_out='1000'), SimpleNamespace(venue='curve', token_in='USDC', token_out='WETH', min_out='900')]), meta={'route_family': 'flashloan_atomic'})


def test_pending_state_context_merges_sources():
    ctx = build_pending_state_context(runtime=_Runtime(), opp=_opp(), existing=[])
    assert ctx['summary']['count'] >= 1
    assert 'mev_sample' in ctx['summary']['sources'] or 'runtime_pending' in ctx['summary']['sources']


def test_adversarial_state_returns_leg_risk_and_invalid_causes():
    env = SimpleNamespace(venues=['uni', 'curve'], token_path=['WETH', 'USDC', 'WETH'], mempool_copy_risk=0.7, latency_half_life_ms=700, private_send_preference=False, route_family='flashloan_atomic', liquidity_fragility=0.8)
    ctx = {'rows': [{'venues': ['uni'], 'tokens': ['WETH', 'USDC'], 'pairs': ['WETH/USDC'], 'priority': 1.0, 'competition_relevance': 0.9, 'searcher_signature': 's1'}], 'summary': {'pending_rate': 0.4}}
    adv = evaluate_adversarial_state(envelope=env, pending_source=ctx, base_expected_value=10.0, lane_hint='PUBLIC')
    assert 'leg_risk' in adv
    assert isinstance(adv['route_invalid_causes'], list)


def test_route_execution_plan_mutates_leg_and_invalidates_when_needed():
    opp = _opp()
    decision = SimpleNamespace(metadata={'route_plan': {'selected_venues': ['uni'], 'split': [{'venue': 'uni', 'share': 1.0, 'size_mult': 1.0, 'venue_quality': 0.9}], 'fallback_tree': []}, 'flashloan_resilience': {'reserve_distortion': 0.2, 'leg_states': [{'venue': 'curve', 'viable': False, 'fallback_venues': ['uni']}], 'provider_priority': ['aave'], 'fallback_provider': 'balancer'}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    assert plan['leg_plan'][1]['action'] in {'fallback_substitute', 'invalidate'}
    if plan['executable']:
        opp2 = apply_execution_route_plan(opp=opp, plan=plan)
        assert opp2.meta['provider_priority'][0] == 'aave'


def test_endpoint_universe_marks_reason_and_private_candidates():
    class _Prefs:
        def snapshot(self):
            return {'read': [], 'send': ['https://send-pref'], 'private': ['https://relay-pref']}
    class _RpcManager:
        def snapshot(self):
            return {'send': [{'url': 'https://send-fast', 'ok': True}], 'private': [{'url': 'https://relay-fast', 'ok': True, 'privacy': 'private'}]}
    class _Chain:
        name = 'ethereum'
        rpc_read = ['https://read-default']
        rpc_send = ['https://send-default']
        rpc_private = ['https://relay-default']
    class _Cfg:
        chain = _Chain()
    universe = EndpointUniverse(cfg=_Cfg(), rpc_manager=_RpcManager(), rpc_preferences=_Prefs())
    private = universe.candidates(lane='PRIVATE')
    assert private['reason'] in {'operator_preferences', 'manager_health', 'config_default'}
    assert any((row.get('privacy_class') == 'private') for row in private['relays'])
