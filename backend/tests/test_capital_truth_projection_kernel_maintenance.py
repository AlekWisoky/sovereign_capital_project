from __future__ import annotations

from victor_ai_bot.runtime_services.capital_state_projection import (
    build_capital_ledger_truth_projection,
    build_capital_operator_projection,
)
from victor_ai_bot.runtime_services.capital_truth_projection import (
    build_capital_truth_projection,
    build_compact_capital_truth_projection,
)


def _capital_truth_payload() -> dict:
    return build_capital_truth_projection(
        now_ms=1_710_000_000_000,
        status="ok",
        status_reason_code="ok",
        reasons=[],
        chain="ethereum",
        categories={
            "total_capital_wei": "100",
            "deployable_capital_wei": "70",
            "reserved_capital_wei": "10",
            "realized_profit_wei": "20",
            "retained_profit_wei": "5",
            "withdrawable_balance_wei": "15",
            "treasury_balance_wei": "95",
            "capital_locked_wei": "10",
        },
        family_allocations={"flash_arb": 0.7},
        family_capital_plan_version="family_capital_plan_v1",
        family_capital_plan=[{"id": "flashloan_atomic", "launchFamily": "flash_arb"}],
        freshness={
            "class": "current",
            "reason_codes": [],
            "reference_ts_ms": 1_710_000_000_000,
            "newest_source_ts_ms": 1_710_000_000_000,
            "source_spread_ms": 0,
        },
        ledger={
            "balances": {"USD": 12.5},
            "accountBalances": {"treasury": {"USD": 12.5}},
            "accounting": {"assetAccounts": {"USD": 12.5}},
            "tail": [{"receipt_id": "0xabc"}],
            "transactions": [{"transaction_id": "tx123"}],
            "last_ts_ms": 1_710_000_000_000,
        },
        reconciliation={
            "receipt_settlement": {
                "ok": True,
                "status": "settled",
                "last_receipt_id": "0xabc",
                "last_transaction_id": "tx123",
                "reason_codes": [],
            },
            "internal_prime_journal": {"ok": True},
            "internal_prime_ledger": {"ok": True},
            "capital_convergence": {"ok": True},
        },
        withdrawal={
            "available": True,
            "previewable": True,
            "reason_code": "ok",
            "reason_codes": ["ok"],
            "profit_destination": "treasury",
        },
    )


def test_capital_truth_projection_kernel_emits_canonical_contract_and_read_model():
    truth = _capital_truth_payload()

    assert truth["canonical"] is True
    assert truth["read_model"] == "ledgered_capital_truth_v3_converged"
    assert truth["summaryContract"]["stateContract"]["phase"] == "capital_truth_summary"
    assert truth["summaryContract"]["readModel"] == "capital_truth_projection_v1"
    assert truth["familyCapitalPlanVersion"] == "family_capital_plan_v1"
    assert truth["familyCapitalPlan"][0]["launchFamily"] == "flash_arb"



def test_compact_capital_truth_projection_extracts_ledger_and_settlement_truth():
    projection = build_compact_capital_truth_projection(_capital_truth_payload())

    assert projection["ledgerUsdBalance"] == 12.5
    assert projection["ledgerAvailable"] is True
    assert projection["settlementRecorded"] is True
    assert projection["lastSettlement"]["receiptId"] == "0xabc"
    assert projection["terminalProfitabilityAuthority"]["authoritative"] is True
    assert projection["capitalAdmission"]["ok"] is True



def test_capital_ledger_truth_projection_falls_back_to_canonical_capital_truth_state():
    truth = _capital_truth_payload()

    out = build_capital_ledger_truth_projection(
        None,
        capital_truth_health={"ok": True, "reasonCode": "ok"},
        capital_truth_state=truth,
    )

    assert out["ledgerUsdBalance"] == 12.5
    assert out["ledgerAvailable"] is True
    assert out["settlementRecorded"] is True
    assert out["lastSettlement"]["transactionId"] == "tx123"
    assert out["terminalProfitabilityAuthority"]["authoritative"] is True
    assert out["capitalAdmission"]["ok"] is True



def test_capital_operator_projection_uses_truth_kernel_when_summary_is_missing():
    truth = _capital_truth_payload()

    out = build_capital_operator_projection(
        capital_summary=None,
        capital_contract={"phase": "capital_contract"},
        capital_policy={"phase": "capital_policy"},
        capital_truth_health={"ok": True, "reasonCode": "ok"},
        capital_truth_state=truth,
    )

    assert out["capitalLedgerTruth"]["ledgerUsdBalance"] == 12.5
    assert out["capitalLedgerTruth"]["settlementRecorded"] is True
    assert out["capital"]["ledgerTruth"]["lastSettlement"]["receiptId"] == "0xabc"
    assert out["capital"]["ledgerTruth"]["capitalAdmission"]["ok"] is True
