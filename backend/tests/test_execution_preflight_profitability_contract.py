from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.execution import try_execute_opportunity


class _Leg:
    def __init__(self, *, amount_in: str = "100", min_out: str = "105"):
        self.amount_in = amount_in
        self.min_out = min_out
        self.dex = "uni"
        self.venue = "uni"
        self.token_in = "USDC"
        self.token_out = "WETH"
        self.data = "0x"


class _Route:
    def __init__(self):
        self.legs = [_Leg(), _Leg(amount_in="105", min_out="105")]


class _Opp:
    def __init__(self):
        self.route = _Route()
        self.min_outs = ["105", "105"]
        self.meta = {
            "profitability_continuity": {"valid": True, "reason": "ok"},
            "profitability": {
                "stage": "route_mutation_pending_revalidation",
                "source": "route_plan",
                "reason": "mutation_revalidation_required",
                "revalidated": False,
                "stale": True,
                "valid": True,
                "authoritative": False,
                "gross_profit_wei": "5",
                "profit_after_costs_wei": "0",
                "gas_cost_wei": "10",
                "flashloan_fee_wei": "0",
                "amount_in_wei": "100",
                "amount_out_wei": "105",
                "continuity": {"valid": True, "reason": "ok"},
            },
            "safety": {
                "gas_cost_wei": "10",
                "profit_after_costs_wei": "0",
                "revalidated": False,
                "reason": "mutation_revalidation_required",
            },
            "gas_cost_estimate_wei": "10",
        }
        self.route_id = "route-1"


class _Rpc:
    pass


@pytest.mark.asyncio
async def test_try_execute_opportunity_blocks_on_canonical_profitability_contract_before_live_gas():
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

    result = await try_execute_opportunity(
        _Rpc(),
        _Rpc(),
        cfg,
        opp,
        current_block=10,
        last_submitted_block=0,
        cache=None,
        decision=None,
        force_dry_run=False,
        mev_guard=None,
        profiler=None,
    )

    assert result.ok is False
    assert result.reason == "profitability_contract:profit_after_costs_not_positive"
    assert result.plan["profitability"]["stage"] == "post_mutation_submission_gate"
    assert result.plan["postMutationRevalidation"]["stage"] == "post_mutation_submission_gate"
    assert result.plan["profitability"]["authoritative"] is False
