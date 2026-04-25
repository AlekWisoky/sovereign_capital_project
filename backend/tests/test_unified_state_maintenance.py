from __future__ import annotations

from victor_ai_bot.aqe.coordination import feature_bus as feature_bus_module
from victor_ai_bot.aqe.coordination.feature_bus import SharedFeatureBus
from victor_ai_bot.aqe.unified.state import UnifiedMarketState


def test_unified_market_state_reports_ingest_degradation_without_crashing():
    state = UnifiedMarketState()

    state.ingest_bus_snapshot(
        {
            "chain": "ethereum",
            "block": "bad-block",
            "gas": {"data": {"basefee_gwei": "bad-gas"}},
            "mev": {"data": {"pending_rate": "bad-rate"}},
            "opaque": object(),
        }
    )

    snap = state.snapshot()
    assert snap["chain"] == ""
    assert snap["block"] == 0
    assert snap["status"]["block"] == "block_invalid"
    assert snap["status"]["gas"] == "gas_invalid"
    assert snap["status"]["mempool"] == "mempool_invalid"
    assert snap["status"]["degraded"] is True
    assert isinstance(snap["meta"]["bus"], dict)
    assert snap["meta"]["bus"]["opaque"] == {}


def test_shared_feature_bus_surfaces_bus_snapshot_failures(monkeypatch):
    bus = SharedFeatureBus()

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(feature_bus_module.BUS, "snapshot", _boom)

    last = bus.update_from_bus()
    snap = bus.snapshot()

    assert last["status"]["busRead"] == "bus_snapshot_failed"
    assert snap["status"]["degraded"] is True
    assert snap["market"]["status"]["input"] == "ok"
