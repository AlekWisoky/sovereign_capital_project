from dataclasses import replace

from victor_ai_bot.execution_capture.flashloan_sizing import choose_flashloan_size
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint


def _env():
    return OpportunityEnvelope(
        opportunity_id='opp-1',
        route_id='route-1',
        route_family='flashloan_atomic',
        expected_profit_usd=12.0,
        gas_estimate_usd=1.0,
        slippage_sensitivity=0.3,
        liquidity_fragility=0.4,
        latency_half_life_ms=900,
        mempool_copy_risk=0.3,
        venue_reliability_score=0.9,
        simulation_confidence=0.92,
        safe_size_curve=[
            SafeSizePoint(0.8, 6.0, 0.5, 0.2, 0.1),
            SafeSizePoint(1.0, 8.5, 0.8, 0.3, 0.2),
            SafeSizePoint(1.4, 12.0, 1.4, 0.7, 0.4),
            SafeSizePoint(2.0, 10.5, 2.8, 1.6, 0.9),
        ],
        failure_cost_estimate=2.0,
        freshness_score=0.95,
        private_send_preference=True,
        chain_id=1,
        token_path=['WETH', 'USDC'],
        venues=['univ3', 'curve'],
        metadata={},
    )


def test_flashloan_sizing_caps_fragile_large_trade():
    result = choose_flashloan_size(
        envelope=_env(),
        requested_size_mult=2.0,
        route_plan={'score': 0.9},
        flashloan_resilience={'reserve_distortion': 0.55, 'provider_priority': ['aave', 'balancer'], 'selected_provider': 'aave'},
        adversarial_state={'interference_probability': 0.45, 'stale_probability': 0.3, 'post_ordering_realized_edge': 6.0},
        treasury_state={'borrow_mult_target_cap': 3.0},
        wealth_goal_state={'state': {'aggressivenessCap': 1.1, 'capitalCommitmentPct': 35.0}},
        drawdown_state={'drawdownPct': 2.0, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['allowed'] is True
    assert result['size_mult'] < 2.0
    assert 'reserve_distortion_cap' in result['reason_codes']


def test_flashloan_sizing_blocks_on_hard_stop():
    result = choose_flashloan_size(
        envelope=_env(),
        requested_size_mult=1.4,
        route_plan={'score': 0.9},
        flashloan_resilience={'reserve_distortion': 0.2, 'provider_priority': ['aave'], 'selected_provider': 'aave'},
        adversarial_state={'interference_probability': 0.1, 'stale_probability': 0.05, 'post_ordering_realized_edge': 8.0},
        treasury_state={'borrow_mult_target_cap': 3.0},
        wealth_goal_state={'state': {'aggressivenessCap': 1.2, 'capitalCommitmentPct': 35.0}},
        drawdown_state={'drawdownPct': 9.0, 'hardStop': {'active': True}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['allowed'] is False
    assert 'drawdown_hard_stop' in result['reason_codes']


def test_flashloan_sizing_caps_by_provider_and_pool_depth():
    result = choose_flashloan_size(
        envelope=_env(),
        requested_size_mult=3.0,
        route_plan={'score': 0.95},
        flashloan_resilience={'reserve_distortion': 0.15, 'provider_priority': ['uniswap_flash'], 'selected_provider': 'uniswap_flash', 'provider_scores': [{'provider': 'uniswap_flash', 'score': 0.8}], 'leg_states': [{'venue': 'univ3', 'distortion': 0.1, 'viable': True}, {'venue': 'curve', 'distortion': 0.12, 'viable': True}], 'route_viable': True},
        adversarial_state={'interference_probability': 0.1, 'stale_probability': 0.05, 'copy_risk': 0.05, 'post_ordering_realized_edge': 9.0},
        treasury_state={'borrow_mult_target_cap': 4.0, 'capital_engine': {'family_targets': {'flashloan_atomic': 0.4}}},
        wealth_goal_state={'state': {'aggressivenessCap': 1.0, 'capitalCommitmentPct': 30.0}},
        drawdown_state={'drawdownPct': 1.0, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['size_mult'] <= result['provider_limit']
    assert result['size_mult'] <= result['pool_depth_cap'] + 1e-9


def test_flashloan_sizing_can_select_fallback_provider_for_better_limit():
    result = choose_flashloan_size(
        envelope=_env(),
        requested_size_mult=2.8,
        route_plan={'score': 0.95},
        flashloan_resilience={'reserve_distortion': 0.12, 'provider_priority': ['uniswap_flash', 'aave'], 'selected_provider': 'uniswap_flash', 'fallback_provider': 'aave', 'provider_scores': [{'provider': 'uniswap_flash', 'score': 0.72}, {'provider': 'aave', 'score': 0.84}], 'leg_states': [{'venue': 'univ3', 'distortion': 0.08, 'viable': True}, {'venue': 'curve', 'distortion': 0.10, 'viable': True}], 'route_viable': True},
        adversarial_state={'interference_probability': 0.08, 'stale_probability': 0.04, 'copy_risk': 0.04, 'post_ordering_realized_edge': 9.5},
        treasury_state={'borrow_mult_target_cap': 4.0, 'capital_engine': {'family_targets': {'flashloan_atomic': 0.45}}},
        wealth_goal_state={'state': {'aggressivenessCap': 1.0, 'capitalCommitmentPct': 30.0}},
        drawdown_state={'drawdownPct': 1.0, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['selected_provider'] in {'uniswap_flash', 'aave'}
    assert result['provider_choice_reason']
    assert result['provider_candidates']


def test_flashloan_sizing_rejects_negative_net_ev_under_distortion():
    result = choose_flashloan_size(
        envelope=_env(),
        requested_size_mult=2.0,
        route_plan={'score': 0.55},
        flashloan_resilience={'reserve_distortion': 0.62, 'provider_priority': ['aave'], 'selected_provider': 'aave', 'provider_scores': [{'provider': 'aave', 'score': 0.65}], 'leg_states': [{'venue': 'univ3', 'distortion': 0.55, 'viable': True}, {'venue': 'curve', 'distortion': 0.60, 'viable': True}], 'route_viable': True},
        adversarial_state={'interference_probability': 0.58, 'stale_probability': 0.42, 'copy_risk': 0.35, 'post_ordering_realized_edge': 2.0},
        treasury_state={'borrow_mult_target_cap': 4.0, 'capital_engine': {'family_targets': {'flashloan_atomic': 0.35}}},
        wealth_goal_state={'state': {'aggressivenessCap': 0.95, 'capitalCommitmentPct': 25.0}},
        drawdown_state={'drawdownPct': 4.0, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['allowed'] is False
    assert 'negative_net_ev' in result['reason_codes'] or 'fragility_too_high' in result['reason_codes']


def test_flashloan_sizing_resolves_decorated_route_family_to_capital_family_target():
    env = replace(
        _env(),
        route_family='flash_arb|univ3>curve|WETH>USDC',
        metadata={'strategy_family': 'flash_arb', 'meta': {'strategy_family': 'flash_arb'}},
    )
    result = choose_flashloan_size(
        envelope=env,
        requested_size_mult=2.2,
        route_plan={'score': 0.95},
        flashloan_resilience={'reserve_distortion': 0.12, 'provider_priority': ['aave'], 'selected_provider': 'aave'},
        adversarial_state={'interference_probability': 0.08, 'stale_probability': 0.05, 'copy_risk': 0.04, 'post_ordering_realized_edge': 9.0},
        treasury_state={'borrow_mult_target_cap': 4.0, 'capital_engine': {'family_targets': {'flashloan_atomic': 0.18}}},
        wealth_goal_state={'state': {'aggressivenessCap': 1.0, 'capitalCommitmentPct': 30.0}},
        drawdown_state={'drawdownPct': 1.0, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['allowed'] is True
    assert result['family_target_known'] is True
    assert result['resolved_family_target_key'] == 'flashloan_atomic'
    assert result['family_target_pct'] == 0.18
    assert result['family_budget_cap'] < 1.0


def test_flashloan_sizing_fails_closed_when_capital_family_target_is_zero():
    env = replace(
        _env(),
        route_family='flash_arb|univ3>curve|WETH>USDC',
        metadata={'strategy_family': 'flash_arb', 'meta': {'strategy_family': 'flash_arb'}},
    )
    result = choose_flashloan_size(
        envelope=env,
        requested_size_mult=1.4,
        route_plan={'score': 0.92},
        flashloan_resilience={'reserve_distortion': 0.08, 'provider_priority': ['aave'], 'selected_provider': 'aave'},
        adversarial_state={'interference_probability': 0.06, 'stale_probability': 0.03, 'copy_risk': 0.02, 'post_ordering_realized_edge': 9.0},
        treasury_state={'borrow_mult_target_cap': 4.0, 'capital_engine': {'family_targets': {'flashloan_atomic': 0.0}}},
        wealth_goal_state={'state': {'aggressivenessCap': 1.0, 'capitalCommitmentPct': 30.0}},
        drawdown_state={'drawdownPct': 0.5, 'hardStop': {'active': False}},
        kill_switch_state={'suppressions': {}},
    )
    assert result['allowed'] is False
    assert 'family_target_zero' in result['reason_codes']
