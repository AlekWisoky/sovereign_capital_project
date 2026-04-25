from victor_ai_bot.strategies.catalog import annotate_strategy_metadata
from victor_ai_bot.strategies.family_scorecards import FamilyScorecardStore
from victor_ai_bot.strategies.interactions import interaction_conflicts


def test_strategy_family_metadata():
    m = annotate_strategy_metadata(strategy_name='flashloan_atomic', regime='balanced')
    assert m['family'] == 'flashloan_atomic'
    assert m['regime_allowed'] is True


def test_strategy_interaction_conflicts():
    x = interaction_conflicts(used_pools=['poolA'], strategy_family='flashloan_atomic', other_families=['flashloan_atomic'])
    assert x['allow'] is False


def test_family_scorecards(tmp_path):
    s = FamilyScorecardStore(str(tmp_path / 'score.json'))
    s.observe(family='flashloan_atomic', realized_pnl_usd=5.0, gas_cost_usd=1.0, ok=True, regime='balanced')
    snap = s.snapshot()
    assert snap['families'][0]['gasEfficiency'] == 5.0


def test_family_scorecards_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / 'score.json'
    path.write_text('{not-json', encoding='utf-8')

    store = FamilyScorecardStore(str(path), chain='corrupt')
    assert store.snapshot() == {'families': []}

    store.observe(
        family='flashloan_atomic',
        realized_pnl_usd=3.0,
        gas_cost_usd=1.0,
        ok=True,
        regime='balanced',
    )
    snap = store.snapshot()
    assert snap['families'][0]['family'] == 'flashloan_atomic'
    assert snap['families'][0]['gasEfficiency'] == 3.0



def test_family_scorecards_sanitizes_partial_persisted_state(tmp_path):
    path = tmp_path / 'score.json'
    path.write_text(
        '''
        {
          "flashloan_atomic": {
            "count": "4",
            "realizedPnlUsd": "12.5",
            "gasCostUsd": "2.5",
            "successes": "3",
            "drawdownPenalty": "1.0",
            "correlationPenalty": "0.2",
            "regimes": {
              "balanced": {
                "count": "4",
                "pnlUsd": "12.5",
                "successes": "3",
                "gasUsd": "2.5"
              },
              "bad": [1, 2, 3]
            }
          },
          "funding_arb": [1, 2, 3]
        }
        ''',
        encoding='utf-8',
    )

    store = FamilyScorecardStore(str(path), chain='sanitize')
    snap = store.snapshot()
    families = {item['family']: item for item in snap['families']}

    assert set(families) == {'flashloan_atomic', 'funding_arb'}
    assert families['flashloan_atomic']['count'] == 4
    assert families['flashloan_atomic']['realizedPnlUsd'] == 12.5
    assert families['flashloan_atomic']['regimeDependence'] == {'balanced': 4}
    assert families['funding_arb']['count'] == 0
    assert families['funding_arb']['regimeDependence'] == {}
