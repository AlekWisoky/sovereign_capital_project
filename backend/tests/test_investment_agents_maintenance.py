from victor_ai_bot.aqe.agents.investment_agents import BenGrahamAgent, FeatureView


def test_feature_view_runtime_marks_invalid_sources() -> None:
    fv = FeatureView(
        {
            "S_global": {"features": {"local.margin_ratio": "bad"}, "embedding": [1, "oops", 3]},
            "Historical_Context": {"margin_ratio": "nope"},
            "C_t": {"margin_ratio": "still-nope"},
            "margin_ratio": "bad-again",
            "regime": "volatile",
        }
    )

    assert fv.f("local.margin_ratio", 0.125) == 0.125
    emb = fv.embedding()
    assert emb == [1.0, 3.0]
    state = fv.runtime_state()
    assert state["features"]["code"] == "features_invalid"
    assert state["embedding"]["code"] == "embedding_partial"
    assert state["degraded"] is True


def test_agent_act_exposes_runtime_when_calibration_apply_fails(tmp_path) -> None:
    agent = BenGrahamAgent(data_dir=str(tmp_path))

    def _boom(_features):
        raise ValueError("apply failed")

    agent.cal.apply = _boom  # type: ignore[assignment]

    out = agent.act(
        state={
            "S_global": {"features": {"local.margin_ratio": "bad"}},
            "regime": "stress",
        }
    )

    runtime = out.info["runtime"]
    assert runtime["calibration"]["code"] == "calibration_apply_failed"
    assert runtime["feature_view"]["degraded"] is True
    assert out.signal <= 1.0
    assert out.signal >= -1.0


def test_agent_update_invalid_reward_is_reported_on_next_act(tmp_path) -> None:
    agent = BenGrahamAgent(data_dir=str(tmp_path))
    agent.update(reward="oops", features_used={"mr": 0.2})  # type: ignore[arg-type]

    out = agent.act(state={"margin_ratio": 0.0015, "regime": "normal"})

    assert out.info["runtime"]["adaptation"]["code"] == "adaptation_reward_invalid"
