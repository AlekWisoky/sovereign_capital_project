from victor_ai_bot.aqe.arbitrage.cross_cex_dex_engine import CrossCEXDEXArbitrageEngine
from victor_ai_bot.aqe.cross_chain import CrossChainArbitrageEngine
from victor_ai_bot.aqe.funding import FundingArbStrategy, FundingArbConfig
from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine
from victor_ai_bot.runtime_services.engine_service import EngineService


def test_cross_cex_dex_respects_inventory_and_penalties():
    eng = CrossCEXDEXArbitrageEngine()
    rows = eng.scan(
        quotes=[{'symbol': 'ETHUSDT', 'venue': 'binance', 'bid': 2050.0, 'ask': 2051.0, 'depth_usd': 4000.0}],
        dex_prices={'ETHUSDT': 2025.0},
        dex_depths={'ETHUSDT': 3000.0},
        venue_inventory={'binance': {'ETHUSDT': 1.5}, 'dex': {'ETHUSDT': 2.0}},
        chain='ethereum',
        chain_id=1,
        regime='balanced',
    )
    assert rows
    top = rows[0]
    assert top.engine_type == 'cross_cex_dex'
    assert top.expected_realized_profit_usd > 0
    assert top.lifecycle_eligibility in {'paper', 'capped_live'}


def test_funding_engine_models_carry_and_risk():
    eng = FundingArbStrategy(cfg=FundingArbConfig(enabled=True, min_rate_diff=0.00001, max_positions=3))
    rows = eng.scan(
        funding_rows=[
            {'symbol': 'BTCUSDT', 'venue': 'a', 'funding_rate': 0.0009, 'hours_to_funding': 2.0, 'basis_bps': 3.0, 'fee_bps': 4.0, 'notional_usd': 5000.0, 'mark_price': 50000.0, 'collateral_efficiency': 0.95, 'liquidation_buffer_pct': 18.0},
            {'symbol': 'BTCUSDT', 'venue': 'b', 'funding_rate': -0.0002, 'hours_to_funding': 2.0, 'basis_bps': -1.0, 'fee_bps': 4.0, 'notional_usd': 5000.0, 'mark_price': 50000.0, 'collateral_efficiency': 0.92, 'liquidation_buffer_pct': 15.0},
        ],
        chain='offchain',
        chain_id=0,
        regime='bear',
    )
    assert rows
    top = rows[0]
    assert top.engine_type == 'funding_arb'
    assert 'carry' in top.metadata and 'risk' in top.metadata


def test_cross_chain_engine_fails_closed_when_inventory_uncertain():
    eng = CrossChainArbitrageEngine()
    rows = eng.scan(
        spreads=[{'src_chain': 'ethereum', 'dst_chain': 'arbitrum', 'symbol': 'ETH', 'spread_ratio': 0.03, 'capital_required_usd': 1000.0, 'class': 'prepositioned_capital_arb', 'chain_id': 1}],
        chain_inventory={'ethereum': 600.0, 'arbitrum': 100.0},
        bridge_quotes={'ethereum->arbitrum': {'bridge': 'canonical', 'finality_seconds': 1800.0, 'bridge_fee_bps': 20.0, 'timeout_probability': 0.08}},
        regime='balanced',
    )
    assert rows
    top = rows[0]
    assert top.engine_type == 'cross_chain_arb'
    assert top.policy_eligibility in {'observe_only', 'capped_live'}
    assert 'bridge_risk' in top.risk_flags


def test_mev_search_private_only_candidates():
    eng = MEVSearchEngine()
    rows = eng.search(
        mev_state={'sample_pending': [{'hash': '0x1', 'to': '0xrouter', 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12'}], 'high_risk_ratio': 0.2},
        base_opportunities=[],
        regime='high_volatility',
        chain='ethereum',
        chain_id=1,
    )
    assert rows
    assert all(r.engine_type == 'mev_search' for r in rows)
    assert all('private_send' in r.risk_flags for r in rows)


def test_engine_service_outputs_all_major_engines():
    svc = EngineService(capture_engine=None, telemetry_service=None)
    state = svc.scan(
        chain='ethereum',
        chain_id=1,
        regime='balanced',
        quotes=[
            {'symbol': 'ETHUSDT', 'venue': 'binance', 'bid': 2050.0, 'ask': 2051.0, 'depth_usd': 4000.0, 'product': 'spot'},
            {'symbol': 'BTCUSDT', 'venue': 'a', 'bid': 50010.0, 'ask': 50020.0, 'product': 'futures', 'funding_rate': 0.0009, 'notional_usd': 4000.0, 'mark_price': 50000.0},
            {'symbol': 'BTCUSDT', 'venue': 'b', 'bid': 50000.0, 'ask': 50010.0, 'product': 'futures', 'funding_rate': -0.0002, 'notional_usd': 4000.0, 'mark_price': 50000.0},
        ],
        funding_rows=[
            {'symbol': 'BTCUSDT', 'venue': 'a', 'funding_rate': 0.0009, 'hours_to_funding': 2.0, 'basis_bps': 3.0, 'fee_bps': 4.0, 'notional_usd': 4000.0, 'mark_price': 50000.0, 'collateral_efficiency': 0.95, 'liquidation_buffer_pct': 18.0},
            {'symbol': 'BTCUSDT', 'venue': 'b', 'funding_rate': -0.0002, 'hours_to_funding': 2.0, 'basis_bps': -1.0, 'fee_bps': 4.0, 'notional_usd': 4000.0, 'mark_price': 50000.0, 'collateral_efficiency': 0.92, 'liquidation_buffer_pct': 15.0},
        ],
        dex_prices={'ETHUSDT': 2025.0},
        dex_depths={'ETHUSDT': 3000.0},
        venue_inventory={'binance': {'ETHUSDT': 2.0}, 'dex': {'ETHUSDT': 2.0}},
        bridge_spreads=[{'src_chain': 'ethereum', 'dst_chain': 'arbitrum', 'symbol': 'ETH', 'spread_ratio': 0.03, 'capital_required_usd': 1000.0, 'class': 'prepositioned_capital_arb', 'chain_id': 1}],
        bridge_quotes={'ethereum->arbitrum': {'bridge': 'canonical', 'finality_seconds': 1800.0, 'bridge_fee_bps': 20.0, 'timeout_probability': 0.08}},
        chain_inventory={'ethereum': 2000.0, 'arbitrum': 600.0},
        mev_state={'sample_pending': [{'hash': '0x1', 'to': '0xrouter', 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12'}], 'high_risk_ratio': 0.2},
        base_opportunities=[],
        meta_candidates=[{'id': 'cand-1', 'score': 12.0, 'strategy_family': 'oracle_drift', 'lifecycle_stage': 'sandbox'}],
        treasury_state={'estimated_capital_usd': 10000.0, 'capital_engine': {'deployable_bankroll_wei': int(8000 * 1e18), 'experimental_bankroll_wei': int(500 * 1e18), 'family_allocations_wei': {'cross_cex_dex': int(1000 * 1e18), 'funding_arb': int(1200 * 1e18)}}},
        public_mode=False,
    )
    engine_types = {item['opportunity']['engine_type'] for item in state['items']}
    assert 'cross_cex_dex' in engine_types
    assert 'funding_arb' in engine_types
    assert 'cross_chain_arb' in engine_types
    assert 'mev_search' in engine_types
    assert 'auto_strategy_generator' in engine_types
