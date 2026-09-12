from __future__ import annotations

import pytest

from victor_ai_bot.execution_capture.institutional_sizing import (
    INSTITUTIONAL_V1_TIERS,
    build_institutional_sizing_contract,
)
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.capital_recovery_repository import (
    CapitalRecoveryRepository,
)
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.family_hardening_service import FamilyHardeningService
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllService
from victor_ai_bot.strategies.families import CATALOG


class _Chain:
    name = "ethereum"
    chain_id = 1


class _Execution:
    withdraw_mode = "txdata"
    withdraw_allowlist = ["0x1111111111111111111111111111111111111111"]
    withdraw_tokens = ["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    executor_address = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    send_mode = "public"
    private_key_env = "TEST_KEY"
    gas_mode = "standard"
    gas_presets = None
    gas_limit = 200000
    profit_to = "0x1111111111111111111111111111111111111111"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _BankrollState:
    realized_profit_wei = 500
    last_amount_in_wei = 2000
    success_streak = 1
    fail_streak = 0


class _BankrollCfg:
    auto_reinvest_enabled = True
    reinvest_rate_pct = 40.0


class _Bankroll:
    state = _BankrollState()
    cfg = _BankrollCfg()


class _RpcManager:
    def best_read(self):
        return "http://rpc.read"

    def best_send(self):
        return "http://rpc.send"

    def best_private(self):
        return ""


class _LaunchProfile:
    active_families = ["flash_arb"]
    family_states = {
        "flash_arb": "live",
        "funding_arb": "observe_only",
        "mev_search": "quarantined",
    }
    exploration_budget = {"used_trades": 0, "max_trades": 3}


class _LaunchRollout:
    profile = _LaunchProfile()


class _LaunchService:
    def summary(self, runtime):
        return {"ok": True, "profile": {"mode": "V1_PLUS_STABLE_ALPHA"}}


class _Runtime:
    cfg = _Cfg()
    _bankroll = _Bankroll()
    _launch_rollout = _LaunchRollout()
    _launch_service = _LaunchService()
    _cc = None
    rpc_manager = _RpcManager()

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 2000,
                "drawdown_buffer_wei": 300,
                "estimated_capital_wei": 2600,
                "family_targets": {"flash_arb": 0.6, "funding_arb": 0.2},
            },
            "capital_efficiency_metrics": {"deployedCapitalWei": 2000},
            "reinvestment_policy": {"reinvestPct": 40.0},
        }

    def treasury_state(self):
        return {"enabled": True}

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "loanCount": 0,
        }

    def ledger_state(self):
        return {
            "balances": {"USDC": 500.0},
            "tail": [{"ts_ms": 4102444800000, "asset": "USDC", "amount": 500.0}],
            "transactions": [],
        }

    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
            }
        }

    def strategy_scorecards_state(self):
        return {
            "families": [
                {
                    "family": "funding_arb",
                    "count": 8,
                    "executionSuccessRate": 0.7,
                    "gasEfficiency": 2.0,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.1,
                },
                {
                    "family": "mev_search",
                    "count": 8,
                    "executionSuccessRate": 0.8,
                    "gasEfficiency": 2.1,
                    "drawdownPenalty": 0.0,
                    "competitionPressure": 0.2,
                },
            ]
        }

    def engine_state(self):
        return {
            "summary": {
                "engines": [
                    {"engine_type": "funding_arb", "mode": "live"},
                    {"engine_type": "mev_search", "mode": "degraded"},
                ]
            },
            "items": [
                {
                    "opportunity": {"strategy_family": "funding_arb", "expected_profit_usd": 12.0},
                    "admission": {"allowed": True, "mode": "capped_live"},
                    "capture": {"action": "trade"},
                },
                {
                    "opportunity": {"strategy_family": "mev_search", "expected_profit_usd": 15.0},
                    "admission": {"allowed": False, "mode": "observe_only", "reason": "degraded"},
                    "capture": {"action": "drop", "drop_reason": "degraded_engine"},
                },
            ],
        }

    def telemetry_summary(self):
        return {"venueReliability": 0.9}

    def execution_calibration_state(self):
        return {"items": [{"route_family": "funding", "calibration_factor": 0.9}]}

    def capital_truth_state(self):
        return CapitalTruthService().summary(self)


def test_family_hardening_summary_covers_every_catalog_family():
    payload = FamilyHardeningService().summary(_Runtime())
    family_names = {str(item["family"]) for item in payload["items"]}
    assert set(CATALOG.keys()).issubset(family_names)
    assert payload["family_catalog_count"] == len(payload["family_catalog"])
    assert payload["uncovered_family_count"] == 0
    assert payload["uncovered_families"] == []
    assert "cross_chain_arb" in family_names
    assert "auto_generated_strategy" in family_names


def test_capital_truth_summary_exposes_canonical_ledgered_read_model():
    truth = CapitalTruthService().summary(_Runtime())
    assert truth["canonical"] is True
    assert truth["ledgered"] is True
    assert truth["auditable"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["reason_code"] == "capital_engine_freshness_unknown"
    assert truth["accounts"]["capital"]["total_wei"] == truth["categories"]["total_capital_wei"]
    assert (
        truth["accounts"]["profit"]["withdrawable_wei"]
        == truth["categories"]["withdrawable_balance_wei"]
    )
    assert truth["withdrawal"]["available"] is False
    assert truth["withdrawal"]["previewable"] is True


def test_capital_truth_summary_degrades_when_receipt_outcome_truth_is_unverified(tmp_path):
    runtime = _Runtime()
    runtime._db = PersistenceDB(str(tmp_path / "runtime.sqlite3"))
    repo = CapitalRecoveryRepository(runtime._db, chain="ethereum")
    repo.observe(
        component="receipt_outcome_truth",
        degraded=True,
        ts_ms=1_700_000_000_000,
        reason_code="settled_profit_truth_unavailable",
    )
    runtime._capital_recovery_repo = repo

    truth = CapitalTruthService().summary(runtime)

    assert truth["status"] == "degraded"
    assert truth["reason_code"] == "settled_profit_truth_unavailable"
    assert "settled_profit_truth_unavailable" in truth["status_reasons"]
    assert truth["reconciliation"]["receipt_outcome_truth"]["is_degraded"] is True
    assert (
        truth["reconciliation"]["receipt_outcome_truth"]["reason_code"]
        == "settled_profit_truth_unavailable"
    )


@pytest.mark.asyncio
async def test_withdraw_all_state_surfaces_staged_vs_approved_destination_controls(
    tmp_path, monkeypatch
):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

    enabled = svc.configure(runtime, {"enabled": True})
    assert enabled["ok"] is True

    staged = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": False,
        },
    )
    assert staged["ok"] is True
    assert staged["approved_destination"] == ""
    assert staged["pending_destination"] == "0x1111111111111111111111111111111111111111"

    pending_state = await svc.state(runtime)
    assert pending_state["destination_status"] == "pending_activation"
    assert pending_state["destination_reason_code"] == "pending_destination_activation_required"
    assert pending_state["destination_activation_required"] is True
    assert pending_state["action_available"] is False
    assert pending_state["action_reason_code"] == "approved_destination_missing"
    assert pending_state["execute_confirmation_text"] == "WITHDRAW EVERYTHING"
    assert pending_state["post_withdraw_posture"]["target_deployable_capital_wei"] == "0"

    approved = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    assert approved["ok"] is True

    approved_state = await svc.state(runtime)
    assert approved_state["destination_status"] == "approved"
    assert approved_state["destination_reason_code"] == "ok"
    assert approved_state["destination_ready"] is True
    assert approved_state["action_available"] is False
    assert approved_state["action_reason_code"] == "capital_truth_degraded"
    assert approved_state["preview_required"] is True
    assert approved_state["items"][0]["balance"] == "250"


def _sizing_contract(**overrides):
    values = {
        "requested_notional_usd": 250_000.0,
        "strategy_family": "flash_arb",
        "capital_source": "flashloan",
        "capital_engine_state": {
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-1",
            "deployable_usd": 2_000_000.0,
        },
        "treasury_state": {"capital_engine": {"family_targets": {"flash_arb": 0.25}}},
        "internal_prime_state": {
            "stateReady": True,
            "borrowedUsd": 0.0,
            "capacityUsd": 10_000_000.0,
            "utilization": 0.0,
            "familyExposure": {"flash_arb": 0.0},
        },
        "wealth_goal_state": {
            "state": {
                "targetReturnPct": 9.0,
                "currentReturnPct": 3.0,
                "capitalCommitmentPct": 25.0,
                "aggressivenessCap": 1.0,
                "maxDrawdownPct": 10.0,
                "drawdownPct": 1.0,
                "timeframeDays": 30,
                "goalStatus": "active",
            }
        },
        "execution_capture": {
            "depth_usd": 600_000.0,
            "pool_depth_cap_usd": 500_000.0,
            "liquidity_fragility": 0.2,
            "slippage_sensitivity": 0.2,
            "latency_half_life_ms": 1200,
            "simulation_confidence": 0.92,
            "freshness_score": 0.95,
            "venue_reliability_score": 0.9,
        },
        "latency_state": {"pipeline_latency_ms": 250.0, "pressure": 0.15, "endpoint_quality": 0.9},
        "economics": {
            "expected_gross_profit_usd": 180.0,
            "expected_net_profit_usd": 120.0,
            "gas_cost_usd": 8.0,
            "borrow_cost_usd": 12.0,
            "slippage_cost_usd": 20.0,
            "latency_cost_usd": 5.0,
            "failure_cost_usd": 15.0,
            "min_profit_usd": 5.0,
            "min_profit_bps": 2.0,
            "success_probability": 0.92,
            "margin_ratio": 0.01,
        },
        "governance": {
            "admitted": True,
            "reason_code": "ok",
            "live_authority": False,
            "execution_allowed": False,
        },
        "base_borrow_amount_wei": 0,
        "max_borrow_amount_wei": 0,
    }
    values.update(overrides)
    return build_institutional_sizing_contract(**values)


def test_institutional_sizing_contract_maps_authoritative_domains():
    contract = _sizing_contract(target_notional_usd=250_000.0)
    valid, errors = contract.validate()
    assert valid is True
    assert errors == ()
    assert contract.requested_notional_usd == 250_000.0
    assert contract.liquidity.pool_depth_cap_usd == 500_000.0
    assert contract.execution.latency_half_life_ms == 1200.0
    assert contract.capital.deployable_usd == 2_000_000.0
    assert contract.wealth_goal.aggressiveness_cap == 1.0
    assert contract.governance.admitted is True
    assert contract.governance.live_authority is False
    assert contract.metadata["behavior_change"] == "none"


def test_institutional_sizing_contract_rejects_missing_or_malformed_required_economics():
    cases = (
        ({"expected_net_profit_usd": None}, "expected_net_profit_missing"),
        ({"success_probability": None}, "success_probability_missing"),
        ({"margin_ratio": None}, "margin_ratio_missing"),
        ({"expected_net_profit_usd": "not-a-number"}, "expected_net_profit_missing"),
        ({"success_probability": "not-a-number"}, "success_probability_missing"),
        ({"margin_ratio": "not-a-number"}, "margin_ratio_missing"),
        ({"expected_net_profit_usd": float("nan")}, "expected_net_profit_missing"),
        ({"success_probability": float("inf")}, "success_probability_missing"),
        ({"margin_ratio": float("-inf")}, "margin_ratio_missing"),
    )
    for economics, expected_error in cases:
        contract = _sizing_contract(economics={**_sizing_contract().to_dict()["economics"], **economics})
        valid, errors = contract.validate()
        assert valid is False
        assert expected_error in errors


def test_institutional_sizing_contract_preserves_explicit_zero_economics():
    contract = _sizing_contract(
        economics={
            "expected_gross_profit_usd": 0.0,
            "expected_net_profit_usd": 0.0,
            "gas_cost_usd": 0.0,
            "borrow_cost_usd": 0.0,
            "slippage_cost_usd": 0.0,
            "latency_cost_usd": 0.0,
            "failure_cost_usd": 0.0,
            "min_profit_usd": 0.0,
            "min_profit_bps": 0.0,
            "success_probability": 0.0,
            "margin_ratio": 0.0,
        }
    )
    valid, errors = contract.validate()
    assert valid is True
    assert errors == ()
    assert contract.economics.expected_net_profit_usd == 0.0
    assert contract.economics.success_probability == 0.0
    assert contract.economics.margin_ratio == 0.0


def test_institutional_tiers_are_design_only_and_disabled():
    ids = [row["id"] for row in INSTITUTIONAL_V1_TIERS]
    amounts = [row["target_notional_usd"] for row in INSTITUTIONAL_V1_TIERS]
    assert ids == ["controlled_250k", "controlled_500k", "institutional_1m", "institutional_2m"]
    assert amounts == [250_000.0, 500_000.0, 1_000_000.0, 2_000_000.0]
    assert all(row["enabled"] is False for row in INSTITUTIONAL_V1_TIERS)


def test_internal_prime_requires_prime_authority():
    contract = _sizing_contract(
        capital_source="internal_prime",
        capital_engine_state={
            "status": "ok",
            "freshness_class": "fresh",
            "authority_id": "cap-auth-1",
            "deployable_usd": 2_000_000.0,
            "internal_prime_available": False,
        },
        internal_prime_state={
            "stateReady": False,
            "stateStatus": "unavailable",
            "capacityUsd": 10_000_000.0,
        },
    )
    valid, errors = contract.validate()
    assert valid is False
    assert "internal_prime_unavailable" in errors
