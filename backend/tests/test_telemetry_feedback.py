from victor_ai_bot.telemetry.store import TelemetryStore
from victor_ai_bot.telemetry.events import TelemetryEvent
from victor_ai_bot.telemetry.feedback import compute_feedback


def test_telemetry_rich_event_persistence_and_feedback(tmp_path):
    store = TelemetryStore(data_dir=str(tmp_path), chain='eth')
    store.append(TelemetryEvent(event_type='outcome', chain='eth', ts_ms=1, payload={'route_family': 'flash', 'strategy_family': 'flashloan_atomic', 'projected_realized_edge_usd': 10.0, 'actual_realized_edge_usd': 8.0, 'ok': True, 'contributors': [{'agent': 'RiskAgent', 'followed': True, 'realized_pnl_impact_usd': 1.0, 'precision_hit': True}]}))
    rows = store.tail(limit=10)
    assert len(rows) == 1
    fb = compute_feedback(rows)
    assert fb['realization']['families'][0]['realizationRatio'] == 0.8
    assert fb['agents']['agents'][0]['agent'] == 'RiskAgent'
