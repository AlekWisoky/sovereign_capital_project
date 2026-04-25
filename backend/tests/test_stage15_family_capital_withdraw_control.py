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


def test_family_hardening_service_uniformly_marks_non_core_controls():
    payload = FamilyHardeningService().summary(_Runtime())
    funding = next(item for item in payload["items"] if item["family"] == "funding_arb")
    mev = next(item for item in payload["items"] if item["family"] == "mev_search")
    assert funding["controls"]["execution_eligible"] is True
    assert funding["controls"]["execution_reason_codes"] == []
    assert funding["controls"]["capital_eligible"] is True
    assert funding["controls"]["withdraw_guard_active"] is False
    assert funding["controls"]["treasury_eligible"] is True
    assert funding["controls"]["treasury_reason_codes"] == []
    assert mev["controls"]["no_trade"] is True
    assert "quarantined" in set(mev["explanation"]["reasons"])
    assert mev["controls"]["governance_eligible"] is False
    assert mev["controls"]["governance_reason_codes"] == ["quarantined"]
    assert mev["controls"]["execution_reason_codes"] == [
        "degraded",
        "execution_mode_not_live",
        "degraded_engine",
    ]
    assert "quarantined" in set(mev["controls"]["no_trade_reason_codes"])
    assert "execution_not_ready" in set(mev["controls"]["no_trade_reason_codes"])


@pytest.mark.asyncio
async def test_withdraw_all_requires_approved_destination_and_preview(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

    blocked = await svc.state(runtime)
    assert blocked["reason_code"] == "withdraw_all_disabled"

    configured = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    assert configured["ok"] is True

    preview = await svc.preview(runtime)
    assert preview["ok"] is False
    assert preview["reason_code"] == "capital_truth_degraded"
    execute = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": True,
        },
    )
    assert execute["ok"] is False
    assert execute["reason_code"] == "capital_truth_degraded"
    assert execute["result"]["reason_code"] == "capital_truth_degraded"


@pytest.mark.asyncio
async def test_withdraw_all_execute_persists_blocked_reason_for_operator_state(
    tmp_path, monkeypatch
):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    blocked = await svc.execute(
        runtime, {"preview_id": preview["preview_id"], "confirm_text": "NOPE", "dry_run": True}
    )
    assert blocked["ok"] is False
    assert blocked["reason_code"] == "confirmation_text_mismatch"

    state = await svc.state(runtime)
    assert state["last_status"] == "execute_blocked"
    assert state["last_reason_code"] == "confirmation_text_mismatch"
    assert state["last_result"]["reason_code"] == "confirmation_text_mismatch"


@pytest.mark.asyncio
async def test_withdraw_all_execute_persists_preview_stale_result(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    balances = [{"token": runtime.cfg.execution.withdraw_tokens[0], "balance": "250"}]

    async def _fake_balances(runtime, tokens):
        return list(balances)

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    balances[0] = {"token": runtime.cfg.execution.withdraw_tokens[0], "balance": "300"}

    stale = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": True,
        },
    )
    assert stale["ok"] is False
    assert stale["reason_code"] == "preview_stale"
    assert stale["result"]["current_reason_code"] == "capital_truth_degraded"

    state = await svc.state(runtime)
    assert state["last_status"] == "execute_blocked"
    assert state["last_reason_code"] == "preview_stale"
    assert state["last_result"]["current_reason_code"] == "capital_truth_degraded"


def test_capital_truth_service_degrades_on_internal_prime_integrity_mismatch():
    class _BadPrimeRuntime(_Runtime):
        def internal_prime_state(self):
            return {
                "borrowedUsd": 1_200_000.0,
                "capacityUsd": 1_000_000.0,
                "utilization": 0.25,
                "familyExposure": {"flash_arb": 1_300_000.0},
                "loanCount": 2,
            }

    truth = CapitalTruthService().summary(_BadPrimeRuntime())
    assert truth["status"] == "degraded"
    reasons = set(truth["status_reasons"])
    assert "internal_prime_capacity_exceeded" in reasons
    assert "internal_prime_utilization_mismatch" in reasons
    assert "internal_prime_family_exposure_exceeds_borrowed" in reasons
    assert truth["reconciliation"]["internal_prime_capacity_usd"] == 1_000_000.0
    assert truth["reconciliation"]["internal_prime_open_loan_count"] == 2


def test_capital_truth_service_degrades_on_internal_prime_journal_mismatch():
    class _PrimeJournalMismatchRuntime(_Runtime):
        def internal_prime_state(self):
            return {
                "borrowedUsd": 250000.0,
                "capacityUsd": 1_000_000.0,
                "utilization": 0.25,
                "familyExposure": {"flash_arb": 250000.0},
                "loanCount": 1,
            }

        def ledger_state(self):
            state = dict(super().ledger_state())
            state["transactions"] = []
            return state

    truth = CapitalTruthService().summary(_PrimeJournalMismatchRuntime())
    assert truth["status"] == "degraded"
    reasons = set(truth["status_reasons"])
    assert "internal_prime_journal_borrowed_mismatch" in reasons
    assert "internal_prime_journal_open_loan_count_mismatch" in reasons
    assert truth["reconciliation"]["internal_prime_journal"]["ok"] is False


def test_capital_truth_service_uses_full_prime_journal_not_tail_only(tmp_path):
    db = PersistenceDB(str(tmp_path / "state.sqlite3"))
    repo = LedgerRepository(db)
    for i in range(60):
        tx_type = "prime_loan_open" if i == 0 else "receipt_settlement"
        metadata = (
            {"loanId": "loan_1", "family": "flash_arb", "notionalUsd": 250000.0} if i == 0 else {}
        )
        repo.append_transaction(
            chain="ethereum",
            payload={
                "transaction_id": f"tx_{i}",
                "ts_ms": i + 1,
                "tx_type": tx_type,
                "receipt_id": "",
                "metadata": metadata,
                "lines": [],
            },
        )

    class _PrimeJournalFullHistoryRuntime(_Runtime):
        _ledger_repo = repo
        _ledger = None

        def internal_prime_state(self):
            return {
                "borrowedUsd": 250000.0,
                "capacityUsd": 1_000_000.0,
                "utilization": 0.25,
                "familyExposure": {"flash_arb": 250000.0},
                "loanCount": 1,
            }

        def ledger_state(self):
            state = dict(super().ledger_state())
            state["transactions"] = []
            return state

    truth = CapitalTruthService().summary(_PrimeJournalFullHistoryRuntime())
    assert truth["reconciliation"]["internal_prime_journal"]["ok"] is True
    assert "internal_prime_journal_borrowed_mismatch" not in set(truth["status_reasons"])
    assert truth["reconciliation"]["internal_prime_journal"]["derived"]["borrowed_usd"] == 250000.0


class _RuntimePrimeStateCorrupt(_Runtime):
    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "loanCount": 0,
            "stateReady": False,
            "stateStatus": "unavailable",
            "stateReasonCode": "prime_state_corrupt",
            "stateReason": "prime_state_corrupt",
        }


def test_capital_truth_service_fails_closed_when_internal_prime_state_is_unavailable():
    truth = CapitalTruthService().summary(_RuntimePrimeStateCorrupt())
    assert truth["status"] == "degraded"
    assert "prime_state_corrupt" in set(truth["status_reasons"])
