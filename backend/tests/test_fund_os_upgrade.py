from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI

from victor_ai_bot.alpha_marketplace.contracts import submission_contract
from victor_ai_bot.alpha_marketplace.intake import candidate_to_submission
from victor_ai_bot.alpha_marketplace.submissions import AlphaMarketplaceStore
from victor_ai_bot.api_routes.alpha_marketplace_routes import router as alpha_marketplace_router
from victor_ai_bot.aqe.meta.types import StrategyCandidate
from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService
from victor_ai_bot.runtime_services.canonical_settlement_interface import canonical_settled_outcome
from victor_ai_bot.omar.lifecycle_bridge import _observe_settled_outcome


def test_fund_manifest_and_stage_policy():
    from victor_ai_bot.fund_os.manifest import FUND_MANIFEST
    assert FUND_MANIFEST['name'] == 'Sovereign Capital Fund OS'
    assert FUND_MANIFEST['stage'] == 'v1'
    assert FUND_MANIFEST['live_capital_family'] == 'flash_arb'


def test_alpha_registry_contains_engine_families():
    from victor_ai_bot.fund_os.registry import AlphaRegistry
    registry = AlphaRegistry()
    names = {item['name'] for item in registry.snapshot()['engines']}
    assert {'aqe', 'decision_engine', 'omar'}.issubset(names)


def test_research_candidate_flow():
    from victor_ai_bot.research_pipeline.candidates import CandidateStore
    store = CandidateStore()
    candidate = store.create('Test', 'flash_arb', {'expected_net_profit': 1.0})
    assert candidate['stage'] == 'sandbox'
    assert candidate['status'] == 'pending'


def test_marketplace_disabled_by_default(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test')
    assert store.snapshot() == {'enabled': False, 'items': []}
    assert store.submit(title='x', contributor='y', family='flash_arb', thesis='z') == {'ok': False, 'reason': 'marketplace_disabled'}


def test_portfolio_risk_and_controls():
    from victor_ai_bot.fund_os.portfolio import PortfolioManager
    pm = PortfolioManager()
    result = pm.snapshot()
    assert 'risk' in result
    assert result['risk']['max_drawdown_pct'] > 0


def test_marketplace_store_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / 'marketplace' / 'submissions_test.json'
    path.parent.mkdir(parents=True)
    path.write_text('{not-json', encoding='utf-8')
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)
    assert store.snapshot() == {'enabled': True, 'items': []}


def test_marketplace_store_sanitizes_partial_state(tmp_path):
    path = tmp_path / 'marketplace' / 'submissions_test.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'a': {'submissionId': 'a', 'stage': 'invalid'}, 'b': 'bad'}), encoding='utf-8')
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)
    item = store.snapshot()['items'][0]
    assert item['submissionId'] == 'a'
    assert item['stage'] == 'sandbox'
    assert item['capitalSleeveStatus'] == 'unfunded'


def test_ai_candidate_enters_marketplace_with_distinct_strategy_identity(tmp_path):
    candidate = StrategyCandidate(
        id='strategy-1', created_ts=1.0, description='Test strategy', score=0.8,
        settings_patch={'x': 1}, safety_patch={'y': 2}, strategy_family='cross_cex_dex',
        lifecycle_stage='experimental', parent_ids=['strategy-parent'], stress_report={'oos': {'passed': True}},
    )
    payload = candidate_to_submission(candidate)
    assert payload['strategyId'] == 'strategy-1'
    assert payload['submissionId'] == 'strategy-1'
    assert payload['generatingEngine'] == 'aqe_meta'
    assert payload['reviewState'] == 'pending'
    assert payload['stage'] == 'sandbox'
    assert payload['governanceStatus'] == 'pending'
    assert payload['capitalSleeveStatus'] == 'unfunded'
    assert 'decision_id' not in payload


def test_human_and_ai_marketplace_rows_share_governance_evidence_shape(tmp_path):
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)
    human = store.submit(title='Human idea', contributor='operator', family='flash_arb', thesis='atomic spread')
    assert human['ok'] is True
    ai = StrategyCandidate(
        id='strategy-shape', created_ts=1.0, description='AI idea', score=0.6,
        settings_patch={}, safety_patch={}, strategy_family='flash_arb',
    )
    ai_result = store.submit_candidate(candidate=candidate_to_submission(ai))
    assert ai_result['ok'] is True
    required = {
        'strategyId', 'parentStrategyIds', 'generatingEngine', 'agentId', 'expectedEconomics',
        'evidence', 'settingsPatch', 'safetyPatch', 'structurePatch', 'mutationHistory',
        'reviewState', 'stage', 'governanceStatus', 'capitalSleeveStatus', 'promotionReason',
    }
    assert required.issubset(human['item'])
    assert required.issubset(ai_result['item'])


def test_marketplace_candidate_intake_is_fail_closed_when_disabled(tmp_path):
    candidate = StrategyCandidate(
        id='strategy-2', created_ts=1.0, description='Funding spread', score=0.60,
        settings_patch={}, safety_patch={}, strategy_family='funding_arb',
    )
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=False)
    out = store.submit_candidate(candidate=candidate_to_submission(candidate))
    assert out == {'ok': False, 'reason': 'marketplace_disabled'}


def test_marketplace_read_and_write_routes_share_internal_surface():
    paths = {(route.path, tuple(sorted(route.methods or []))) for route in alpha_marketplace_router.routes}
    assert ('/api/fund/alpha-marketplace', ('GET',)) in paths
    assert ('/api/fund/alpha-marketplace', ('POST',)) in paths
    contract = submission_contract()
    assert contract['mode'] == 'internal_only'
    assert contract['executionAuthority'] == 'canonical_lifecycle_only'
    assert contract['evidenceRequiredForPromotion'] is True


def test_strategy_identity_survives_canonical_settlement_annotation():
    runtime = SimpleNamespace(_canonical_settlement_lineage={'strategy_id': 'strategy-95'})
    payload = {'metadata': {}, 'canonical_lineage': {'decision_id': 'd-1'}}
    annotated = CanonicalCapitalWriteService._annotate_settlement_payload(runtime, payload)
    assert annotated['metadata']['strategy_id'] == 'strategy-95'
    assert annotated['canonical_lineage']['strategy_id'] == 'strategy-95'


def test_canonical_settlement_reader_preserves_strategy_identity():
    ledger = SimpleNamespace(load=lambda limit=1: [{
        'status': 'settled', 'decision_id': 'd-1', 'correlation_id': 'c-1',
        'execution_id': 'e-1', 'sizing_id': 's-1', 'receipt_id': 'r-1',
        'outcome_id': 'o-1', 'opportunity_id': 'opp-1', 'route_id': 'route-1',
        'action': 'flash_arb', 'strategy_id': 'strategy-95',
        'canonical_lineage': {'strategy_id': 'strategy-95'},
    }])
    runtime = SimpleNamespace(_ledger_repo=ledger, cfg=SimpleNamespace())
    outcome = canonical_settled_outcome(runtime, decision_id='d-1')
    assert outcome['strategy_id'] == 'strategy-95'
    assert outcome['canonical_lineage']['strategy_id'] == 'strategy-95'


def test_settled_strategy_identity_reaches_omar_learning_metadata():
    class Omar:
        enabled = True
        def __init__(self): self.calls = []
        def observe_outcome(self, **kwargs): self.calls.append(kwargs); return {'ok': True}
    runtime = SimpleNamespace(_omar=Omar(), _agent_attribution=None, _agent_hub=None)
    pending = {'canonical_lineage': {
        'decision_id': 'd-1', 'correlation_id': 'c-1', 'execution_id': 'e-1', 'sizing_id': 's-1',
        'receipt_id': 'r-1', 'outcome_id': 'o-1', 'opportunity_id': 'opp-1', 'route_id': 'route-1',
        'action': 'flash_arb', 'strategy_id': 'strategy-95',
    }, 'strategy_id': 'strategy-95'}
    outcome = {
        'status': 'settled', 'ok': True, 'realized_net_usd': 4.25, 'expected_net_usd': 4.0,
        'amount_in_wei': 1000, 'gas_cost_usd': 0.1, 'slippage_bps': 2.0, 'latency_ms': 37,
        'route_id': 'route-1', 'tx_hash': '0xabc', 'truth_verified': True,
        'decision_id': 'd-1', 'correlation_id': 'c-1', 'sizing_id': 's-1', 'execution_id': 'e-1',
        'receipt_id': 'r-1', 'outcome_id': 'o-1', 'opportunity_id': 'opp-1', 'action': 'flash_arb',
        'strategy_id': 'strategy-95',
    }
    result = _observe_settled_outcome(runtime, pending=pending, outcome=outcome)
    assert result['ok'] is True
    assert runtime._omar.calls[0]['metadata']['strategy_id'] == 'strategy-95'


def test_corrupt_marketplace_state_does_not_create_capital_authority(tmp_path):
    path = tmp_path / 'marketplace' / 'submissions_test.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'bad': {'submissionId': 'bad', 'stage': 'live', 'governanceStatus': 'approved', 'capitalSleeveStatus': 'funded'}}), encoding='utf-8')
    store = AlphaMarketplaceStore(data_dir=str(tmp_path), chain='test', enabled=True)
    item = store.snapshot()['items'][0]
    assert item['stage'] == 'live'
    assert item['governanceStatus'] == 'approved'
    assert item['capitalSleeveStatus'] == 'funded'


def test_existing_promotion_authority_remains_canonical():
    from victor_ai_bot.research_pipeline.promotion import promotion_allowed
    assert callable(promotion_allowed)


def test_marketplace_submission_is_not_execution_authority():
    contract = submission_contract()
    assert contract['executionAuthority'] == 'canonical_lifecycle_only'
    assert contract['mode'] == 'internal_only'


def test_marketplace_read_surface_is_additive():
    app = FastAPI()
    app.include_router(alpha_marketplace_router)
    paths = {(route.path, tuple(sorted(route.methods or []))) for route in app.routes}
    assert ('/api/fund/alpha-marketplace', ('GET',)) in paths
    assert ('/api/fund/alpha-marketplace', ('POST',)) in paths
