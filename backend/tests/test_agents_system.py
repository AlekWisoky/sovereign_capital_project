from victor_ai_bot.agents.health import AgentHealthStatus, classify_health
from victor_ai_bot.agents.weighting import AgentWeightingGovernor
from victor_ai_bot.agents.attribution import AgentAttributionStore


def test_agent_health_states():
    assert classify_health(duration_ms=10, ttl_ms=100, ok=True).status == AgentHealthStatus.HEALTHY
    assert classify_health(duration_ms=80, ttl_ms=100, ok=True).status == AgentHealthStatus.DEGRADED
    assert classify_health(duration_ms=100, ttl_ms=100, ok=False, error='timeout').status == AgentHealthStatus.TIMED_OUT
    assert classify_health(duration_ms=10, ttl_ms=100, ok=False, error='boom').status == AgentHealthStatus.FAILED


def test_agent_weighting_changes_by_regime_and_performance(tmp_path):
    gov = AgentWeightingGovernor(path=str(tmp_path / 'weights.json'))
    base = gov.weights_for(regime='high_volatility', agents=['RiskAgent', 'ValuationAgent'])
    gov.observe(agent='RiskAgent', regime='high_volatility', followed=True, predicted_signal=1.0, realized_edge_usd=4.0)
    gov.observe(agent='RiskAgent', regime='high_volatility', followed=True, predicted_signal=1.0, realized_edge_usd=3.5)
    after = gov.weights_for(regime='high_volatility', agents=['RiskAgent', 'ValuationAgent'])
    assert after['RiskAgent'] > base['RiskAgent']


def test_agent_attribution_summary(tmp_path):
    store = AgentAttributionStore(path=str(tmp_path / 'attrib.json'))
    store.append({'contributors': [{'agent': 'RiskAgent', 'followed': True, 'realized_pnl_impact_usd': 2.5, 'precision_hit': True}]})
    snap = store.summary()
    assert snap['agents'][0]['agent'] == 'RiskAgent'
    assert snap['agents'][0]['precision'] == 1.0


from victor_ai_bot.aqe.agents.hub import AgentHub
from victor_ai_bot.agents.contracts import mandate_for


def test_agent_hub_exposes_full_specialist_roster_and_portfolio_manager(tmp_path):
    hub = AgentHub(data_dir=str(tmp_path))
    state = {
        'local': {'margin_ratio': 0.002, 'gas_ratio': 0.0003, 'p_success': 0.92, 'legs': 2, 'ev_wei': 1000},
        'dex': {'mid': 101.0, 'opps_per_block': 5},
        'cex': {'mid': 100.0, 'spread_bps': 8.0, 'depth_usd': 2.0, 'funding_bps': 3.0, 'funding_change_bps': 1.0},
        'mev': {'sandwich_risk': 0.2, 'router_flow': 0.3},
        'treasury': {'borrow_mult_target_cap': 1.5, 'aggressiveness_level': 'LOW', 'urgency_factor': 0.0},
        'wallets': {'flow': 0.2, 'whale': 0.1},
        'liq': {'intensity': 0.2},
        'sent': {'score': 0.1},
    }
    out = hub.step(state=state)
    expected = [
        'Ben Graham Agent', 'Bill Ackman Agent', 'Cathie Wood Agent', 'Charlie Munger Agent',
        'Phil Fisher Agent', 'Stanley Druckenmiller Agent', 'Warren Buffett Agent',
        'Valuation Agent', 'Sentiment Agent', 'Fundamentals Agent', 'Technicals Agent', 'Risk Manager'
    ]
    for name in expected:
        assert name in out.outputs
        assert name in out.signals
        assert mandate_for(name).role
    assert 'Portfolio Manager' in out.outputs
    assert out.portfolio_manager
    assert 'weights_used' in out.outputs['Portfolio Manager']


def test_agent_weighting_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "weights.json"
    path.write_text("{not-json", encoding="utf-8")
    gov = AgentWeightingGovernor(path=str(path))
    assert gov.snapshot() == {"metrics": {}}


def test_agent_weighting_sanitizes_partially_malformed_state(tmp_path):
    path = tmp_path / "weights.json"
    path.write_text(
        __import__("json").dumps(
            {
                "metrics": {
                    "RiskAgent|balanced": {
                        "count": "3",
                        "precision_hits": "2",
                        "followed": 99,
                        "realized_edge_usd": "4.5",
                        "junk": "drop-me",
                    },
                    "Bad|balanced": "not-a-dict",
                    "Ugly|balanced": {"count": "oops"},
                }
            }
        ),
        encoding="utf-8",
    )
    gov = AgentWeightingGovernor(path=str(path))
    snap = gov.snapshot()
    assert list(snap["metrics"].keys()) == ["RiskAgent|balanced"]
    assert snap["metrics"]["RiskAgent|balanced"] == {
        "count": 3,
        "precision_hits": 2,
        "followed": 3,
        "realized_edge_usd": 4.5,
    }


def test_agent_attribution_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / 'attrib.json'
    path.write_text('{not-json', encoding='utf-8')
    store = AgentAttributionStore(path=str(path))
    assert store.load() == []


def test_agent_attribution_sanitizes_partially_malformed_state(tmp_path):
    import json
    path = tmp_path / 'attrib.json'
    path.write_text(
        json.dumps([
            {
                'contributors': [
                    {'agent': 'RiskAgent', 'followed': True, 'realized_pnl_impact_usd': '2.5', 'precision_hit': True},
                    {'agent': '', 'followed': True, 'realized_pnl_impact_usd': 9, 'precision_hit': True},
                    {'agent': 'BadPnl', 'realized_pnl_impact_usd': 'oops'},
                    'junk',
                ],
                'junk': 'drop-me',
            },
            'not-a-dict',
            {'contributors': 'not-a-list'},
        ]),
        encoding='utf-8',
    )
    store = AgentAttributionStore(path=str(path))
    rows = store.load()
    assert rows == [
        {
            'contributors': [
                {'agent': 'RiskAgent', 'followed': True, 'realized_pnl_impact_usd': 2.5, 'precision_hit': True},
                {'agent': 'BadPnl', 'followed': False, 'realized_pnl_impact_usd': 0.0, 'precision_hit': False},
            ]
        }
    ]
