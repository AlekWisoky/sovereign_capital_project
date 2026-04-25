import json

from victor_ai_bot.aqe.meta.memory import StrategyMemory


def test_strategy_memory_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / 'meta_memory.json'
    path.write_text('{not-valid-json', encoding='utf-8')

    memory = StrategyMemory(str(path))

    assert memory.load() == []
    assert memory.summary() == {'count': 0, 'stages': {}, 'byRegime': {}}


def test_strategy_memory_sanitizes_partially_malformed_state(tmp_path):
    path = tmp_path / 'meta_memory.json'
    path.write_text(
        json.dumps(
            [
                {
                    'id': 'good-1',
                    'lifecycle_stage': 'candidate',
                    'regime_tags': ['trend', 7, None],
                    'score': '1.5',
                    'created_ts': '42',
                    'genealogy_depth': '3',
                    'settings_patch': {'foo': 'bar'},
                    'stress_report': {'ok': True},
                },
                {
                    'id': 'good-2',
                    'lifecycle_stage': 'live',
                    'regime_tags': 'not-a-list',
                    'score': 'oops',
                    'parent_ids': ['p1', 2],
                    'mutation_history': ['m1', None],
                },
                {
                    'id': None,
                    'lifecycle_stage': 'broken',
                },
                'junk-row',
            ]
        ),
        encoding='utf-8',
    )

    memory = StrategyMemory(str(path))
    items = memory.load()

    assert len(items) == 2
    assert items[0]['id'] == 'good-1'
    assert items[0]['score'] == 1.5
    assert items[0]['created_ts'] == 42
    assert items[0]['genealogy_depth'] == 3
    assert items[0]['regime_tags'] == ['trend', '7']
    assert items[0]['settings_patch'] == {'foo': 'bar'}
    assert items[0]['stress_report'] == {'ok': True}

    assert items[1]['id'] == 'good-2'
    assert items[1]['lifecycle_stage'] == 'live'
    assert items[1]['parent_ids'] == ['p1', '2']
    assert items[1]['mutation_history'] == ['m1']
    assert 'score' not in items[1]
    assert 'regime_tags' not in items[1]

    assert memory.get('good-2')['id'] == 'good-2'
    assert memory.summary() == {
        'count': 2,
        'stages': {'candidate': 1, 'live': 1},
        'byRegime': {'trend': 1, '7': 1},
    }
