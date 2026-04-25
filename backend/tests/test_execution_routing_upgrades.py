import json
from types import SimpleNamespace

from victor_ai_bot.execution_capture.adversarial_state import evaluate_adversarial_state
from victor_ai_bot.execution_capture.decision_engine import ExecutionDecisionEngine
from victor_ai_bot.execution_capture.endpoint_quality import EndpointQualityStore
from victor_ai_bot.execution_capture.smart_order_router import VenueScorecardStore, plan_route
from victor_ai_bot.execution_capture.telemetry import ExecutionTelemetryStore
from victor_ai_bot.execution_capture.template_cache import RouteTemplateCache


def _opp(*, latency_half_life_ms=800, age_ms=0, mev_risk=0.1, expected_profit_usd=120.0):
    legs = [
        SimpleNamespace(venue='uni', token_in='WETH', token_out='USDC'),
        SimpleNamespace(venue='curve', token_in='USDC', token_out='WETH'),
    ]
    return SimpleNamespace(
        id='opp-1',
        route_id='route-1',
        strategy='flash_arb',
        expected_profit_usd=expected_profit_usd,
        route=SimpleNamespace(legs=legs),
        meta={
            'age_ms': age_ms,
            'p_success': 0.9,
            'margin_ratio': 0.05,
            'freshness_score': 0.95,
            'liquidity_fragility': 0.55,
            'slippage_sensitivity': 0.25,
            'latency_half_life_ms': latency_half_life_ms,
            'strategy_family': 'flashloan_atomic',
            'candidate_endpoints': ['rpc-fast', 'rpc-slow'],
            'candidate_relays': ['relay-a'],
            'flash_providers': ['aave', 'balancer'],
            'aqe': {'mev_risk': mev_risk},
        },
    )


def test_endpoint_quality_prefers_fast_successful_endpoint(tmp_path):
    store = EndpointQualityStore(data_dir=str(tmp_path), chain='eth')
    for _ in range(5):
        store.observe(lane='PRIVATE', endpoint='rpc-fast', latency_ms=120, ok=True, timeout=False, error=False)
        store.observe(lane='PRIVATE', endpoint='rpc-slow', latency_ms=950, ok=False, timeout=True, error=True)
    choice = store.choose(lane='PRIVATE', endpoints=['rpc-fast', 'rpc-slow'], relays=['relay-a'])
    assert choice['endpoint'] == 'rpc-fast'
    assert choice['pressure_class'] in {'low', 'medium', 'normal'}
    assert choice['endpoint_quality'] > 0.7


def test_sor_plans_best_route_and_fallback(tmp_path):
    telemetry = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    cache = RouteTemplateCache(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=telemetry, template_cache=cache)
    engine.endpoint_quality = EndpointQualityStore(data_dir=str(tmp_path), chain='eth')
    scorecards = VenueScorecardStore(data_dir=str(tmp_path), chain='eth')
    scorecards.observe(pair='WETH/USDC', size_bucket='M', latency_class='fast', venue='curve', success=True, realized_edge_usd=8.0)
    scorecards.observe(pair='WETH/USDC', size_bucket='M', latency_class='fast', venue='uni', success=False, realized_edge_usd=-1.0)
    engine.venue_scorecards = scorecards
    for _ in range(5):
        engine.endpoint_quality.observe(lane='PRIVATE', endpoint='rpc-fast', latency_ms=90, ok=True, timeout=False, error=False)
    opp = _opp(expected_profit_usd=260.0, mev_risk=0.02)
    decision = engine.evaluate(opp, chain_id=1, regime='balanced', public_mode=False, force_send_mode='private')
    assert decision.metadata['route_plan']['selected_venues']
    assert decision.metadata['route_plan']['fallback_tree']
    assert decision.metadata['route_plan']['fallback_tree']
    assert decision.metadata['endpoint_selection']['endpoint']



def test_latency_half_life_rejects_fragile_opportunity(tmp_path):
    telemetry = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    cache = RouteTemplateCache(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=telemetry, template_cache=cache)
    eq = EndpointQualityStore(data_dir=str(tmp_path), chain='eth')
    for _ in range(4):
        eq.observe(lane='PUBLIC', endpoint='rpc-slow', latency_ms=1800, ok=True, timeout=False, error=False)
    engine.endpoint_quality = eq
    opp = _opp(latency_half_life_ms=300, expected_profit_usd=40.0)
    decision = engine.evaluate(opp, chain_id=1, regime='balanced', public_mode=True)
    assert decision.action == 'drop'
    assert decision.drop_reason == 'edge_half_life_below_pipeline_latency'



def test_adversarial_state_requires_private_lane_for_conflicted_pending():
    envelope = SimpleNamespace(
        venues=['uni', 'curve'],
        token_path=['WETH', 'USDC', 'WETH'],
        mempool_copy_risk=0.7,
        latency_half_life_ms=900,
        private_send_preference=False,
    )
    pending = [
        {'pool': 'uni', 'token_in': 'WETH', 'token_out': 'USDC'},
        {'venue': 'curve', 'pair': 'USDC/WETH'},
        {'token': 'WETH'},
    ]
    adv = evaluate_adversarial_state(envelope=envelope, pending_source=pending, base_expected_value=15.0, lane_hint='PUBLIC')
    assert adv['interference_probability'] > 0.0
    assert adv['requires_private_lane'] is True
    assert adv['relay_necessity'] >= 0.5



def test_plan_route_is_deterministic_for_same_inputs(tmp_path):
    telemetry = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    cache = RouteTemplateCache(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=telemetry, template_cache=cache)
    opp = _opp()
    envelope = engine.evaluate(opp, chain_id=1, regime='balanced').metadata['envelope']
    # Rebuild using plain namespaces to keep deterministic path.
    env_ns = SimpleNamespace(**{k: v for k, v in envelope.items() if k != 'safe_size_curve'})
    env_ns.safe_size_curve = [SimpleNamespace(**pt) for pt in envelope['safe_size_curve']]
    capture = engine.evaluate(opp, chain_id=1, regime='balanced').capture_score
    p1 = plan_route(envelope=env_ns, capture=capture, telemetry={}, latency_pressure=0.1)
    p2 = plan_route(envelope=env_ns, capture=capture, telemetry={}, latency_pressure=0.1)
    assert p1.to_dict() == p2.to_dict()



def test_flashloan_resilience_prefers_redundant_provider(tmp_path):
    telemetry = ExecutionTelemetryStore(data_dir=str(tmp_path), chain='eth')
    cache = RouteTemplateCache(data_dir=str(tmp_path), chain='eth')
    engine = ExecutionDecisionEngine(telemetry=telemetry, template_cache=cache)
    opp = _opp(expected_profit_usd=180.0, mev_risk=0.55)
    decision = engine.evaluate(opp, chain_id=1, regime='volatile', public_mode=False, force_send_mode='private')
    flash = decision.metadata['flashloan_resilience']
    assert flash['provider_priority']
    assert 'require_fallback_tree' in flash


def test_route_template_cache_recovers_from_corrupt_json(tmp_path):
    cache_dir = tmp_path / "data"
    path = cache_dir / "execution_capture" / "templates_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")

    cache = RouteTemplateCache(data_dir=str(cache_dir), chain="eth")

    assert cache.snapshot() == {"by_family": {}, "by_route_id": {}}


def test_route_template_cache_sanitizes_partial_payloads(tmp_path):
    cache_dir = tmp_path / "data"
    path = cache_dir / "execution_capture" / "templates_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "by_family": {
                    "flash": {
                        "route_id": 123,
                        "metadata": {"lane": "PRIVATE"},
                        "updated_ts_ms": "1700",
                    },
                    "bad": ["not", "a", "mapping"],
                },
                "by_route_id": {
                    "route-1": {
                        "route_id": "route-1",
                        "metadata": ["bad"],
                        "updated_ts_ms": None,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    cache = RouteTemplateCache(data_dir=str(cache_dir), chain="eth")

    assert cache.get("flash") == {
        "route_id": "123",
        "metadata": {"lane": "PRIVATE"},
        "updated_ts_ms": 1700,
    }
    assert cache.get("route-1") == {
        "route_id": "route-1",
        "metadata": {},
        "updated_ts_ms": 0,
    }
    assert "bad" not in cache.snapshot()["by_family"]


def test_venue_scorecard_store_recovers_from_corrupt_json(tmp_path):
    cache_dir = tmp_path / "data"
    path = cache_dir / "execution_capture" / "venue_scorecards_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")

    store = VenueScorecardStore(data_dir=str(cache_dir), chain="eth")

    assert store.snapshot() == {"items": []}


def test_venue_scorecard_store_sanitizes_partial_payloads(tmp_path):
    cache_dir = tmp_path / "data"
    path = cache_dir / "execution_capture" / "venue_scorecards_eth.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "items": {
                    "good": {
                        "pair": "WETH/USDC",
                        "size_bucket": 123,
                        "latency_class": "fast",
                        "venue": "curve",
                        "attempts": "5",
                        "successes": "7",
                        "realized_edge_usd_sum": "12.5",
                    },
                    "bad": ["not", "a", "mapping"],
                }
            }
        ),
        encoding="utf-8",
    )

    store = VenueScorecardStore(data_dir=str(cache_dir), chain="eth")

    snapshot = store.snapshot()
    assert len(snapshot["items"]) == 1
    item = snapshot["items"][0]
    assert item["key"] == "WETH/USDC|123|fast|curve"
    assert item["pair"] == "WETH/USDC"
    assert item["size_bucket"] == "123"
    assert item["latency_class"] == "fast"
    assert item["venue"] == "curve"
    assert item["attempts"] == 5
    assert item["success_rate"] == 1.0
    assert item["mean_edge_usd"] == 2.5
