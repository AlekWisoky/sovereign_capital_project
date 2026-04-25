from pathlib import Path

from victor_ai_bot.aqe.agents.adaptation import OnlineLinearCalibrator
from victor_ai_bot.aqe.agents.investment_agents import BenGrahamAgent
import victor_ai_bot.aqe.agents.adaptation as adaptation_module


def test_calibrator_load_failure_is_exposed_in_agent_runtime(tmp_path: Path) -> None:
    cal_path = tmp_path / "aqe" / "agents"
    cal_path.mkdir(parents=True, exist_ok=True)
    (cal_path / "ben_graham_agent.json").write_text("{not-json", encoding="utf-8")

    agent = BenGrahamAgent(data_dir=str(tmp_path))
    out = agent.act(state={"margin_ratio": 0.0015, "regime": "normal"})

    calibration = out.info["runtime"]["calibration"]
    assert calibration["load"]["code"] == "calibration_load_failed"
    assert calibration["degraded"] is True


def test_calibrator_save_failure_is_exposed_in_agent_runtime(tmp_path: Path, monkeypatch) -> None:
    agent = BenGrahamAgent(data_dir=str(tmp_path))
    agent.cal.last_save_ts = 0.0

    def _boom(_src: str, _dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(adaptation_module.os, "replace", _boom)

    agent.update(reward=0.6, features_used={"mr": 1.0})
    out = agent.act(state={"margin_ratio": 0.002, "regime": "normal"})

    calibration = out.info["runtime"]["calibration"]
    assert calibration["save"]["code"] == "calibration_save_failed"
    assert calibration["degraded"] is True


def test_calibrator_apply_partial_marks_invalid_feature_inputs(tmp_path: Path) -> None:
    cal = OnlineLinearCalibrator(name="Test Agent", data_dir=str(tmp_path), enabled=True)
    cal.w = {"mr": 1.0}

    score = cal.apply({"mr": 2.0, "bad": object()})

    assert score == 2.0
    state = cal.state()
    assert state["apply"]["code"] == "calibration_apply_partial"
    assert "bad" in state["apply"]["invalid"]
