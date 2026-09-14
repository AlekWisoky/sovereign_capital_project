import math

from victor_ai_bot.agents.weighting import AgentWeightingGovernor
from victor_ai_bot.aqe.agents.base import AgentOutput
from victor_ai_bot.aqe.agents.hub import AgentHub
from victor_ai_bot.aqe.portfolio.manager import PortfolioManager


def _output(name: str, signal: float) -> AgentOutput:
    return AgentOutput(
        pi_team={},
        pi_self={},
        alpha=0.0,
        q_values={},
        confidence=1.0,
        info={"name": name},
        signal=signal,
        reasoning={},
    )


def test_dynamic_weight_changes_pm_aggregation():
    pm = PortfolioManager()
    outputs = [_output("Ben Graham Agent", 1.0), _output("Warren Buffett Agent", -1.0)]

    static = pm.aggregate(outputs)
    weighted = pm.aggregate(
        outputs,
        weight_override={"Ben Graham Agent": 1.75, "Warren Buffett Agent": 0.25},
    )

    assert weighted["weights_used"]["Ben Graham Agent"] == 1.75
    assert weighted["weights_used"]["Warren Buffett Agent"] == 0.25
    assert weighted["portfolio_signal"] > static["portfolio_signal"]


def test_regime_changes_select_distinct_governor_state(tmp_path):
    gov = AgentWeightingGovernor(path=str(tmp_path / "weights.json"))
    agent = "RiskAgent"

    high_before = gov.weights_for(regime="high_volatility", agents=[agent])[agent]
    low_before = gov.weights_for(regime="low_volatility", agents=[agent])[agent]

    gov.observe(
        agent=agent,
        regime="high_volatility",
        followed=True,
        predicted_signal=1.0,
        realized_edge_usd=100.0,
    )

    high_after = gov.weights_for(regime="high_volatility", agents=[agent])[agent]
    low_after = gov.weights_for(regime="low_volatility", agents=[agent])[agent]

    assert high_after > high_before
    assert low_after == low_before
    assert high_after != low_after


def test_malformed_dynamic_weights_fall_back_to_static():
    pm = PortfolioManager()
    outputs = [_output("Ben Graham Agent", 1.0)]
    static_weight = pm.cfg.weights["Ben Graham Agent"]

    result = pm.aggregate(
        outputs,
        weight_override={
            "Ben Graham Agent": float("nan"),
            "Warren Buffett Agent": 99.0,
        },
    )

    assert result["weights_used"]["Ben Graham Agent"] == static_weight
    assert math.isfinite(result["weights_used"]["Ben Graham Agent"])


def test_agent_hub_uses_explicit_regime_and_weight_projection_without_authority():
    hub = AgentHub()
    state = {
        "regime": "high_volatility",
        "agent_weights": {"Risk Manager": 1.75},
        "local": {"margin_ratio": 0.002, "gas_ratio": 0.0003, "p_success": 0.92, "legs": 2, "ev_wei": 1000},
        "dex": {"mid": 101.0, "opps_per_block": 5},
        "cex": {"mid": 100.0, "spread_bps": 8.0, "depth_usd": 2.0, "funding_bps": 3.0, "funding_change_bps": 1.0},
        "mev": {"sandwich_risk": 0.2, "router_flow": 0.3},
        "treasury": {"borrow_mult_target_cap": 1.5, "aggressiveness_level": "LOW", "urgency_factor": 0.0},
        "wallets": {"flow": 0.2, "whale": 0.1},
        "liq": {"intensity": 0.2},
        "sent": {"score": 0.1},
    }

    out = hub.step(state=state)
    pm = out.portfolio_manager

    assert pm["regime"] == "high_volatility"
    assert pm["weights_used"]["Risk Manager"] == 1.75
    assert "decision_id" not in pm
    assert "execution_id" not in pm
    assert "governance" not in pm
    assert "admission" not in pm
