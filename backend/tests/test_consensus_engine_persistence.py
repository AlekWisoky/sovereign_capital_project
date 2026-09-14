from __future__ import annotations

import json

import pytest

from victor_ai_bot.aqe.coordination.consensus_engine import (
    AgentConsensusEngine,
    AgentPerformanceTracker,
    ConsensusConfig,
)


def test_agent_performance_tracker_recovers_from_corrupt_json(tmp_path):
    path = tmp_path / "tracker.json"
    path.write_text("{bad json", encoding="utf-8")

    tracker = AgentPerformanceTracker(path=str(path))

    assert tracker.snapshot()["agents"] == {}


def test_agent_performance_tracker_sanitizes_partial_state(tmp_path):
    path = tmp_path / "tracker.json"
    path.write_text(
        json.dumps(
            {
                "agents": {
                    "alpha": {
                        "weight": "1.7",
                        "n": "4",
                        "wins": "9",
                        "mean_reward": "2.5",
                        "var_reward": "-4",
                    },
                    " ": {"weight": 2.0},
                    "beta": "bad",
                }
            }
        ),
        encoding="utf-8",
    )

    tracker = AgentPerformanceTracker(path=str(path))
    snap = tracker.snapshot()["agents"]

    assert set(snap.keys()) == {"alpha"}
    assert snap["alpha"]["agent"] == "alpha"
    assert snap["alpha"]["weight"] == 1.7
    assert snap["alpha"]["n"] == 4
    assert snap["alpha"]["wins"] == 4
    assert snap["alpha"]["mean_reward"] == 2.5
    assert snap["alpha"]["var_reward"] == 0.0


def test_agent_performance_tracker_save_does_not_swallow_unexpected_bug(tmp_path, monkeypatch):
    path = tmp_path / "tracker.json"
    tracker = AgentPerformanceTracker(path=str(path))
    tracker.observe(agent="alpha", ok=True, reward=1.0)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("victor_ai_bot.aqe.coordination.consensus_engine.json.dump", boom)

    with pytest.raises(RuntimeError, match="boom"):
        tracker.save()


def test_consensus_engine_uses_explicit_weight_overrides_without_persisting_them():
    engine = AgentConsensusEngine(cfg=ConsensusConfig(enabled=True), tracker=None)
    result = engine.compute(
        signals={"alpha": 1.0, "beta": -1.0},
        confidences={"alpha": 1.0, "beta": 1.0},
        regime="balanced",
        strategy_type="dex_flash",
        deterministic_key="block:opp",
        weight_overrides={"alpha": 0.25, "beta": 1.75},
    )
    assert result["weights"]["alpha"] == 0.25
    assert result["weights"]["beta"] == 1.75
    assert result["deterministic_key"] == "block:opp"
    assert engine.tracker is None


def test_consensus_engine_malformed_weight_overrides_fall_back_per_agent():
    engine = AgentConsensusEngine(cfg=ConsensusConfig(enabled=True), tracker=None)
    result = engine.compute(
        signals={"alpha": 1.0, "beta": -1.0},
        confidences={"alpha": 1.0, "beta": 1.0},
        regime="balanced",
        strategy_type="dex_flash",
        weight_overrides={"alpha": float("nan"), "beta": 0.5},
    )
    assert result["weights"]["alpha"] == 1.0
    assert result["weights"]["beta"] == 0.5
