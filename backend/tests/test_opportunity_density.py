from victor_ai_bot.opportunity_density import attach_scan_efficiency, scan_efficiency_snapshot


def test_scan_efficiency_snapshot_is_deterministic_and_bounded():
    out = scan_efficiency_snapshot(
        elapsed_ms=500,
        candidate_count=20,
        quote_requests=10,
        quote_successes=8,
        opportunity_count=2,
        cache_hits=4,
        network_batches=2,
    )
    assert out["quote_success_rate"] == 0.8
    assert out["opportunity_density_per_sec"] == 4.0
    assert out["opportunity_rate_per_quote"] == 0.2
    assert out["quotes_per_network_batch"] == 3.0


def test_scan_efficiency_snapshot_handles_zero_work():
    out = scan_efficiency_snapshot(
        elapsed_ms=0,
        candidate_count=0,
        quote_requests=0,
        quote_successes=3,
        opportunity_count=0,
    )
    assert out["quote_successes"] == 0
    assert out["quote_success_rate"] == 0.0
    assert out["opportunity_density_per_sec"] == 0.0


def test_scan_efficiency_can_be_attached_without_changing_route_authority():
    meta = {"route_family": "univ3_fee_tier_arb", "profit_after_gas_estimate_wei": "1"}
    snapshot = scan_efficiency_snapshot(
        elapsed_ms=1000,
        candidate_count=5,
        quote_requests=5,
        quote_successes=5,
        opportunity_count=1,
    )
    out = attach_scan_efficiency(meta, snapshot)
    assert out["route_family"] == "univ3_fee_tier_arb"
    assert out["profit_after_gas_estimate_wei"] == "1"
    assert out["scan_efficiency"]["opportunity_count"] == 1
