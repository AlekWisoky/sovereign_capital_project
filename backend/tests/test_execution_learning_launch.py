from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.execution_capture.edge_model import ExecutionLearningEngine
from victor_ai_bot.execution_capture.edge_predictions import EdgePrediction
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint
from victor_ai_bot.fund_os.staged_rollout import StagedRolloutManager
from victor_ai_bot.server import app


def make_env(route_family: str = 'flash_arb'):
    return OpportunityEnvelope(
        opportunity_id='opp-1',
        route_id='route-1',
        route_family=route_family,
        expected_profit_usd=12.0,
        gas_estimate_usd=2.0,
        slippage_sensitivity=0.2,
        liquidity_fragility=0.4,
        latency_half_life_ms=700,
        mempool_copy_risk=0.55,
        venue_reliability_score=0.8,
        simulation_confidence=0.82,
        safe_size_curve=[SafeSizePoint(size_mult=1.0, expected_profit_usd=12.0, slippage_cost_usd=0.2, interference_penalty_usd=0.1, latency_decay_cost_usd=0.1)],
        failure_cost_estimate=1.0,
        freshness_score=0.85,
        private_send_preference=True,
        chain_id=1,
        token_path=['WETH', 'USDC'],
        venues=['univ3'],
        metadata={'strategy_family': route_family},
    )


def test_edge_learning_updates_and_quarantine(tmp_path):
    eng = ExecutionLearningEngine(data_dir=str(tmp_path), chain='eth')
    env = make_env()
    pred = eng.predict(envelope=env, regime='balanced', lane_hint='PRIVATE', telemetry={})
    assert 0 < pred.success_probability <= 1
    assert pred.data_sufficiency == 0
    for _ in range(3):
        eng.observe(envelope=env, regime='balanced', lane='PUBLIC', telemetry={}, prediction=pred, actual_success=False, actual_realized_edge_usd=-1.0, actual_competed_out=True)
    snap = eng.snapshot()
    assert snap['quarantine']
    pred2 = eng.predict(envelope=env, regime='balanced', lane_hint='PUBLIC', telemetry={})
    assert 'route_quarantined' in pred2.reason_codes


def test_confidence_to_size_scaling(tmp_path):
    eng = ExecutionLearningEngine(data_dir=str(tmp_path), chain='eth')
    lo = eng.confidence_to_size_scale(EdgePrediction(0.4, 0.6, 0.9, 0.8, 0.8, data_sufficiency=0.0))
    hi = eng.confidence_to_size_scale(EdgePrediction(0.9, 0.1, 1.1, 1.0, 1.0, data_sufficiency=1.0))
    assert hi > lo


def test_launch_rollout_recommends_funding_when_execution_truth_is_live_and_receipt_truth_is_fresh(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain='eth')
    rec = mgr.recommendation(
        stage='pilot_capital',
        scorecards={'families': [{'family': 'flash_arb', 'count': 20, 'executionSuccessRate': 0.92, 'gasEfficiency': 4.0}, {'family': 'funding_arb', 'count': 7, 'executionSuccessRate': 0.84, 'gasEfficiency': 1.2}]},
        engine_state={
            'summary': {'engines': [{'engine_type': 'funding_arb', 'mode': 'capped_live'}]},
            'items': [
                {
                    'opportunity': {'strategy_family': 'funding_arb', 'expected_profit_usd': 11.0},
                    'admission': {'allowed': True, 'mode': 'capped_live'},
                    'capture': {'action': 'trade'},
                }
            ],
        },
        telemetry={},
        calibration={'items': [{'route_family': 'funding_arb', 'lane': 'PROTECTED', 'calibration_factor': 0.98}]},
        fund_summary={
            'fundStage': 'internal_capital',
            'privateRoutingReady': True,
            'capitalReady': True,
            'internalPrimeReady': True,
            'receiptOutcomeTruthFreshnessClass': 'current',
            'receiptOutcomeTruthFreshnessReasonCodes': [],
            'receiptOutcomeTruthReliabilityClass': 'stable',
            'receiptOutcomeTruthReliabilityReasonCode': 'ok',
            'receiptOutcomeTruthReliabilityReasonCodes': [],
        },
    )
    assert rec['recommended_next_family'] == 'funding_arb'


def test_launch_rollout_blocks_funding_when_receipt_truth_is_not_rollout_ready(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain='eth')
    rec = mgr.recommendation(
        stage='pilot_capital',
        scorecards={'families': [{'family': 'flash_arb', 'count': 20, 'executionSuccessRate': 0.92, 'gasEfficiency': 4.0}, {'family': 'funding_arb', 'count': 7, 'executionSuccessRate': 0.84, 'gasEfficiency': 1.2}]},
        engine_state={
            'summary': {'engines': [{'engine_type': 'funding_arb', 'mode': 'capped_live'}]},
            'items': [
                {
                    'opportunity': {'strategy_family': 'funding_arb', 'expected_profit_usd': 11.0},
                    'admission': {'allowed': True, 'mode': 'capped_live'},
                    'capture': {'action': 'trade'},
                }
            ],
        },
        telemetry={},
        calibration={'items': [{'route_family': 'funding_arb', 'lane': 'PROTECTED', 'calibration_factor': 0.98}]},
        fund_summary={
            'fundStage': 'internal_capital',
            'privateRoutingReady': True,
            'capitalReady': True,
            'internalPrimeReady': True,
            'receiptOutcomeTruthFreshnessClass': 'unavailable',
            'receiptOutcomeTruthFreshnessReasonCodes': ['receipt_outcome_truth_freshness_unavailable'],
            'receiptOutcomeTruthReliabilityClass': 'unavailable',
            'receiptOutcomeTruthReliabilityReasonCode': 'receipt_outcome_truth_reliability_unavailable',
            'receiptOutcomeTruthReliabilityReasonCodes': ['receipt_outcome_truth_reliability_unavailable'],
        },
    )
    assert rec['recommended_next_family'] == ''
    assert rec['blocked_family_details']['funding_arb']['reason_code'] == 'receipt_outcome_truth_freshness_unavailable'
    assert rec['blocked_family_details']['funding_arb']['suggested_next_action'] == 'restore_receipt_outcome_truth'


def test_launch_v1_only_blocks_nonapproved_family(tmp_path):
    mgr = StagedRolloutManager(data_dir=str(tmp_path), chain='eth')
    mgr.set_mode('V1_ONLY')
    out = mgr.enable_family(
        'mev_search',
        stage='internal_capital',
        scorecards={'families': [{'family': 'mev_search', 'count': 8, 'executionSuccessRate': 0.9, 'gasEfficiency': 1.0}]},
        engine_state={'summary': {'engines': []}},
        telemetry={},
        calibration={},
        fund_summary={'fundStage': 'internal_capital', 'privateRoutingReady': False},
    )
    assert out['ok'] is False
    assert out['reason_code'] in {'private_routing_not_ready', 'stage_restriction', 'degraded_engine_state', 'launch_mode_v1_only'}


def test_launch_state_route_present():
    client = TestClient(app)
    r = client.get('/api/launch/state')
    assert r.status_code == 200
    assert r.json().get('ok') in {True, False}


def test_edge_learning_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "execution_capture" / "edge_learning_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{bad json", encoding="utf-8")

    eng = ExecutionLearningEngine(data_dir=str(tmp_path), chain="eth")

    assert eng.snapshot()["quarantine"] == {}
    assert eng.snapshot()["items"] == []


def test_edge_learning_sanitizes_partially_malformed_state(tmp_path):
    path = tmp_path / "execution_capture" / "edge_learning_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        __import__("json").dumps(
            {
                "priors": {
                    "valid-key": {
                        "family": "flash_arb",
                        "route_family": "flash_arb",
                        "venue": "univ3",
                        "lane": "PRIVATE",
                        "regime": "balanced",
                        "count": "3",
                        "success_ewma": "0.8",
                        "competition_ewma": None,
                        "quality_ewma": "1.1",
                        "freshness_ewma": "0.9",
                        "slippage_bias_ewma": "0.05",
                        "failure_risk_ewma": "0.2",
                        "updated_ts_ms": "1234",
                    },
                    "bad-key": "oops",
                },
                "quarantine": {
                    "valid-key": {"recent_failures": "2", "until_ts_ms": "4567"},
                    "bad-key": [1, 2, 3],
                },
            }
        ),
        encoding="utf-8",
    )

    eng = ExecutionLearningEngine(data_dir=str(tmp_path), chain="eth")
    snap = eng.snapshot()
    assert snap["quarantine"] == {"valid-key": {"recent_failures": 2, "until_ts_ms": 4567}}
    assert snap["items"] == [
        {
            "key": "valid-key",
            "family": "flash_arb",
            "route_family": "flash_arb",
            "venue": "univ3",
            "lane": "PRIVATE",
            "regime": "balanced",
            "count": 3,
            "success_ewma": 0.8,
            "competition_ewma": 0.0,
            "quality_ewma": 1.1,
            "freshness_ewma": 0.9,
            "slippage_bias_ewma": 0.05,
            "failure_risk_ewma": 0.2,
            "updated_ts_ms": 1234,
        }
    ]
