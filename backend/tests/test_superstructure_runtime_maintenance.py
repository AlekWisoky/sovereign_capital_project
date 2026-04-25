from pathlib import Path
from types import SimpleNamespace

import pytest

from victor_ai_bot.superstructure.runtime import SuperstructureRuntime
import victor_ai_bot.superstructure.runtime as super_runtime


class _FailingPlanner:
    def plan(self, **_: object):
        raise ValueError("planner unavailable")

    def last(self):
        raise RuntimeError("planner snapshot unavailable")


@pytest.fixture()
def sample_opp() -> SimpleNamespace:
    return SimpleNamespace(
        id="opp-1",
        route=SimpleNamespace(
            legs=[
                SimpleNamespace(amount_in="100000", to="0xabc"),
                SimpleNamespace(amount_in="100000", to="0xdef"),
            ]
        ),
        meta={
            "profit_after_costs": "250",
            "brain": {"p_success": 0.82, "gas_ratio": 0.0008},
            "route_id": "route-1",
        },
        expected_profit_raw="250",
        route_id="route-1",
    )


def test_superstructure_runtime_has_no_broad_exception_handlers():
    text = (Path(__file__).resolve().parents[1] / "victor_ai_bot" / "superstructure" / "runtime.py").read_text(encoding="utf-8")
    assert "except Exception" not in text


def test_build_trade_proposal_marks_bus_degradation(monkeypatch, tmp_path, sample_opp):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))

    def _boom():
        raise RuntimeError("bus offline")

    monkeypatch.setattr(super_runtime.BUS, "snapshot", _boom)

    proposal = runtime.build_trade_proposal(opp=sample_opp)
    state = runtime.state()

    assert proposal.proposal_id.startswith("trade:")
    assert state["runtime"]["bus"]["ok"] is False
    assert state["runtime"]["bus"]["last_error_code"] == "bus_snapshot_failed"
    assert state["runtime"]["degraded"] is True


def test_pre_execute_trade_marks_path_planning_failure(tmp_path, sample_opp):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    runtime.cfg.enabled = True
    runtime.cfg.require_negotiation = False
    runtime.cfg.require_path_planning = True
    runtime.path_planner = _FailingPlanner()

    result = runtime.pre_execute_trade(opp=sample_opp, mode="auto")
    rt_state = runtime._runtime_state()

    assert result["ok"] is True
    assert result["allow"] is True
    assert result["overrides"] == {}
    assert rt_state["path_planning"]["ok"] is False
    assert rt_state["path_planning"]["last_error_code"] == "path_plan_failed"
    assert rt_state["degraded"] is True


def test_build_trade_proposal_does_not_fall_back_to_gross_profit_when_after_costs_missing(tmp_path):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    opp = SimpleNamespace(
        id="opp-gross-only",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={"brain": {"p_success": 0.8}},
        expected_profit_raw="5000",
        route_id="route-gross",
    )

    proposal = runtime.build_trade_proposal(opp=opp)

    assert proposal.expected_return == 0.0
    assert proposal.meta["profit_after_costs_verified"] is False
    assert proposal.meta["profit_after_costs_reason"] == "profit_after_costs_unavailable"


def test_pre_execute_trade_blocks_when_after_costs_are_unavailable_or_nonpositive(tmp_path):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    runtime.cfg.enabled = True
    runtime.cfg.require_negotiation = False
    runtime.cfg.require_path_planning = False

    missing_after_costs = SimpleNamespace(
        id="opp-gross-only",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={"brain": {"p_success": 0.8}},
        expected_profit_raw="5000",
        route_id="route-gross",
    )
    nonpositive_after_costs = SimpleNamespace(
        id="opp-net-zero",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={"profit_after_costs": "0", "brain": {"p_success": 0.8}},
        expected_profit_raw="5000",
        route_id="route-net-zero",
    )

    missing_result = runtime.pre_execute_trade(opp=missing_after_costs, mode="auto")
    nonpositive_result = runtime.pre_execute_trade(opp=nonpositive_after_costs, mode="auto")

    assert missing_result["ok"] is True
    assert missing_result["allow"] is False
    assert missing_result["reason"] == "profit_after_costs_unavailable"
    assert missing_result["overrides"] == {}

    assert nonpositive_result["ok"] is True
    assert nonpositive_result["allow"] is False
    assert nonpositive_result["reason"] == "profit_after_costs_not_positive"
    assert nonpositive_result["overrides"] == {}


def test_build_trade_proposal_marks_mismatched_after_costs_unverified(tmp_path):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    opp = SimpleNamespace(
        id="opp-mismatch",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={
            "profit_after_costs": "9000",
            "safety": {"profit_after_costs_wei": "250"},
            "brain": {"p_success": 0.8},
        },
        expected_profit_raw="9000",
        route_id="route-mismatch",
    )

    proposal = runtime.build_trade_proposal(opp=opp)
    state = runtime.state()

    assert proposal.expected_return == 0.0
    assert proposal.meta["profit_after_costs_verified"] is False
    assert proposal.meta["profit_after_costs_reason"] == "profit_after_costs_mismatch"
    assert state["runtime"]["proposal"]["ok"] is False
    assert state["runtime"]["proposal"]["last_error_code"] == "proposal_profit_after_costs_mismatch"
    assert state["runtime"]["degraded"] is True


def test_pre_execute_trade_blocks_when_after_costs_mismatch(tmp_path):
    runtime = SuperstructureRuntime(cfg={"enabled": False}, chain="eth", data_dir=str(tmp_path))
    runtime.cfg.enabled = True
    runtime.cfg.require_negotiation = False
    runtime.cfg.require_path_planning = False

    mismatched_after_costs = SimpleNamespace(
        id="opp-mismatch",
        route=SimpleNamespace(legs=[SimpleNamespace(amount_in="100000")]),
        meta={
            "profit_after_costs": "9000",
            "safety": {"profit_after_costs_wei": "250"},
            "brain": {"p_success": 0.8},
        },
        expected_profit_raw="9000",
        route_id="route-mismatch",
    )

    result = runtime.pre_execute_trade(opp=mismatched_after_costs, mode="auto")

    assert result["ok"] is True
    assert result["allow"] is False
    assert result["reason"] == "profit_after_costs_mismatch"
    assert result["overrides"] == {}
