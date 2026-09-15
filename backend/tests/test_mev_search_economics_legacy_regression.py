from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine


def _evidence():
    return {
        'simulation_id': 'sim-1',
        'deterministic': True,
        'fork_block': 100,
        'pre_state_root': '0xpre',
        'post_state_root': '0xpost',
        'scenario_digest': 'sha256:scenario-1',
        'scenario_results': [
            {'gas_multiplier': 1.0, 'liquidity_multiplier': 1.0, 'oracle_multiplier': 1.0, 'conflict_checked': True, 'reverted': False}
        ],
        'reverted': False,
        'economics': {
            'simulation_id': 'sim-1',
            'scenario_digest': 'sha256:scenario-1',
            'expected_realized_profit_usd': 17.5,
            'gross_asset_delta_usd': 20.0,
            'gas_cost_usd': 2.0,
            'borrow_cost_usd': 0.5,
        },
    }


def test_mev_search_records_simulation_gate_without_promoting_heuristic_economics():
    evidence = _evidence()
    evidence['economics'] = None
    rows = MEVSearchEngine().search(mev_state={'sample_pending': [{'hash': '0x2', 'to': '0xrouter', 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12', 'simulation_evidence': evidence}], 'high_risk_ratio': 0.2}, base_opportunities=[])
    assert rows
    gate = rows[0].metadata['simulation_gate']
    assert gate['ok'] is False
    assert gate['reason_code'] == 'simulation_economics_missing'
    assert rows[0].metadata['economics_status'] == 'heuristic_non_authoritative'
    assert rows[0].lifecycle_eligibility == 'observe_only'
    assert rows[0].policy_eligibility == 'observe_only'
    assert rows[0].expected_profit_usd == 0.0


def test_mev_search_accepts_only_explicit_simulation_economics():
    evidence = _evidence()
    rows = MEVSearchEngine().search(mev_state={'sample_pending': [{'hash': '0x4', 'to': '0xrouter', 'value_wei': 5 * 10**18, 'tags': ['dex_like'], 'sel': '0xabcdef12', 'simulation_evidence': evidence}], 'high_risk_ratio': 0.2}, base_opportunities=[])
    assert rows
    row = rows[0]
    assert row.expected_profit_usd == 17.5
    assert row.expected_realized_profit_usd == 17.5
    assert row.metadata['economics_status'] == 'simulation_backed'
    assert row.metadata['economics_source'] == 'simulation_evidence'
    assert row.lifecycle_eligibility == 'observe_only'
    assert row.policy_eligibility == 'observe_only'
