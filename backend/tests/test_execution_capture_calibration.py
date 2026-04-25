from victor_ai_bot.execution_capture.calibration import EmpiricalCalibrationStore
from victor_ai_bot.execution_capture.no_trade_analytics import NoTradeAnalytics
from victor_ai_bot.execution_capture.realized_edge_metrics import realized_edge_metrics


def test_calibration_updates_and_priors(tmp_path):
    store = EmpiricalCalibrationStore(data_dir=str(tmp_path), chain='eth')
    store.observe(route_family='flash|u', lane='PRIVATE', projected_realized_edge_usd=10.0, actual_realized_edge_usd=8.0, predicted_success_probability=0.8, actual_success=True, predicted_slippage_usd=1.0, actual_slippage_usd=1.5, predicted_interference_probability=0.2, actual_stale=False)
    pri = store.priors(route_family='flash|u', lane='PRIVATE')
    assert pri['realization_ratio'] == 0.8


def test_no_trade_analytics(tmp_path):
    store = NoTradeAnalytics(str(tmp_path / 'nt.json'))
    store.observe(admitted=True, projected_edge_usd=5.0, actual_edge_usd=-2.0)
    store.observe(admitted=False, projected_edge_usd=3.0, actual_edge_usd=0.0)
    snap = store.snapshot()
    assert snap['false_admissions'] == 1
    assert snap['false_drops'] == 1


def test_realized_edge_metrics():
    m = realized_edge_metrics(projected_gross_edge_usd=10.0, projected_realized_edge_usd=8.0, actual_realized_edge_usd=6.0)
    assert m['realization_ratio'] == 0.75


def test_no_trade_analytics_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "nt.json"
    path.write_text("{bad json", encoding="utf-8")

    store = NoTradeAnalytics(str(path))

    assert store.snapshot() == {
        "false_admissions": 0,
        "false_drops": 0,
        "conservatism_cost_usd": 0.0,
        "bad_trade_avoidance_value_usd": 0.0,
    }


def test_no_trade_analytics_sanitizes_partially_malformed_state(tmp_path):
    path = tmp_path / "nt.json"
    path.write_text(
        __import__("json").dumps(
            {
                "false_admissions": "3",
                "false_drops": "bad",
                "conservatism_cost_usd": "4.5",
                "bad_trade_avoidance_value_usd": None,
                "ignored": {"nested": True},
            }
        ),
        encoding="utf-8",
    )

    store = NoTradeAnalytics(str(path))

    assert store.snapshot() == {
        "false_admissions": 3,
        "false_drops": 0,
        "conservatism_cost_usd": 4.5,
        "bad_trade_avoidance_value_usd": 0.0,
    }
