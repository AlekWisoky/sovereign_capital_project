import pytest

from victor_ai_bot.aqe.spread.engine import SpreadEngine, SpreadEngineConfig, SpotSpotCrossExchangeArbitrageEngine


def test_spread_engine_skips_expected_local_scan_failures(monkeypatch):
    engine = SpreadEngine(cfg=SpreadEngineConfig(enabled=True, min_alpha=0.0, fee_bps=0.0, gas_usd=0.0, vol_risk_usd=0.0))

    class BadEngine:
        def scan(self, *, state):
            raise ValueError("bad local state")

    engine.engines = [BadEngine(), SpotSpotCrossExchangeArbitrageEngine()]
    out = engine.scan(
        state={
            "quotes": [
                {"symbol": "ETH", "venue": "a", "bid": 101.0, "ask": 102.0},
                {"symbol": "ETH", "venue": "b", "bid": 103.0, "ask": 100.0},
            ]
        }
    )
    assert len(out) == 1
    assert out[0].opp_id.startswith("spotspot:ETH:")


def test_spread_engine_does_not_swallow_unexpected_runtime_bug():
    engine = SpreadEngine(cfg=SpreadEngineConfig(enabled=True))

    class ExplodingEngine:
        def scan(self, *, state):
            raise RuntimeError("unexpected scan bug")

    engine.engines = [ExplodingEngine()]
    with pytest.raises(RuntimeError, match="unexpected scan bug"):
        engine.scan(state={"quotes": []})
