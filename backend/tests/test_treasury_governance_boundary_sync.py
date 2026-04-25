from __future__ import annotations

import time
from types import SimpleNamespace

from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.runtime_agent_consensus_facade import (
    RuntimeAgentConsensusFacade,
)
from victor_ai_bot.runtime_services.runtime_market_facade import RuntimeMarketFacade
from victor_ai_bot.runtime_services.runtime_spread_facade import RuntimeSpreadFacade
from victor_ai_bot.runtime_services.runtime_treasury_overlay_facade import (
    RuntimeTreasuryOverlayFacade,
)
from victor_ai_bot.treasury.config import ProfitGoal, TreasuryConfig
from victor_ai_bot.treasury.runtime import TreasuryRuntime


class _DecisionRuntime(RuntimeTreasuryOverlayFacade):
    pass


class _SpreadRuntime(RuntimeSpreadFacade):
    def __init__(self):
        self._arbitrage = SimpleNamespace(state=lambda: {"quotes": []})
        self._spread_engine = None
        self._spread_opps = []
        self._spread_last = {}


class _Behave:
    def __init__(self):
        self.overlay_calls = []

    def select_strategy_overlay(self, *, opps, profit_goal, aggressiveness, seed):
        self.overlay_calls.append(
            {
                "opps": list(opps),
                "profit_goal": dict(profit_goal),
                "aggressiveness": aggressiveness,
                "seed": seed,
            }
        )
        return {"ok": True}


class _MarketRuntime(RuntimeMarketFacade):
    def __init__(self):
        self._behave = _Behave()


class _Hub:
    def __init__(self):
        self.calls = []

    def step(self, *, state):
        self.calls.append(state)
        return SimpleNamespace(
            signals={},
            confidences={},
            outputs={},
            contracts={},
            health={},
            mandates={},
            portfolio_manager={},
        )


class _Consensus:
    def __init__(self):
        self.calls = []

    def compute(self, *, signals, confidences, regime, strategy_type, deterministic_key):
        self.calls.append(
            {
                "signals": dict(signals),
                "confidences": dict(confidences),
                "regime": regime,
                "strategy_type": strategy_type,
                "deterministic_key": deterministic_key,
            }
        )
        return {"allow": True, "key": deterministic_key}


class _AgentRuntime(RuntimeAgentConsensusFacade):
    def __init__(self):
        self._agent_hub = _Hub()
        self._consensus = _Consensus()
        self._agent_weighting = None
        self._agent_hub_last = {}
        self._consensus_last = {}


class _TreasuryStub:
    def __init__(self):
        self.cfg = SimpleNamespace(
            enabled=True, allow_maximum=True, max_aggressiveness_without_approval="MODERATE"
        )
        self._state = {
            "aggressiveness": {
                "aggressiveness_level": "MAXIMUM",
                "aggressiveness_multiplier": 1.4,
                "current_return_pct": 0.0,
                "performance_gap": 5.0,
                "urgency_factor": 1.0,
                "drawdown_pct": 0.0,
            },
            "goal": {"target_return_percentage": 5.0, "max_drawdown_pct": 10.0},
            "borrow_mult_target_cap": 3.0,
            "governance": {
                "ok": False,
                "blocked": True,
                "reason": "maximum_requires_approval",
                "reason_codes": ["maximum_requires_approval"],
                "approved_by_human": False,
                "allow_maximum": True,
                "max_aggressiveness_without_approval": "MODERATE",
                "raw_aggressiveness_level": "MAXIMUM",
                "effective_aggressiveness_level": "MODERATE",
                "raw_borrow_mult_target_cap": 3.0,
                "effective_borrow_mult_target_cap": 1.0,
                "urgency_factor": 1.0,
                "suggested_next_action": "obtain_treasury_approval_or_reduce_aggressiveness",
            },
        }

    def snapshot(self):
        return dict(self._state)


class _RuntimeWithTreasury:
    def __init__(self):
        self._treasury = _TreasuryStub()


def test_treasury_runtime_preselect_strategy_embeds_governance_boundary(tmp_path):
    rt = TreasuryRuntime(
        cfg=TreasuryConfig(
            enabled=True,
            allow_maximum=True,
            max_aggressiveness_without_approval="MODERATE",
            goal=ProfitGoal(
                target_return_percentage=50.0,
                time_horizon_seconds=1,
                risk_tolerance="aggressive",
                max_drawdown_pct=10.0,
            ),
        ),
        data_dir=str(tmp_path),
    )
    rt._started_ts = int(time.time())

    out = rt.pre_select_strategy(
        bankroll_state={"realized_profit_wei": 0, "last_amount_in_wei": 100},
        volatility_regime="balanced",
        persist=False,
    )

    assert out["governance"]["blocked"] is True
    assert out["governance"]["reason"] in {
        "aggressiveness_requires_approval",
        "maximum_requires_approval",
    }
    assert out["effective_borrow_mult_target_cap"] == 1.0
    assert out["effective_aggressiveness_level"] == "MODERATE"


def test_runtime_treasury_overlay_uses_governed_cap_and_level():
    runtime = _DecisionRuntime()
    decision = SimpleNamespace(action="trade", borrow_mult=1.0, p_success=0.95)

    runtime._apply_treasury_borrow_overlay(
        decision=decision,
        treasury_state=_TreasuryStub().snapshot(),
        regime_label="risk_on",
    )

    assert decision.borrow_mult == 1.0


def test_runtime_spread_facade_uses_effective_aggressiveness_level():
    runtime = _SpreadRuntime()
    state = runtime._spread_scan_state(
        regime_label="risk_on",
        mev_risk=0.1,
        pending_rate=0.2,
        treasury_state=_TreasuryStub().snapshot(),
    )
    assert state["aggressiveness_level"] == "MODERATE"


def test_runtime_market_facade_uses_effective_aggressiveness_level():
    runtime = _MarketRuntime()
    runtime._behave_strategy_overlay(
        behave_state={"enabled": True},
        treasury_state=_TreasuryStub().snapshot(),
        opps=[SimpleNamespace(route_id="a")],
        current_block=7,
    )
    assert runtime._behave.overlay_calls[0]["aggressiveness"] == "MODERATE"


def test_runtime_agent_consensus_uses_governed_treasury_fields():
    runtime = _AgentRuntime()
    runtime._run_agent_consensus_gate(
        opps=[
            SimpleNamespace(can_execute=True, id="opp-1", meta={}, route=SimpleNamespace(legs=[]))
        ],
        bus_snap={},
        mev_snap={},
        treasury_state=_TreasuryStub().snapshot(),
        regime_label="risk_on",
        current_block=11,
    )
    treasury = runtime._agent_hub.calls[0]["treasury"]
    assert treasury["borrow_mult_target_cap"] == 1.0
    assert treasury["aggressiveness_level"] == "MODERATE"
    assert treasury["governance_blocked"] is True


def test_execution_service_auto_trade_treasury_gate_uses_governance_contract_metadata():
    gate = ExecutionService().auto_trade_treasury_gate(_RuntimeWithTreasury())

    assert gate.allowed is False
    assert gate.reason == "maximum_requires_approval"
    assert gate.metadata["effective_aggressiveness_level"] == "MODERATE"
    assert gate.metadata["effective_borrow_mult_target_cap"] == 1.0
    assert gate.metadata["governance"]["blocked"] is True


from victor_ai_bot.analytics.quicksight.dashboards import build_executive_overview_with_status
from victor_ai_bot.analytics.quicksight.datasets import build_treasury_metrics_row_with_status
from victor_ai_bot.execution_capture.flashloan_sizing import choose_flashloan_size
from victor_ai_bot.execution_capture.models import OpportunityEnvelope, SafeSizePoint
import victor_ai_bot.treasury.runtime as treasury_runtime_mod


def test_treasury_runtime_preselect_strategy_uses_effective_governed_posture_for_advisory_components(
    tmp_path, monkeypatch
):
    calls = {"inventory": [], "allocate": [], "reinvest": []}

    def _fake_allocate_capital(**kwargs):
        calls["allocate"].append(kwargs["aggressiveness_level"])
        return {"deployable_bankroll_wei": 1, "drawdown_buffer_wei": 1}

    def _fake_reinvestment_policy(**kwargs):
        calls["reinvest"].append(kwargs["aggressiveness_level"])
        return {"mode": "ok"}

    monkeypatch.setattr(treasury_runtime_mod, "allocate_capital", _fake_allocate_capital)
    monkeypatch.setattr(treasury_runtime_mod, "reinvestment_policy", _fake_reinvestment_policy)

    rt = TreasuryRuntime(
        cfg=TreasuryConfig(
            enabled=True,
            allow_maximum=True,
            max_aggressiveness_without_approval="MODERATE",
            goal=ProfitGoal(
                target_return_percentage=50.0,
                time_horizon_seconds=1,
                risk_tolerance="aggressive",
                max_drawdown_pct=10.0,
            ),
        ),
        data_dir=str(tmp_path),
    )
    rt._started_ts = int(time.time())

    def _fake_inventory(*, volatility_regime, aggressiveness_level, liquidity_buffer):
        calls["inventory"].append(aggressiveness_level)
        return {"targets": {"stable_reserves": 0.25}}

    rt._inv_balancer.compute_targets = _fake_inventory  # type: ignore[assignment]

    out = rt.pre_select_strategy(
        bankroll_state={"realized_profit_wei": 0, "last_amount_in_wei": 100},
        volatility_regime="balanced",
        persist=False,
    )

    assert out["effective_aggressiveness_level"] == "MODERATE"
    assert out["governance"]["blocked"] is True
    assert out["aggressiveness"]["aggressiveness_level"] == "MODERATE"
    assert out["aggressiveness"]["borrow_mult_target_cap"] == 1.0
    assert calls["inventory"] == ["MODERATE"]
    assert calls["allocate"] == ["MODERATE", "MODERATE"]
    assert calls["reinvest"] == ["MODERATE"]


def test_flashloan_sizing_uses_effective_treasury_borrow_cap():
    envelope = OpportunityEnvelope(
        opportunity_id="opp-1",
        route_id="route-1",
        route_family="flashloan_atomic",
        expected_profit_usd=100.0,
        gas_estimate_usd=5.0,
        slippage_sensitivity=0.1,
        liquidity_fragility=0.1,
        latency_half_life_ms=100,
        mempool_copy_risk=0.05,
        venue_reliability_score=1.0,
        simulation_confidence=1.0,
        safe_size_curve=[
            SafeSizePoint(1.0, 100.0, 5.0, 1.0, 1.0),
            SafeSizePoint(2.0, 180.0, 8.0, 2.0, 2.0),
        ],
        failure_cost_estimate=10.0,
        freshness_score=1.0,
        private_send_preference=False,
        chain_id=1,
        metadata={"strategy_family": "flashloan_atomic"},
    )

    result = choose_flashloan_size(
        envelope=envelope,
        requested_size_mult=2.0,
        route_plan={"score": 1.0},
        flashloan_resilience={
            "selected_provider": "aave",
            "provider_priority": ["aave"],
            "provider_scores": [{"provider": "aave", "score": 1.0}],
            "route_viable": True,
        },
        adversarial_state={},
        treasury_state=_TreasuryStub().snapshot(),
    )

    assert result["borrow_mult"] == 1.0
    assert result["size_mult"] == 1.0
    assert result["hard_cap"] == 1.0


def test_quicksight_treasury_views_use_effective_governed_posture():
    treasury_state = _TreasuryStub().snapshot()

    row, _ = build_treasury_metrics_row_with_status(ts=7, treasury_state=treasury_state)
    dashboard, _ = build_executive_overview_with_status(
        ts=7,
        pnl={"realized_pnl_wei": 1, "net_pnl_wei": 1, "win_rate": 1.0, "trades": 1},
        treasury=treasury_state,
        income={},
    )

    assert row["aggressiveness_level"] == "MODERATE"
    assert row["borrow_cap_mult"] == 1.0
    assert dashboard["aggressiveness"]["level"] == "MODERATE"
    assert dashboard["aggressiveness"]["borrow_cap_mult"] == 1.0
