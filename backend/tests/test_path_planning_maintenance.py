from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot.superstructure.path_planning import StrategyPathPlanner
import victor_ai_bot.superstructure.path_planning as path_planning


@pytest.fixture()
def sample_opp() -> SimpleNamespace:
    return SimpleNamespace(
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(amount_in="100000"),
                SimpleNamespace(amount_in="100000"),
            ]
        ),
        meta={"profit_after_costs": "250"},
        expected_profit_raw="250",
    )


def test_path_planning_has_no_broad_exception_handlers():
    text = (Path(__file__).resolve().parents[1] / "victor_ai_bot" / "superstructure" / "path_planning.py").read_text(encoding="utf-8")
    assert "except Exception" not in text



def test_path_planning_marks_bus_publish_failure_explicitly(monkeypatch, tmp_path: Path, sample_opp: SimpleNamespace):
    planner = StrategyPathPlanner(data_dir=str(tmp_path), chain="eth")

    monkeypatch.setattr(path_planning.BUS, "snapshot", lambda: {"mev": {"data": {"sandwich_risk": 0.2}}, "S_global": {"data": {"vol_cluster": 0.1}}})

    def _boom(bucket: str, data: dict, *, ts=None):
        raise RuntimeError(f"bus offline:{bucket}:{sorted(data)}")

    monkeypatch.setattr(path_planning.BUS, "update", _boom)

    plan = planner.plan(opp=sample_opp)
    state = planner.last()["runtime"]

    assert plan.ok is True
    assert state["bus"]["ok"] is False
    assert state["bus"]["last_error_code"] == "path_plan_publish_failed"
    assert state["degraded"] is True



def test_path_planning_marks_storage_and_input_failures_explicitly(monkeypatch, tmp_path: Path):
    planner = StrategyPathPlanner(data_dir=str(tmp_path), chain="eth")

    monkeypatch.setattr(path_planning.BUS, "snapshot", lambda: {})

    def _open_fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(path_planning.os, "open", _open_fail)

    opp = SimpleNamespace(
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="bad")]),
        meta={"profit_after_costs": "bad"},
        expected_profit_raw="bad",
    )

    plan = planner.plan(opp=opp)
    state = planner.last()["runtime"]

    assert plan.ok is True
    assert state["inputs"]["ok"] is False
    assert state["inputs"]["last_error_code"] == "path_profit_after_costs_invalid"
    assert state["storage"]["ok"] is False
    assert state["storage"]["last_error_code"] == "path_plan_write_failed"
    assert state["degraded"] is True


def test_path_planning_does_not_fall_back_to_gross_profit_when_after_costs_missing(monkeypatch, tmp_path: Path):
    planner = StrategyPathPlanner(data_dir=str(tmp_path), chain="eth")
    monkeypatch.setattr(path_planning.BUS, "snapshot", lambda: {})

    opp = SimpleNamespace(
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={},
        expected_profit_raw="9000",
    )

    plan = planner.plan(opp=opp)
    state = planner.last()["runtime"]

    assert plan.ok is True
    assert state["inputs"]["ok"] is False
    assert state["inputs"]["last_error_code"] == "path_profit_after_costs_missing"
    assert float(plan.score) <= 0.0


def test_path_planning_marks_mismatched_after_costs_explicitly(monkeypatch, tmp_path: Path):
    planner = StrategyPathPlanner(data_dir=str(tmp_path), chain="eth")
    monkeypatch.setattr(path_planning.BUS, "snapshot", lambda: {})

    opp = SimpleNamespace(
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={
            "profit_after_costs": "9000",
            "safety": {"profit_after_costs_wei": "250"},
        },
        expected_profit_raw="9000",
    )

    plan = planner.plan(opp=opp)
    state = planner.last()["runtime"]

    assert plan.ok is True
    assert state["inputs"]["ok"] is False
    assert state["inputs"]["last_error_code"] == "path_profit_after_costs_mismatch"
    assert float(plan.score) <= 0.0
