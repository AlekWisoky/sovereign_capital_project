from victor_ai_bot.rft.graders.composite import score_proposal
from victor_ai_bot.rft.schema import (
    BreakerState,
    EpisodeContext,
    LastOutcome,
    LatencyProfile,
    RiskCaps,
    TopOpportunity,
)


def _ctx() -> EpisodeContext:
    return EpisodeContext(
        episode_id="episode-1",
        replay_event_id="replay-1",
        decision_id="decision-1",
        chain="ethereum",
        chain_id=1,
        block_number=123,
        opportunity_id="opp-1",
        route_id="route-1",
        v1_focus="flashloan_atomic",
        regime_state="normal",
        risk_state="normal",
        risk_caps=RiskCaps(
            max_daily_loss_pct_bps=300,
            max_exposure_pct_bps=8000,
            sandbox_cap_pct_bps=1000,
            probation_cap_pct_bps=250,
        ),
        breakers=BreakerState(drawdown_breaker=False, gas_anomaly_breaker=False, drift_breaker=False, rpc_degraded=False),
        latency=LatencyProfile(loop_ms_p90=400, loop_ms_p99=900, exec_ms_p90=500, exec_ms_p99=950),
        last_outcomes=[LastOutcome(event_id="old-1", ok=True, reward_scaled_ppm=2500, realized_after_gas_usd_micro=5_000_000)],
        top_opportunities=[
            TopOpportunity(
                opportunity_id="opp-1",
                route_id="route-1",
                strategy_id="flashloan_atomic",
                expected_profit_after_costs_wei="1000000000000000000",
                expected_profit_after_gas_usd_micro=8_000_000,
                expected_profit_usd_micro=9_000_000,
                competition="medium",
                venue_tags=["univ3", "curve"],
                why=["top spread", "gas-adjusted"],
            )
        ],
        controls={"sandbox_only": False, "paused": False},
        wealth_goal={"target_return_pct": 8.0},
        reward_trace={"reward_scaled_ppm": 2500},
        execution_summary={"send_mode": "protected_rpc", "slippage_bps": 50, "deadline_seconds": 30},
    )


def _proposal(send_mode: str = "protected_rpc", sandbox_only: bool = False) -> dict:
    return {
        "proposal_schema_version": "1",
        "backend_builder_version": "test-builder",
        "opportunity_id": "opp-1",
        "strategy_id": "flashloan_atomic",
        "notional_usd_micro": 250_000_000,
        "send_mode": send_mode,
        "why": ["net positive", "route ranked first"],
        "constraints": {"max_slippage_bps": 50, "deadline_seconds": 30},
        "mode": {"sandbox_only": sandbox_only, "defensive": False, "probation": False},
    }


def test_composite_score_positive_for_valid_conservative_proposal():
    res = score_proposal(_ctx(), _proposal())
    assert res.proposal_valid is True
    assert res.total_reward_ppm > 0
    names = {c.name: c for c in res.components}
    assert names["schema"].passed is True
    assert names["policy"].passed is True
    assert names["capital"].passed is True
    assert names["profit"].passed is True


def test_policy_grader_rejects_public_send_in_sandbox():
    ctx = _ctx().model_copy(update={"controls": {"sandbox_only": True, "paused": False}})
    res = score_proposal(ctx, _proposal(send_mode="public", sandbox_only=True))
    names = {c.name: c for c in res.components}
    assert names["policy"].passed is False
    assert names["policy"].reason == "sandbox_requires_non_public_send"


def test_schema_invalid_fails_fast():
    bad = _proposal()
    bad["extra"] = "nope"
    res = score_proposal(_ctx(), bad)
    assert res.proposal_valid is False
    assert res.total_reward_ppm == -500
    assert len(res.components) == 1
    assert res.components[0].name == "schema"


def test_profit_grader_fails_closed_when_after_costs_non_positive_despite_after_gas_positive():
    ctx = _ctx().model_copy(update={
        "top_opportunities": [
            TopOpportunity(
                opportunity_id="opp-1",
                route_id="route-1",
                strategy_id="flashloan_atomic",
                expected_profit_after_costs_wei="0",
                expected_profit_after_gas_usd_micro=8_000_000,
                expected_profit_usd_micro=9_000_000,
                competition="medium",
                venue_tags=["univ3"],
                why=["gross only"],
            )
        ]
    })
    res = score_proposal(ctx, _proposal())
    names = {c.name: c for c in res.components}
    assert names["profit"].passed is False
    assert names["profit"].reason == "negative_or_missing_net_after_costs"


def test_capital_grader_fails_closed_when_after_costs_non_positive_despite_after_gas_positive():
    ctx = _ctx().model_copy(update={
        "top_opportunities": [
            TopOpportunity(
                opportunity_id="opp-1",
                route_id="route-1",
                strategy_id="flashloan_atomic",
                expected_profit_after_costs_wei="-1",
                expected_profit_after_gas_usd_micro=8_000_000,
                expected_profit_usd_micro=9_000_000,
                competition="medium",
                venue_tags=["univ3"],
                why=["gross only"],
            )
        ]
    })
    res = score_proposal(ctx, _proposal())
    names = {c.name: c for c in res.components}
    assert names["capital"].passed is False
    assert names["capital"].reason == "capital_deny_non_positive_after_costs"
