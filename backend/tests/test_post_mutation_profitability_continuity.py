from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import try_execute_opportunity
from victor_ai_bot.profitability_state import refresh_post_mutation_revalidation_contract


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
        self.id = "opp-continuity"
        self.route_id = "route-continuity"
        self.route = _Route()
        self.expected_profit_raw = "20"
        self.expected_profit_usd = 15.0
        self.min_outs = ["120", "120"]
        self.meta = {
            "gas_cost_estimate_wei": "5",
            "selected_venues": ["uni"],
            "provider_priority": ["aave"],
            "route_invalid_causes": [],
            "profitability": {
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
            },
            "profitability_continuity": {"valid": True, "reason": "ok"},
        }

    def copy(self, deep: bool = True):
        return copy.deepcopy(self) if deep else copy.copy(self)


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(
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


@pytest.mark.parametrize(
    ("route_context", "reason"),
    [
        (
            {"selectedVenues": ["curve"], "providerPriority": ["aave"]},
            "mutation_desync_selected_venues",
        ),
        (
            {"selectedVenues": ["uni"], "providerPriority": ["balancer"]},
            "mutation_desync_provider_priority",
        ),
    ],
)
def test_refresh_post_mutation_revalidation_contract_invalidates_route_context_desync(
    route_context: dict,
    reason: str,
):
    opp = _Opp()

    contract = refresh_post_mutation_revalidation_contract(
        opp,
        _cfg(),
        stage="post_mutation_submission_gate",
        source="execution_service",
        route_context=route_context,
    )

    assert contract["valid"] is False
    assert contract["authoritative"] is False
    assert contract["reason_code"] == reason
    assert contract["continuity"]["valid"] is False
    assert reason in contract["continuity"]["mismatchCodes"]
    assert contract["continuity"]["expected"]["selected_venues"] == route_context["selectedVenues"]


@pytest.mark.asyncio
async def test_try_execute_opportunity_rejects_stale_existing_contract_on_amount_out_desync():
    cfg = _cfg()
    opp = _Opp()
    opp.meta["post_mutation_revalidation"] = {
        "source": "execution_service",
        "stage": "post_mutation_submission_gate",
        "reason_code": "ok",
        "degraded": False,
        "authoritative": True,
        "revalidated": True,
        "valid": True,
        "continuity": {
            "valid": True,
            "reason": "ok",
            "expected": {
                "amount_in_wei": "100",
                "amount_out_wei": "120",
                "route_id": "route-continuity",
                "selected_venues": ["uni"],
                "provider_priority": ["aave"],
                "route_invalid_causes": [],
                "gas_cost_wei": "5",
                "flashloan_fee_bps": 0,
            },
            "observed": {
                "amount_in_wei": "100",
                "amount_out_wei": "120",
                "route_id": "route-continuity",
                "selected_venues": ["uni"],
                "provider_priority": ["aave"],
                "route_invalid_causes": [],
                "gas_cost_wei": "5",
                "flashloan_fee_bps": 0,
            },
            "mismatchCodes": [],
        },
        "safety": {
            "revalidated": True,
            "reason": "ok",
            "gas_cost_wei": "5",
            "profit_after_costs_wei": "15",
            "flashloan_fee_wei": "0",
        },
        "routeInvalidCauses": [],
        "selectedVenues": ["uni"],
        "providerPriority": ["aave"],
        "profitability": {
            "stage": "post_mutation_submission_gate",
            "source": "execution_service",
            "reason": "ok",
            "revalidated": True,
            "stale": False,
            "valid": True,
            "authoritative": True,
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "15",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        },
    }
    opp.min_outs = ["90", "90"]
    opp.route.legs[-1].min_out = "90"

    result = await try_execute_opportunity(
        SimpleNamespace(),
        SimpleNamespace(),
        cfg,
        opp,
        current_block=1,
        last_submitted_block=0,
        cache=None,
        decision=None,
        force_dry_run=False,
        mev_guard=None,
        profiler=None,
    )

    assert result.ok is False
    assert result.reason == "profitability_contract:mutation_desync_amount_out"
    assert result.plan["postMutationRevalidation"]["reason_code"] == "mutation_desync_amount_out"
    assert (
        result.plan["postMutationRevalidation"]["continuity"]["observed"]["amount_out_wei"] == "90"
    )


@pytest.mark.asyncio
async def test_try_execute_opportunity_rejects_stale_existing_contract_on_gas_desync():
    cfg = _cfg()
    opp = _Opp()
    opp.meta["post_mutation_revalidation"] = {
        "source": "execution_service",
        "stage": "post_mutation_submission_gate",
        "reason_code": "ok",
        "degraded": False,
        "authoritative": True,
        "revalidated": True,
        "valid": True,
        "continuity": {
            "valid": True,
            "reason": "ok",
            "expected": {
                "amount_in_wei": "100",
                "amount_out_wei": "120",
                "route_id": "route-continuity",
                "selected_venues": ["uni"],
                "provider_priority": ["aave"],
                "route_invalid_causes": [],
                "gas_cost_wei": "5",
                "flashloan_fee_bps": 0,
            },
            "observed": {
                "amount_in_wei": "100",
                "amount_out_wei": "120",
                "route_id": "route-continuity",
                "selected_venues": ["uni"],
                "provider_priority": ["aave"],
                "route_invalid_causes": [],
                "gas_cost_wei": "5",
                "flashloan_fee_bps": 0,
            },
            "mismatchCodes": [],
        },
        "safety": {
            "revalidated": True,
            "reason": "ok",
            "gas_cost_wei": "5",
            "profit_after_costs_wei": "15",
            "flashloan_fee_wei": "0",
        },
        "routeInvalidCauses": [],
        "selectedVenues": ["uni"],
        "providerPriority": ["aave"],
        "profitability": {
            "stage": "post_mutation_submission_gate",
            "source": "execution_service",
            "reason": "ok",
            "revalidated": True,
            "stale": False,
            "valid": True,
            "authoritative": True,
            "gross_profit_wei": "20",
            "profit_after_costs_wei": "15",
            "gas_cost_wei": "5",
            "flashloan_fee_wei": "0",
            "amount_in_wei": "100",
            "amount_out_wei": "120",
            "continuity": {"valid": True, "reason": "ok"},
        },
    }
    opp.meta["gas_cost_estimate_wei"] = "9"

    result = await try_execute_opportunity(
        SimpleNamespace(),
        SimpleNamespace(),
        cfg,
        opp,
        current_block=1,
        last_submitted_block=0,
        cache=None,
        decision=None,
        force_dry_run=False,
        mev_guard=None,
        profiler=None,
    )

    assert result.ok is False
    assert result.reason == "profitability_contract:mutation_desync_gas_cost"
    assert result.plan["postMutationRevalidation"]["reason_code"] == "mutation_desync_gas_cost"
    assert result.plan["postMutationRevalidation"]["continuity"]["observed"]["gas_cost_wei"] == "9"
