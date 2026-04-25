from victor_ai_bot.aqe.agents.base import AgentOutput
from victor_ai_bot.aqe.agents.hub import AgentHub


class _MalformedAgent:
    name = "Valuation Agent"

    def act(self, *, state):
        return AgentOutput(
            pi_team={},
            pi_self={},
            alpha=0.0,
            q_values={},
            confidence="bad-confidence",
            info="not-a-mapping",
            signal="bad-signal",
            reasoning=[("why", "bad")],
        )


class _FailingAgent:
    name = "Risk Manager"

    def act(self, *, state):
        raise ValueError("agent boom")


class _FailingPortfolioManager:
    def aggregate(self, agent_outs):
        raise RuntimeError("portfolio boom")


def test_agent_hub_emits_runtime_for_malformed_agent_outputs(tmp_path):
    hub = AgentHub(data_dir=str(tmp_path))
    hub.agents = [_MalformedAgent()]

    out = hub.step(state={"local": {}})
    agent = out.outputs["Valuation Agent"]

    assert agent["signal"] == 0.0
    assert agent["confidence"] == 0.0
    assert agent["runtime"]["degraded"] is True
    assert agent["runtime"]["signal"]["code"] == "signal_invalid"
    assert agent["runtime"]["confidence"]["code"] == "confidence_invalid"
    assert agent["runtime"]["info"]["code"] in {"info_coerced", "info_invalid"}
    assert agent["runtime"]["reasoning"]["code"] in {"reasoning_coerced", "reasoning_invalid"}
    assert agent["info"]["runtime"]["degraded"] is True
    assert out.runtime["agents"]["code"] == "agent_output_degraded"


def test_agent_hub_emits_runtime_for_agent_and_portfolio_failures(tmp_path):
    hub = AgentHub(data_dir=str(tmp_path))
    hub.agents = [_FailingAgent()]
    hub.portfolio_manager = _FailingPortfolioManager()

    out = hub.step(state={"local": {}})
    agent = out.outputs["Risk Manager"]

    assert agent["runtime"]["degraded"] is True
    assert agent["runtime"]["act"]["code"] == "act_failed"
    assert out.runtime["agents"]["code"] == "agent_failed"

    assert out.portfolio_manager is not None
    assert out.portfolio_manager["runtime"]["degraded"] is True
    assert out.portfolio_manager["runtime"]["aggregate"]["code"] == "portfolio_aggregate_failed"
    assert out.runtime["portfolio_manager"]["code"] == "portfolio_manager_failed"
