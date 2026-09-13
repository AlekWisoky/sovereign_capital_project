from __future__ import annotations

import pytest

from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.runtime_services.family_hardening_service import FamilyHardeningService
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllService


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
    _capital_engine_state = {
        "capital_engine": {
            "deployable_bankroll_wei": 2000,
            "drawdown_buffer_wei": 300,
            "estimated_capital_wei": 2600,
            "family_targets": {"flash_arb": 0.6, "funding_arb": 0.2},
        },
        "capital_efficiency_metrics": {"deployedCapitalWei": 2000},
        "reinvestment_policy": {"reinvestPct": 40.0},
    }

    def capital_engine_state(self):
        return dict(self._capital_engine_state)

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


class _ReceiptOutcomeTruthRuntime(_Runtime):
    def fund_summary_state(self):
        return {
            "health": {
                "fundStage": "private_fund",
                "capitalReady": True,
                "internalPrimeReady": True,
                "privateRoutingReady": True,
                "receiptOutcomeTruthReasonCodes": ["settled_profit_truth_unavailable"],
                "receiptOutcomeTruthRecoveryHistoryStatus": "degraded",
                "receiptOutcomeTruthDegradedSinceTsMs": 4102444800000,
                "receiptOutcomeTruthDegradedDurationMs": 60000,
                "receiptOutcomeTruthDegradedCount": 2,
                "receiptOutcomeTruthReliabilityClass": "degraded",
                "receiptOutcomeTruthReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "receiptOutcomeTruthReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                ],
                "recoveryReady": False,
                "recoveryStatus": "capital_truth_restore_required",
                "recoveryReasonCode": "settled_profit_truth_unavailable",
                "recoveryReasonCodes": ["settled_profit_truth_unavailable"],
                "recoveryNextAction": "restore_receipt_outcome_truth",
                "recoveryHistoryComponent": "receipt_outcome_truth",
                "recoveryHistoryStatus": "degraded",
                "recoveryReliabilityClass": "degraded",
                "recoveryReliabilityReasonCode": "receipt_outcome_truth_reliability_degraded",
                "recoveryReliabilityReasonCodes": [
                    "receipt_outcome_truth_reliability_degraded",
                ],
            }
        }


def test_capital_truth_service_produces_canonical_categories():
    truth = CapitalTruthService().summary(_Runtime())
    assert truth["canonical"] is True
    assert truth["categories"]["realized_profit_wei"] == "500"
    assert truth["categories"]["retained_profit_wei"] == "200"
    assert truth["categories"]["withdrawable_balance_wei"] == "300"
    assert truth["withdrawal"]["available"] is False
    assert truth["withdrawal"]["reason_code"] == "capital_engine_freshness_unknown"
    assert truth["withdrawal"]["previewable"] is True


def test_family_hardening_service_preserves_receipt_outcome_truth_as_first_class_recovery_component():
    payload = FamilyHardeningService().summary(_ReceiptOutcomeTruthRuntime())

    funding = next(item for item in payload["items"] if item["family"] == "funding_arb")

    assert payload["reason_code"] == "settled_profit_truth_unavailable"
    assert payload["reason_codes"] == ["settled_profit_truth_unavailable"]
    assert payload["recovery_status"] == "capital_truth_restore_required"
    assert payload["recovery_reason_code"] == "settled_profit_truth_unavailable"
    assert payload["recovery_next_action"] == "restore_receipt_outcome_truth"
    assert payload["recovery_history_component"] == "receipt_outcome_truth"
    assert payload["receipt_outcome_truth_reason_codes"] == ["settled_profit_truth_unavailable"]
    assert payload["receipt_outcome_truth_recovery_history_status"] == "degraded"
    assert payload["receipt_outcome_truth_reliability_class"] == "degraded"
    assert funding["controls"]["receipt_outcome_truth_reason_codes"] == [
        "settled_profit_truth_unavailable"
    ]
    assert funding["controls"]["capital_eligible"] is False
    assert funding["controls"]["treasury_eligible"] is False

