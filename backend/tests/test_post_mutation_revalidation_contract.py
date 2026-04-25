from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import try_execute_opportunity
from victor_ai_bot.profitability_projection import profitability_summary_projection
from victor_ai_bot.runtime_services.capital_admission_service import CapitalAdmissionService
from victor_ai_bot.runtime_services.execution_service import ExecutionService


class _Leg:
    def __init__(self, *, amount_in: str = "100", min_out: str = "120"):
        self.amount_in = amount_in
        self.min_out = min_out
        self.dex = "uni"
        self.venue = "uni"
        self.token_in = "USDC"
        self.token_out = "WETH"
        self.data = "0x"


class _Route:
    def __init__(self):
        self.legs = [_Leg(), _Leg(amount_in="120", min_out="120")]


class _Opp:
    def __init__(self):
        self.id = "opp-1"
        self.route_id = "route-1"
        self.route = _Route()
        self.expected_profit_raw = "20"
        self.expected_profit_usd = 15.0
        self.capital_required_usd = 1000.0
        self.min_outs = ["120", "120"]
        self.meta = {
            "out1": "120",
            "overlay": {},
            "margin_ratio": 0.25,
            "strategy_family": "carry_trade",
            "route_family": "carry_trade",
            "gas_cost_estimate_wei": "5",
        }

    def model_copy(self, deep: bool = True):
        return copy.deepcopy(self)


class _RpcManager:
    def best_send(self):
        return "https://send"

    def best_private(self):
        return "https://private"

    def best_read(self):
        return "https://read"


def _runtime(*, capital_admission_service=None):
    return SimpleNamespace(
        cfg=SimpleNamespace(
            execution=SimpleNamespace(
                gas_mode="standard",
                send_mode="public",
                dry_run=False,
                governance=SimpleNamespace(enforce_on_auto=False),
                consensus=SimpleNamespace(enforce_on_auto=False),
                flashloan_fee_bps=0,
                gas_limit=200000,
                daily_gas_budget_wei="0",
            ),
            safety=SimpleNamespace(
                minProfitAbs=1,
                minProfitBps=0,
                slippage_bps=50,
                require_simulation=False,
            ),
        ),
        metrics=SimpleNamespace(gas_mode="standard", send_mode="public"),
        rpc_manager=_RpcManager(),
        _cc=SimpleNamespace(
            controls=SimpleNamespace(
                paused=False,
                sandbox_only=False,
                defensive_mode=False,
                reduce_exposure_half=False,
                governance_enabled=True,
            ),
            snapshot=lambda: {"fundStage": "internal_capital"},
        ),
        _capital_admission_service=capital_admission_service,
        _gov=None,
        _super=None,
        _consensus=None,
        capital_engine_state=lambda: {
            "borrow_mult_target_cap": 1.0,
            "capital_engine": {"family_targets": {"carry_trade": 0.25, "flashloan_atomic": 0.35}},
        },
        capital_truth=lambda: SimpleNamespace(
            capital_summary={"deployableUsd": 100000.0, "navUsd": 250000.0, "utilizationPct": 20.0}
        ),
    )


@pytest.mark.parametrize("reason", ["ok", "profit_after_costs_not_positive"])
def test_profitability_projection_prefers_post_mutation_revalidation_contract(reason: str):
    opp = _Opp()
    opp.meta["profitability"] = {
        "stage": "route_mutation_pending_revalidation",
        "source": "route_plan",
        "reason": "mutation_revalidation_required",
        "revalidated": False,
        "stale": True,
        "valid": True,
        "authoritative": False,
        "gross_profit_wei": "20",
        "profit_after_costs_wei": "0",
        "gas_cost_wei": "5",
        "flashloan_fee_wei": "0",
        "amount_in_wei": "100",
        "amount_out_wei": "120",
        "continuity": {"valid": True, "reason": "ok"},
    }
    opp.meta["post_mutation_revalidation"] = {
        "source": "execution_service",
        "stage": "post_mutation_submission_gate",
        "reason_code": reason,
        "degraded": reason != "ok",
        "authoritative": reason == "ok",
        "revalidated": True,
        "valid": reason == "ok",
        "continuity": {"valid": True, "reason": "ok"},
        "safety": {"revalidated": True, "reason": reason, "gas_cost_wei": "5"},
        "routeInvalidCauses": [],
        "selectedVenues": ["uni"],
        "providerPriority": ["aave"],
        "profitability": {
            "stage": "post_mutation_submission_gate",
            "source": "execution_service",
            "reason": reason,
            "revalidated": True,
            "stale": reason != "ok",
            "valid": reason == "ok",
            "authoritative": reason == "ok",
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "15" if reason == "ok" else "0",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        },
    }

    view = profitability_summary_projection(opp)

    assert view["stage"] == "post_mutation_submission_gate"
    assert view["reason"] == reason


def test_prepare_auto_execution_threads_canonical_post_mutation_revalidation_into_capital_admission(
    monkeypatch: pytest.MonkeyPatch,
):
    svc = ExecutionService()
    opp = _Opp()
    runtime = _runtime(capital_admission_service=CapitalAdmissionService())
    decision = SimpleNamespace(
        size_mult=1.0,
        borrow_mult=1.0,
        metadata={
            "execution_route_plan": {
                "executable": True,
                "selected_venues": ["uni", "curve"],
                "provider_priority": ["aave"],
                "route_invalid_causes": [],
            },
            "envelope": {"strategy_family": "carry_trade", "route_family": "carry_trade"},
        },
    )

    def _fake_apply_execution_route_plan(*, opp, plan):
        opp2 = opp.model_copy(deep=True)
        opp2.meta["profitability_continuity"] = {"valid": True, "reason": "ok"}
        opp2.meta["profitability"] = {
            "stage": "route_mutation_pending_revalidation",
            "source": "route_plan",
            "reason": "mutation_revalidation_required",
            "revalidated": False,
            "stale": True,
            "valid": True,
            "authoritative": False,
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "0",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        }
        opp2.meta["safety"] = {
            "revalidated": False,
            "reason": "mutation_revalidation_required",
            "gas_cost_wei": "5",
            "profit_after_costs_wei": "0",
        }
        opp2.meta["selected_venues"] = list(plan.get("selected_venues") or [])
        opp2.meta["provider_priority"] = list(plan.get("provider_priority") or [])
        opp2.meta["route_invalid_causes"] = list(plan.get("route_invalid_causes") or [])
        return opp2

    monkeypatch.setattr(
        "victor_ai_bot.runtime_services.execution_service.apply_execution_route_plan",
        _fake_apply_execution_route_plan,
    )

    result = svc.prepare_auto_execution(runtime, opp, bn=12, decision=decision)

    assert result.proceed is True
    contract = result.metadata["postMutationRevalidation"]
    assert contract["stage"] == "post_mutation_submission_gate"
    assert contract["reason_code"] == "ok"
    assert contract["authoritative"] is True
    assert contract["selectedVenues"] == ["uni", "curve"]
    assert contract["providerPriority"] == ["aave"]
    assert result.opportunity.meta["post_mutation_revalidation"] == contract
    assert result.metadata["capitalAdmission"]["details"]["postMutationRevalidation"] == contract


@pytest.mark.asyncio
async def test_try_execute_opportunity_reuses_existing_post_mutation_revalidation_before_live_gas():
    cfg = SimpleNamespace(
        execution=SimpleNamespace(
            dry_run=True,
            send_mode="public",
            max_submit_per_block=0,
            gas_mode="standard",
            gas_presets={},
            private_key_env="MISSING",
            from_address="",
            executor_address="",
            profit_to="",
            flashloan_fee_bps=0,
            gas_limit=200000,
        ),
        safety=SimpleNamespace(
            minProfitAbs=1,
            minProfitBps=0,
            require_estimate_gas=False,
            require_simulation=False,
            mev_adversarial_eval_enabled=False,
        ),
    )
    opp = _Opp()
    opp.meta["profitability_continuity"] = {"valid": True, "reason": "ok"}
    opp.meta["profitability"] = {
        "stage": "route_mutation_pending_revalidation",
        "source": "route_plan",
        "reason": "mutation_revalidation_required",
        "revalidated": False,
        "stale": True,
        "valid": True,
        "authoritative": False,
        "gross_profit_wei": "20",
        "profit_after_costs_wei": "0",
        "gas_cost_wei": "5",
        "flashloan_fee_wei": "0",
        "amount_in_wei": "100",
        "amount_out_wei": "120",
        "continuity": {"valid": True, "reason": "ok"},
    }
    opp.meta["post_mutation_revalidation"] = {
        "source": "execution_service",
        "stage": "post_mutation_submission_gate",
        "reason_code": "profit_after_costs_not_positive",
        "degraded": True,
        "authoritative": False,
        "revalidated": True,
        "valid": False,
        "continuity": {"valid": True, "reason": "ok"},
        "safety": {
            "revalidated": True,
            "reason": "profit_after_costs_not_positive",
            "gas_cost_wei": "5",
            "profit_after_costs_wei": "0",
            "flashloan_fee_wei": "0",
        },
        "routeInvalidCauses": [],
        "selectedVenues": ["uni", "curve"],
        "providerPriority": ["aave"],
        "profitability": {
            "stage": "post_mutation_submission_gate",
            "source": "execution_service",
            "reason": "profit_after_costs_not_positive",
            "revalidated": True,
            "stale": False,
            "valid": False,
            "authoritative": False,
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "0",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        },
    }

    result = await try_execute_opportunity(
        SimpleNamespace(),
        SimpleNamespace(),
        cfg,
        opp,
        current_block=9,
        last_submitted_block=0,
        cache=None,
        decision=None,
        force_dry_run=False,
        mev_guard=None,
        profiler=None,
    )

    assert result.ok is False
    assert result.reason == "profitability_contract:profit_after_costs_not_positive"
    assert result.plan["postMutationRevalidation"]["stage"] == "post_mutation_submission_gate"
    assert result.plan["profitability"]["stage"] == "post_mutation_submission_gate"
