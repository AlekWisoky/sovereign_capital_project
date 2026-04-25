
from victor_ai_bot.efficiency import EfficiencyTracker, EfficiencyPoint

def test_efficiency_basic():
    t = EfficiencyTracker(window=10)
    t.add(EfficiencyPoint(ts=1, expected_after_costs_wei=100, realized_after_gas_wei=100, success=True, latency_ms=500))
    s = t.snapshot()
    assert s["n"] == 1
    assert s["raw_efficiency_pct"] == 100.0
    assert s["success_rate_pct"] == 100.0

def test_efficiency_penalty():
    t = EfficiencyTracker(window=10)
    t.add(EfficiencyPoint(ts=1, expected_after_costs_wei=100, realized_after_gas_wei=100, success=True, latency_ms=3000))
    s = t.snapshot()
    assert s["efficiency_pct"] <= 100.0
