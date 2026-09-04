from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.learning.borrowing_truth import resolve_borrowing_truth
from victor_ai_bot.learning.outcome_ledger import CanonicalOutcomeLedger


def test_borrowing_truth_distinguishes_requested_authorized_deployed_and_settled():
    runtime = SimpleNamespace(
        internal_prime_state=lambda: {
            "capacityUsd": 1_000_000.0,
            "utilization": 0.25,
            "loans": {
                "loan-7": {
                    "loan_id": "loan-7",
                    "notional_usd": 25_000.0,
                    "borrow_cost_usd": 12.5,
                    "status": "settled",
                }
            },
        }
    )
    truth = resolve_borrowing_truth(
        runtime=runtime,
        pending={
            "loan_id": "loan-7",
            "capital_admission": {
                "allowed": True,
                "details": {
                    "requestedNotionalUsd": 25_000.0,
                    "capitalSource": "internal_prime",
                },
            },
        },
    )

    assert truth.requested_usd == 25_000.0
    assert truth.authorized_usd == 25_000.0
    assert truth.deployed_usd == 25_000.0
    assert truth.settled_usd == 25_000.0
    assert truth.realized_cost_usd == 12.5
    assert truth.capacity_usd == 1_000_000.0
    assert truth.utilization == 0.25
    assert truth.source == "internal_prime_loan"
    assert truth.status == "settled"


def test_borrowing_truth_does_not_infer_settlement_from_global_prime_balance():
    runtime = SimpleNamespace(
        internal_prime_state=lambda: {
            "capacityUsd": 1_000_000.0,
            "utilization": 0.50,
            "borrowedUsd": 500_000.0,
            "loans": {},
        }
    )
    truth = resolve_borrowing_truth(
        runtime=runtime,
        pending={
            "capital_admission": {
                "allowed": True,
                "details": {
                    "requestedNotionalUsd": 10_000.0,
                    "capitalSource": "internal_prime",
                },
            }
        },
    )

    assert truth.requested_usd == 10_000.0
    assert truth.authorized_usd == 10_000.0
    assert truth.deployed_usd == 0.0
    assert truth.settled_usd == 0.0
    assert truth.reason_code == "borrowing_authorized"


def test_ordinary_capital_admission_is_not_classified_as_borrowing():
    truth = resolve_borrowing_truth(
        pending={
            "capital_admission": {
                "allowed": True,
                "details": {
                    "requestedNotionalUsd": 10_000.0,
                    "capitalSource": "treasury",
                },
            }
        }
    )

    assert truth.requested_usd == 0.0
    assert truth.authorized_usd == 0.0
    assert truth.deployed_usd == 0.0
    assert truth.settled_usd == 0.0
    assert truth.source == "unavailable"


def test_canonical_outcome_ledger_binds_live_capital_authority(tmp_path):
    ledger = CanonicalOutcomeLedger(
        data_dir=str(tmp_path),
        chain="ethereum",
        runtime=SimpleNamespace(
            internal_prime_state=lambda: {
                "capacityUsd": 500_000.0,
                "utilization": 0.20,
                "loans": {
                    "loan-1": {
                        "loan_id": "loan-1",
                        "notional_usd": 20_000.0,
                        "borrow_cost_usd": 8.0,
                        "status": "settled",
                    }
                },
            }
        ),
    )
    outcome = ledger._normalize(
        {
            "id": 1,
            "ts": 100,
            "chain": "ethereum",
            "opportunity_id": "opp-1",
            "route_id": "route-1",
            "tx_hash": "0xabc",
            "mode": "auto",
            "receipt_status": 1,
            "expected_profit_after_costs_wei": "100",
            "estimated_gas_cost_wei": "10",
            "flashloan_fee_wei": "0",
            "realized_gas_cost_wei": "5",
            "realized_profit_after_gas_wei": "95",
            "realized_profit_token": "WETH",
            "realized_profit_token_wei": "95",
            "realized_gas_cost_in_profit_token_wei": "5",
            "realized_profit_usd_micro": "1000000",
            "realized_gas_cost_usd_micro": "50000",
            "realized_profit_after_gas_usd_micro": "950000",
            "strategy_type": "arb",
            "income_stream": "trading",
            "venue_path": "private",
        },
        {
            "ts": 100,
            "amount_in_wei": "1000",
            "rl_state": "state-1",
            "rl_action_index": 5,
            "extra": {
                "capital_admission": {
                    "allowed": True,
                    "details": {
                        "requestedNotionalUsd": 20_000.0,
                        "capitalSource": "internal_prime",
                    },
                    "loanId": "loan-1",
                },
                "loan_id": "loan-1",
            },
        },
    )

    assert outcome.borrowing.loan_id == "loan-1"
    assert outcome.borrowing.settled_usd == 20_000.0
    assert outcome.borrowing.realized_cost_usd == 8.0
    assert outcome.context["borrowing"]["status"] == "settled"
