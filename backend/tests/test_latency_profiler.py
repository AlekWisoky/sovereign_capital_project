from __future__ import annotations

import pytest

from victor_ai_bot.latency_profiler import RollingLatency


def test_rolling_latency_ignores_unparseable_values() -> None:
    rl = RollingLatency(window=20)
    rl.add("12.5")
    rl.add("bad")
    snap = rl.snapshot()
    assert snap["count"] == 1.0
    assert snap["last"] == 12.5


def test_rolling_latency_ignores_negative_values() -> None:
    rl = RollingLatency(window=20)
    rl.add(5.0)
    rl.add(-1.0)
    snap = rl.snapshot()
    assert snap["count"] == 1.0
    assert snap["last"] == 5.0


def test_rolling_latency_does_not_swallow_unexpected_float_runtime_error() -> None:
    class BadFloat:
        def __float__(self) -> float:
            raise RuntimeError("boom")

    rl = RollingLatency(window=20)
    with pytest.raises(RuntimeError):
        rl.add(BadFloat())
