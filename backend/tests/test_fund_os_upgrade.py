from __future__ import annotations

from victor_ai_bot.alpha_marketplace.submissions import AlphaMarketplaceStore
from victor_ai_bot.alpha_platform.registry import alpha_engine_registry
from victor_ai_bot.fund_os.manifests import build_fund_manifest
from victor_ai_bot.research_pipeline.candidates import CandidateStore
from victor_ai_bot.research_pipeline.promotion import promotion_allowed
from victor_ai_bot.risk_engine.controls import risk_controls
from victor_ai_bot.risk_engine.portfolio_risk import compute_portfolio_risk


def test_fund_manifest_and_stage_policy():
    manifest = build_fund_manifest(stage='private_fund')
    stage = manifest['fund_os']['stage_policy']
    assert stage['stage'] == 'private_fund'
    assert 'research' in manifest['fund_os']['layers']
    assert stage['max_deployable_pct'] > 0.0


def test_alpha_registry_contains_engine_families():
    reg = alpha_engine_registry()
    assert 'cross_cex_dex' in reg['families']
    assert 'funding_arb' in reg['families']
    assert 'execution_capture' in reg['engines']


def test_research_candidate_flow(tmp_path):
    store = CandidateStore(data_dir=str(tmp_path), chain='test')
    item = store.create(family='auto_generated_strategy', origin='hybrid', thesis='Mean reversion after volatility shocks', owner='pm')
    assert item['stage'] == 'sandbox'
    decision = promotion_allowed(score=0.62, risk_score=0.40, stage='sandbox')
    assert decision['allowed'] is True
    promoted = store.transition(item['candidateId'], stage=decision['nextStage'], reason=decision['reason'], reviewer='reviewer')
    assert promoted['stage'] == 'paper'
    assert store.pipeline_counts()['paper'] == 1


def test_marketplace_disabled_by_default(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=False)
    out = store.submit(title='Idea', contributor='analyst', family='funding_arb', thesis='Capture funding spread')
    assert out['ok'] is False
    assert out['reason'] == 'marketplace_disabled'


def test_portfolio_risk_and_controls():
    capital_state = {
        'capital_engine': {'family_targets': {'flashloan_atomic': 0.4, 'funding_arb': 0.2}, 'drawdown_pct': 0.18},
        'capital_efficiency_metrics': {'utilizationRate': 0.72},
    }
    engine_state = {'summary': {'engines': [{'engine': 'mev_search', 'status': 'capped_live'}]}}
    risk = compute_portfolio_risk(capital_state=capital_state, covariance_penalties={'flashloan_atomic': 0.3}, engine_state=engine_state)
    assert risk['riskScore'] > 0.0
    ctrl = risk_controls(risk_score=risk['riskScore'], fund_stage=build_fund_manifest()['fund_os']['stage_policy'])
    assert 'deployableScale' in ctrl



def test_marketplace_store_recovers_from_corrupt_json(tmp_path):
    marketplace_dir = tmp_path / 'marketplace'
    marketplace_dir.mkdir()
    path = marketplace_dir / 'submissions_test.json'
    path.write_text('{not valid json', encoding='utf-8')

    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)

    assert store.snapshot() == {'enabled': True, 'items': []}



def test_marketplace_store_sanitizes_partial_state(tmp_path):
    marketplace_dir = tmp_path / 'marketplace'
    marketplace_dir.mkdir()
    path = marketplace_dir / 'submissions_test.json'
    path.write_text(
        __import__('json').dumps(
            {
                'row-1': {
                    'submissionId': 17,
                    'title': 'Basis trade',
                    'contributor': 'analyst',
                    'family': 'funding_arb',
                    'thesis': 'capture spread',
                    'reviewState': 'approved',
                    'stage': 'paper',
                    'createdTs': '42',
                    'profitSharingPlaceholder': 0,
                    'junk': 'drop-me',
                },
                'row-2': 'bad-entry',
            }
        ),
        encoding='utf-8',
    )

    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)
    snap = store.snapshot()

    assert snap['enabled'] is True
    assert len(snap['items']) == 1
    item = snap['items'][0]
    assert item['submissionId'] == '17'
    assert item['title'] == 'Basis trade'
    assert item['createdTs'] == 42
    assert item['profitSharingPlaceholder'] is False
    assert 'junk' not in item
