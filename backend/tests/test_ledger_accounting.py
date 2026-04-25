import pytest

from victor_ai_bot.domain_errors import LedgerConsistencyError, ReconciliationError
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.treasury.ledger import LedgerLine, TreasuryLedger
from victor_ai_bot.treasury.reconciliation import (
    reconcile_balances,
    reconcile_internal_prime_journal,
)
from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService


def test_double_entry_validation_and_repository(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx = ledger.append_transaction(
        tx_type="receipt_settlement",
        chain="eth",
        receipt_id="r1",
        lines=[
            LedgerLine(account="asset:USDC", asset="USDC", amount=100.0),
            LedgerLine(account="equity:offset", asset="USD", amount=-100.0),
        ],
    )
    assert tx.receipt_id == "r1"
    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state.sqlite3")))
    repo.append_transaction(chain="eth", payload=tx.to_dict())
    assert repo.transactions_tail(chain="eth", limit=5)[0]["transaction_id"] == tx.transaction_id


def test_unbalanced_transaction_rejected(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    with pytest.raises(LedgerConsistencyError):
        ledger.append_transaction(
            tx_type="bad",
            chain="eth",
            lines=[LedgerLine(account="asset:USDC", asset="USDC", amount=10.0)],
        )


def test_strict_reconciliation_fails_closed(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    ledger.append(entry_type="realized_pnl", asset="USDC", amount=10.0, chain="eth")
    with pytest.raises(ReconciliationError):
        reconcile_balances(ledger, {"USDC": 0.0}, strict=True)


def test_internal_prime_journal_reconciliation_matches_open_loan_state():
    payload = reconcile_internal_prime_journal(
        {
            "borrowedUsd": 100.0,
            "familyExposure": {"flash_arb": 100.0},
            "loanCount": 1,
        },
        [
            {
                "ts_ms": 1,
                "tx_type": "prime_loan_open",
                "transaction_id": "tx_a",
                "metadata": {"loanId": "loan_1", "family": "flash_arb", "notionalUsd": 100.0},
            }
        ],
    )
    assert payload["ok"] is True
    assert payload["derived"]["borrowed_usd"] == 100.0
    assert payload["derived"]["family_exposure"] == {"flash_arb": 100.0}


def test_internal_prime_journal_reconciliation_detects_mismatch_and_unmatched_settlement():
    payload = reconcile_internal_prime_journal(
        {
            "borrowedUsd": 100.0,
            "familyExposure": {"flash_arb": 100.0},
            "loanCount": 1,
        },
        [
            {
                "ts_ms": 2,
                "tx_type": "prime_loan_settlement",
                "transaction_id": "tx_b",
                "metadata": {"loanId": "loan_1", "family": "flash_arb", "notionalUsd": 100.0},
            }
        ],
    )
    assert payload["ok"] is False
    assert "internal_prime_journal_unmatched_settlement" in set(payload["reasons"])
    assert "internal_prime_journal_borrowed_mismatch" in set(payload["reasons"])
    assert "internal_prime_journal_open_loan_count_mismatch" in set(payload["reasons"])


def test_canonical_balances_prefer_transaction_journal_and_include_prime_postings(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    ledger.append(entry_type="realized_pnl", asset="USDC", amount=10.0, chain="eth")
    report = ledger.balance_report()
    assert report["balanceSource"] == "transaction_journal"
    assert report["balances"] == {"USDC": 10.0}

    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    opened = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert opened["allowed"] is True

    report = ledger.balance_report()
    assert report["balanceSource"] == "transaction_journal"
    assert report["balances"]["USDC"] == -99990.0
    assert report["balances"]["USD"] == 100000.0


def test_auxiliary_ledger_state_uses_repository_transaction_balances(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    opened = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert opened["allowed"] is True

    runtime = type(
        "Runtime",
        (),
        {
            "cfg": type("Cfg", (), {"chain": type("Chain", (), {"name": "eth"})()})(),
            "_ledger_repo": prime._ledger_repo,
            "_ledger": None,
        },
    )()
    payload = AuxiliaryStateService().ledger_state(runtime)
    assert payload["balanceSource"] == "transaction_journal"
    assert payload["transactionCount"] >= 1
    assert payload["balances"]["USD"] == 100000.0
    assert payload["balances"]["USDC"] == -100000.0


def test_balance_report_scans_full_transaction_journal_not_last_5000_rows(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    for _ in range(5002):
        ledger.append_transaction(
            tx_type="receipt_settlement",
            chain="eth",
            lines=[
                LedgerLine(account="asset:USDC", asset="USDC", amount=1.0),
                LedgerLine(account="equity:offset", asset="USD", amount=-1.0),
            ],
        )
    report = ledger.balance_report()
    assert report["balanceSource"] == "transaction_journal"
    assert report["transactionCount"] == 5002
    assert report["balances"]["USDC"] == 5002.0


def test_repository_transaction_balance_report_scans_full_history(tmp_path):
    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state.sqlite3")))
    for i in range(5002):
        repo.append_transaction(
            chain="eth",
            payload={
                "transaction_id": f"tx_{i}",
                "ts_ms": i + 1,
                "tx_type": "receipt_settlement",
                "receipt_id": "",
                "lines": [
                    {"account": "asset:USDC", "asset": "USDC", "amount": 1.0},
                    {"account": "equity:offset", "asset": "USD", "amount": -1.0},
                ],
            },
        )
    report = repo.transaction_balance_report(chain="eth")
    assert report["balanceSource"] == "transaction_journal"
    assert report["transactionCount"] == 5002
    assert report["balances"]["USDC"] == 5002.0


def test_tail_projects_canonical_entry_view_from_transaction_journal(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    ledger.append_transaction(
        tx_type="receipt_settlement",
        chain="eth",
        receipt_id="r1",
        lines=[
            LedgerLine(account="asset:USD", asset="USD", amount=4.75),
            LedgerLine(account="equity:offset", asset="USD", amount=-4.75),
        ],
        metadata={
            "tx_hash": "0xabc",
            "status": 1,
            "route_id": "route-1",
            "strategy_family": "flashloan_atomic",
            "capture_lane": "PRIVATE",
            "realized_after_gas_usd": 6.0,
            "borrow_cost_usd": 1.25,
            "gas_cost_usd": 1.0,
            "profitabilityChain": {"realizedAfterGasWei": "6000000"},
        },
    )
    tail = ledger.tail(limit=5)
    assert {row["entry_type"] for row in tail} == {"realized_pnl", "borrow_cost"}
    assert next(row for row in tail if row["entry_type"] == "borrow_cost")["amount"] == -1.25
    assert (
        next(row for row in tail if row["entry_type"] == "realized_pnl")["metadata"][
            "settlementRole"
        ]
        == "realized_pnl"
    )


def test_repository_append_canonicalizes_legacy_entry_into_transaction_journal(tmp_path):
    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state.sqlite3")))
    repo.append(
        chain="eth",
        payload={
            "ts_ms": 1,
            "entry_type": "realized_pnl",
            "asset": "USDC",
            "amount": 10.0,
            "venue": "PRIVATE",
            "family": "flashloan_atomic",
            "note": "compat",
            "transaction_id": "tx_compat",
            "receipt_id": "r1",
            "metadata": {"source": "test"},
        },
    )
    report = repo.transaction_balance_report(chain="eth")
    assert report["balanceSource"] == "transaction_journal"
    assert report["transactionCount"] == 1
    assert report["balances"]["USDC"] == 10.0
    tail = repo.tail(chain="eth", limit=5)
    assert tail[0]["transaction_id"] == "tx_compat"
    assert tail[0]["metadata"]["source"] == "test"


def test_accounting_report_exposes_assets_liabilities_equity_and_encumbrance(tmp_path):
    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    ledger.append_transaction(
        tx_type="receipt_settlement",
        chain="eth",
        receipt_id="r1",
        lines=[
            LedgerLine(account="asset:USDC", asset="USDC", amount=100.0),
            LedgerLine(account="liability:USD", asset="USD", amount=25.0),
            LedgerLine(account="equity:offset", asset="USD", amount=-115.0),
            LedgerLine(
                account="internal_prime:inventory_reserved:USDC", asset="USDC", amount=-10.0
            ),
        ],
    )
    report = ledger.balance_report()
    assert report["accountBalances"]["asset:USDC"]["USDC"] == 100.0
    assert report["accountBalances"]["liability:USD"]["USD"] == 25.0
    assert report["accounting"]["assets"]["USDC"] == 100.0
    assert report["accounting"]["liabilities"]["USD"] == 25.0
    assert report["accounting"]["equity"]["USD"] == -115.0
    assert report["accounting"]["encumberedAssets"]["USDC"] == 10.0
    assert report["accounting"]["freeAssets"]["USDC"] == 90.0
    assert report["accounting"]["netAssets"]["USD"] == -25.0


def test_internal_prime_ledger_semantics_and_capital_truth_reconcile(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    opened = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert opened["allowed"] is True

    runtime = type(
        "Runtime",
        (),
        {
            "cfg": type("Cfg", (), {"chain": type("Chain", (), {"name": "eth"})()})(),
            "_ledger_repo": prime._ledger_repo,
            "_ledger": prime._ledger,
            "ledger_state": lambda self: AuxiliaryStateService().ledger_state(self),
            "internal_prime_state": lambda self: prime.snapshot(),
            "treasury_state": lambda self: {"enabled": True},
            "capital_engine_state": lambda self: {
                "capital_engine": {
                    "deployable_bankroll_wei": 0,
                    "estimated_capital_wei": 0,
                    "drawdown_buffer_wei": 0,
                    "family_targets": {},
                },
                "capital_efficiency_metrics": {},
                "reinvestment_policy": {},
            },
            "_bankroll": type(
                "Bankroll",
                (),
                {
                    "state": type(
                        "State", (), {"realized_profit_wei": 0, "last_amount_in_wei": 0}
                    )(),
                    "cfg": type(
                        "Cfg", (), {"auto_reinvest_enabled": False, "reinvest_rate_pct": 0.0}
                    )(),
                },
            )(),
            "launch_state": lambda self: {},
        },
    )()

    ledger_state = AuxiliaryStateService().ledger_state(runtime)
    assert ledger_state["accountBalances"]["internal_prime:borrowed_usd"]["USD"] == 100000.0
    assert ledger_state["accounting"]["liabilities"]["USD"] == 100000.0
    assert ledger_state["accounting"]["encumberedAssets"]["USDC"] == 100000.0

    from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService

    truth = CapitalTruthService().summary(runtime)
    assert truth["reconciliation"]["internal_prime_ledger"]["ok"] is True
    assert truth["reconciliation"]["internal_prime_ledger"]["ledger_borrowed_usd"] == 100000.0
    assert truth["reconciliation"]["internal_prime_ledger"]["encumbered_assets"] == {
        "USDC": 100000.0
    }


def test_internal_prime_collateral_reservation_flows_into_ledger_accounting_and_capital_truth(
    tmp_path,
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 200000.0)
    opened = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
            "collateral_efficiency": 0.95,
            "min_collateral_ratio": 1.10,
            "collateral_haircut_pct": 5.0,
        },
    )
    assert opened["allowed"] is True

    runtime = type(
        "Runtime",
        (),
        {
            "cfg": type("Cfg", (), {"chain": type("Chain", (), {"name": "eth"})()})(),
            "_ledger_repo": prime._ledger_repo,
            "_ledger": prime._ledger,
            "ledger_state": lambda self: AuxiliaryStateService().ledger_state(self),
            "internal_prime_state": lambda self: prime.snapshot(),
            "treasury_state": lambda self: {"enabled": True},
            "capital_engine_state": lambda self: {
                "capital_engine": {
                    "deployable_bankroll_wei": 0,
                    "estimated_capital_wei": 0,
                    "drawdown_buffer_wei": 0,
                    "family_targets": {},
                },
                "capital_efficiency_metrics": {},
                "reinvestment_policy": {},
            },
            "_bankroll": type(
                "Bankroll",
                (),
                {
                    "state": type(
                        "State", (), {"realized_profit_wei": 0, "last_amount_in_wei": 0}
                    )(),
                    "cfg": type(
                        "Cfg", (), {"auto_reinvest_enabled": False, "reinvest_rate_pct": 0.0}
                    )(),
                },
            )(),
            "launch_state": lambda self: {},
        },
    )()

    ledger_state = AuxiliaryStateService().ledger_state(runtime)
    assert ledger_state["accounting"]["liabilities"]["USD"] == 100000.0
    assert ledger_state["accounting"]["encumberedAssets"]["USDC"] == 115500.0

    from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService

    truth = CapitalTruthService().summary(runtime)
    assert truth["reconciliation"]["internal_prime_reserved_collateral_usd"] == 115500.0
    assert truth["reconciliation"]["internal_prime_collateralization_ratio"] == 1.155
    assert truth["reconciliation"]["internal_prime_ledger"]["ok"] is True
    assert truth["reconciliation"]["internal_prime_ledger"]["encumbered_assets"] == {
        "USDC": 115500.0
    }
    assert truth["reconciliation"]["internal_prime_ledger"]["open_loan_asset_exposure"] == {
        "USDC": 115500.0
    }
