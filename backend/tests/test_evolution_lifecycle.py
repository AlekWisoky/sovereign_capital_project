from victor_ai_bot.evolution.diversity import diversity_score
from victor_ai_bot.evolution.validation import validate_multi_regime
from victor_ai_bot.evolution.lifecycle import next_stage
from victor_ai_bot.evolution.retirement import retirement_reason
from victor_ai_bot.evolution.genealogy import GenealogyStore


def test_genealogy_store(tmp_path):
    g = GenealogyStore(str(tmp_path / 'g.json'))
    g.append({'id': 'a', 'parent_ids': []})
    g.append({'id': 'b', 'parent_ids': ['a']})
    line = g.lineage('a')
    assert len(line) == 2


def test_diversity_and_validation():
    existing = [{'structure_patch': {'signals': ['spread', 'volatility_proxy']}, 'regime_tags': ['balanced']}]
    d = diversity_score(signals=['gas_pressure', 'latency_half_life'], existing=existing, regime='high_volatility')
    assert d['behavioral_novelty'] > 0.0
    v = validate_multi_regime(candidate={'regime_tags': ['balanced'], 'stress_report': {'robustness_score': 0.9}}, regimes=['balanced', 'bear'])
    assert v['passed_count'] >= 1


def test_lifecycle_and_retirement():
    assert next_stage(robustness=0.85, validation_ok=True, live_ok=True) == 'production'
    assert retirement_reason(robustness=0.2, realized_edge_usd=1.0, overlap_penalty=0.0, regime_fit=1.0) == 'robustness_gate_failure'


def test_genealogy_store_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / 'g.json'
    path.write_text('{bad json', encoding='utf-8')
    g = GenealogyStore(str(path))
    assert g.load() == []


def test_genealogy_store_sanitizes_partially_malformed_state(tmp_path):
    path = tmp_path / 'g.json'
    path.write_text(
        __import__('json').dumps([
            {
                'id': 'child',
                'parent_ids': ['root', '', 7],
                'mutation_history': ['mutate', None, ''],
                'generation_number': '2',
                'lifecycle_stage': 'paper',
                'retirement_reason': None,
                'strategy_family': 'funding_arb',
                'junk': 'discard',
            },
            {'id': '', 'parent_ids': ['ignored']},
            'bad-row',
        ]),
        encoding='utf-8',
    )
    g = GenealogyStore(str(path))
    rows = g.load()
    assert rows == [
        {
            'id': 'child',
            'parent_ids': ['root', '7'],
            'mutation_history': ['mutate'],
            'generation_number': 2,
            'lifecycle_stage': 'paper',
            'strategy_family': 'funding_arb',
        }
    ]
