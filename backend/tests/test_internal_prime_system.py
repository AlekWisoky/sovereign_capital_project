from victor_ai_bot.internal_prime.allocator import InternalPrimeAllocator
from victor_ai_bot.internal_prime.contracts import PrimeBorrowRequest
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.treasury.ledger import TreasuryLedger


def test_internal_prime_allocate_settle_persists(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    out = prime.allocate(
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
    assert out["allowed"] is True
    loan_id = out["loan"]["loan_id"]
    settled = prime.settle(loan_id, realized_pnl_usd=250.0)
    assert settled["ok"] is True
    reloaded = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    assert reloaded.snapshot()["loanCount"] == 0


def test_internal_prime_family_cap_rejection(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=500000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.02,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert out["allowed"] is False
    assert out["reason"] == "family_cap_exceeded"


def test_internal_prime_family_cap_rejection_is_audited_without_mutating_capital(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=500000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy={
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.02,
            "prime_capacity_usd": 1_000_000.0,
        },
    )
    assert out["allowed"] is False
    assert out["reason"] == "family_cap_exceeded"
    assert out["auditRecorded"] is True
    assert out["ledgerTransaction"]["tx_type"] == "prime_loan_rejected"
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=5)
    assert tx_tail[-1]["tx_type"] == "prime_loan_rejected"
    assert tx_tail[-1]["metadata"]["reasonCode"] == "family_cap_exceeded"


def test_internal_prime_family_cap_respects_prime_capacity(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=300000.0,
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
    assert out["allowed"] is False
    assert out["reason"] == "family_cap_exceeded"


def test_internal_prime_utilization_tracks_configured_capacity_after_reload_and_settle(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 1_000_000.0)
    stage_policy = {
        "max_deployable_pct": 0.5,
        "family_cap_pct": 0.5,
        "prime_capacity_usd": 1_000_000.0,
    }
    first = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=250000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy=stage_policy,
    )
    second = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=250000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.9,
        ),
        stage_policy=stage_policy,
    )
    reloaded = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    snap = reloaded.snapshot()
    assert snap["capacityUsd"] == 1_000_000.0
    assert snap["utilization"] == 0.5

    settled = reloaded.settle(first["loan"]["loan_id"], realized_pnl_usd=100.0)
    assert settled["ok"] is True
    assert settled["utilization"] == 0.25

    after = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth").snapshot()
    assert after["capacityUsd"] == 1_000_000.0
    assert after["utilization"] == 0.25
    assert after["borrowedUsd"] == 250000.0
    assert after["loanCount"] == 1


def test_internal_prime_allocate_rolls_back_inventory_on_state_persist_failure(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)

    def _boom() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(prime, "_save_state", _boom)
    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "prime_state_persist_failed"
    assert prime.inventory.snapshot()["USDC"] == 500000.0
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0


def test_internal_prime_settle_rolls_back_inventory_on_state_persist_failure(tmp_path, monkeypatch):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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

    def _boom() -> None:
        raise OSError("disk full")

    monkeypatch.setattr(prime, "_save_state", _boom)
    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=10.0)

    assert settled == {"ok": False, "reason_code": "prime_settlement_persist_failed"}
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 100000.0
    assert snap["loanCount"] == 1
    assert prime.inventory.snapshot()["USDC"] == 400000.0


def test_internal_prime_allocate_and_settle_write_canonical_ledger_transactions(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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
    assert allocated["allowed"] is True
    assert allocated["ledgerTransaction"]["tx_type"] == "prime_loan_open"

    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=25.0)
    assert settled["ok"] is True
    assert settled["ledgerTransaction"]["tx_type"] == "prime_loan_settlement"

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=5)
    assert [row["tx_type"] for row in tx_tail[-2:]] == ["prime_loan_open", "prime_loan_settlement"]

    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state" / "xdv_runtime_state.sqlite3")))
    repo_tail = repo.transactions_tail(chain="eth", limit=5)
    assert [row["tx_type"] for row in repo_tail[:2]] == ["prime_loan_settlement", "prime_loan_open"]


def test_internal_prime_allocate_rolls_back_when_journal_write_fails(tmp_path, monkeypatch):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)

    def _boom(tx):
        raise OSError("ledger offline")

    monkeypatch.setattr(prime._ledger, "write_transaction", _boom)
    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "prime_journal_write_failed"
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0
    assert prime.inventory.snapshot()["USDC"] == 500000.0
    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state" / "xdv_runtime_state.sqlite3")))
    assert repo.transactions_tail(chain="eth", limit=5) == []


def test_internal_prime_explicit_denial_does_not_open_loan_and_is_audited(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    out = prime.allocate(
        PrimeBorrowRequest(
            family="flash_arb",
            capital_source="internal_prime",
            notional_usd=100000.0,
            asset="USDC",
            horizon_minutes=60.0,
            confidence=0.5,
        ),
        stage_policy={
            "min_confidence": 0.75,
            "max_deployable_pct": 0.5,
            "family_cap_pct": 0.25,
            "prime_capacity_usd": 1_000_000.0,
        },
    )

    assert out["allowed"] is False
    assert out["reason"] == "confidence_too_low"
    assert out["decision"]["approved"] is False
    assert out["auditRecorded"] is True
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0
    assert prime.inventory.snapshot()["USDC"] == 500000.0

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=5)
    assert tx_tail[-1]["tx_type"] == "prime_loan_rejected"
    assert tx_tail[-1]["metadata"]["reasonCode"] == "confidence_too_low"


def test_internal_prime_requires_tracked_inventory_asset_and_audits_rejection(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "inventory_untracked"
    assert out["decision"]["approved"] is False
    assert out["decision"]["details"]["detailsVersion"] == 2
    assert out["decision"]["details"]["inventoryTracked"] is False
    assert out["decision"]["details"]["inventoryAvailableUsd"] == 0.0
    assert out["decision"]["details"]["requiredCollateralUsd"] == 100000.0
    assert out["auditRecorded"] is True
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0
    assert snap["inventory"] == {}

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=5)
    assert tx_tail[-1]["tx_type"] == "prime_loan_rejected"
    assert tx_tail[-1]["metadata"]["reasonCode"] == "inventory_untracked"
    assert tx_tail[-1]["metadata"]["inventoryTracked"] is False
    assert tx_tail[-1]["metadata"]["requiredCollateralUsd"] == 100000.0


def test_internal_prime_settlement_rejection_is_audited_for_unknown_loan(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.settle("missing-loan", realized_pnl_usd=10.0)

    assert out["ok"] is False
    assert out["reason_code"] == "unknown_loan"
    assert out["auditRecorded"] is True
    assert out["ledgerTransaction"]["tx_type"] == "prime_loan_settlement_rejected"
    assert out["ledgerTransaction"]["metadata"]["reasonCode"] == "unknown_loan"

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=5)
    assert tx_tail[-1]["tx_type"] == "prime_loan_settlement_rejected"
    assert tx_tail[-1]["metadata"]["loanId"] == "missing-loan"


def test_internal_prime_settlement_fails_closed_when_inventory_tracking_missing(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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
    assert allocated["allowed"] is True

    # Simulate lost/corrupted inventory tracking after the loan is already open.
    prime.inventory._assets = {}
    prime.inventory._save()

    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=25.0)
    assert settled["ok"] is False
    assert settled["reason_code"] == "inventory_untracked_on_settlement"
    assert settled["auditRecorded"] is True
    assert settled["ledgerTransaction"]["tx_type"] == "prime_loan_disputed"
    assert (
        settled["ledgerTransaction"]["metadata"]["reasonCode"]
        == "inventory_untracked_on_settlement"
    )

    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 100000.0
    assert snap["loanCount"] == 1
    assert snap["disputedLoanCount"] == 1
    assert snap["openLoans"] == []
    assert snap["disputedLoans"][0]["status"] == "disputed"
    assert snap["disputedLoans"][0]["dispute_reason_code"] == "inventory_untracked_on_settlement"
    assert snap["inventory"] == {}

    ledger = TreasuryLedger(data_dir=str(tmp_path), chain="eth")
    tx_tail = ledger.transactions_tail(limit=10)
    assert tx_tail[-1]["tx_type"] == "prime_loan_disputed"
    assert tx_tail[-1]["metadata"]["loanId"] == allocated["loan"]["loan_id"]


def test_internal_prime_disputed_loan_can_settle_after_inventory_tracking_is_restored(tmp_path):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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
    assert allocated["allowed"] is True

    prime.inventory._assets = {}
    prime.inventory._save()
    disputed = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=25.0)
    assert disputed["ok"] is False
    assert disputed["ledgerTransaction"]["tx_type"] == "prime_loan_disputed"

    prime.inventory.seed("USDC", 0.0)
    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=25.0)
    assert settled["ok"] is True
    assert settled["ledgerTransaction"]["tx_type"] == "prime_loan_settlement"

    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0
    assert snap["disputedLoanCount"] == 0
    assert snap["disputedLoans"] == []
    assert snap["inventory"]["USDC"] == 100000.0


def test_internal_prime_corrupt_state_fails_closed_for_allocation_and_surfaces_snapshot_state(
    tmp_path,
):
    state_dir = tmp_path / "internal_prime"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state_eth.json").write_text("{not-json", encoding="utf-8")

    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)

    snap = prime.snapshot()
    assert snap["stateReady"] is False
    assert snap["stateStatus"] == "unavailable"
    assert snap["stateReasonCode"] == "prime_state_corrupt"

    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "prime_state_corrupt"
    assert out["auditRecorded"] is True
    assert out["ledgerTransaction"]["tx_type"] == "prime_loan_rejected"
    assert out["ledgerTransaction"]["metadata"]["reasonCode"] == "prime_state_corrupt"

    after = prime.snapshot()
    assert after["borrowedUsd"] == 0.0
    assert after["loanCount"] == 0
    assert after["stateReady"] is False


def test_internal_prime_corrupt_state_fails_closed_for_settlement_and_audits_rejection(tmp_path):
    state_dir = tmp_path / "internal_prime"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state_eth.json").write_text("{not-json", encoding="utf-8")

    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    out = prime.settle("loan_123", realized_pnl_usd=5.0)

    assert out["ok"] is False
    assert out["reason_code"] == "prime_state_corrupt"
    assert out["auditRecorded"] is True
    assert out["ledgerTransaction"]["tx_type"] == "prime_loan_settlement_rejected"
    assert out["ledgerTransaction"]["metadata"]["reasonCode"] == "prime_state_corrupt"


def test_internal_prime_collateral_policy_reserves_haircutted_collateral_and_releases_on_settlement(
    tmp_path,
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 200000.0)
    allocated = prime.allocate(
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
    assert allocated["allowed"] is True
    loan = allocated["loan"]
    assert loan["collateral_reserved_usd"] == 115500.0
    assert loan["collateral_ratio"] == 1.155
    assert loan["collateral_haircut_pct"] == 5.0
    assert loan["collateral_efficiency"] == 0.95
    assert prime.inventory.snapshot()["USDC"] == 84500.0

    snap = prime.snapshot()
    assert snap["reservedCollateralUsd"] == 115500.0
    assert snap["collateralizationRatio"] == 1.155

    settled = prime.settle(loan["loan_id"], realized_pnl_usd=12.0)
    assert settled["ok"] is True
    assert prime.inventory.snapshot()["USDC"] == 200000.0
    assert prime.snapshot()["reservedCollateralUsd"] == 0.0


def test_internal_prime_collateral_policy_denies_when_inventory_covers_notional_but_not_required_collateral(
    tmp_path,
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 110000.0)
    out = prime.allocate(
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
    assert out["allowed"] is False
    assert out["reason"] == "collateral_insufficiency"
    assert out["decision"]["reason_code"] == "collateral_insufficiency"
    assert out["decision"]["details"]["inventoryTracked"] is True
    assert out["decision"]["details"]["inventoryAvailableUsd"] == 110000.0
    assert out["decision"]["details"]["requiredCollateralUsd"] == 115500.0
    assert out["decision"]["details"]["primeCapacityUsd"] == 1000000.0


def test_internal_prime_allocate_rolls_back_cleanly_when_repository_append_fails(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)

    called = {"ledger": 0}

    def _repo_boom(*args, **kwargs):
        raise OSError("repo offline")

    def _ledger_write(tx):
        called["ledger"] += 1
        return tx

    monkeypatch.setattr(prime._ledger_repo, "append_transaction", _repo_boom)
    monkeypatch.setattr(prime._ledger, "write_transaction", _ledger_write)

    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "prime_journal_write_failed"
    assert called["ledger"] == 0
    assert prime.inventory.snapshot()["USDC"] == 500000.0
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0

    repo = LedgerRepository(PersistenceDB(str(tmp_path / "state" / "xdv_runtime_state.sqlite3")))
    assert repo.transactions_tail(chain="eth", limit=5) == []


def test_internal_prime_settle_rolls_back_cleanly_when_repository_append_fails(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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

    called = {"ledger": 0}

    def _repo_boom(*args, **kwargs):
        raise OSError("repo offline")

    def _ledger_write(tx):
        called["ledger"] += 1
        return tx

    monkeypatch.setattr(prime._ledger_repo, "append_transaction", _repo_boom)
    monkeypatch.setattr(prime._ledger, "write_transaction", _ledger_write)

    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=10.0)

    assert settled == {"ok": False, "reason_code": "prime_settlement_journal_write_failed"}
    assert called["ledger"] == 0
    assert prime.inventory.snapshot()["USDC"] == 400000.0
    snap = prime.snapshot()
    assert snap["borrowedUsd"] == 100000.0
    assert snap["loanCount"] == 1


def test_internal_prime_allocate_marks_state_unavailable_when_inventory_rollback_release_fails(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)

    def _ledger_boom(tx):
        raise OSError("ledger offline")

    def _release_boom(asset, amount):
        raise OSError("inventory release failed")

    monkeypatch.setattr(prime._ledger, "write_transaction", _ledger_boom)
    monkeypatch.setattr(prime.inventory, "release", _release_boom)

    out = prime.allocate(
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

    assert out["allowed"] is False
    assert out["reason"] == "prime_inventory_rollback_failed"
    snap = prime.snapshot()
    assert snap["stateReady"] is False
    assert snap["stateReasonCode"] == "prime_inventory_rollback_failed"
    assert snap["borrowedUsd"] == 0.0
    assert snap["loanCount"] == 0


def test_internal_prime_settle_marks_state_unavailable_when_inventory_rereserve_fails(
    tmp_path, monkeypatch
):
    prime = InternalPrimeAllocator(data_dir=str(tmp_path), chain="eth")
    prime.inventory.seed("USDC", 500000.0)
    allocated = prime.allocate(
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

    def _ledger_boom(tx):
        raise OSError("ledger offline")

    def _reserve_boom(asset, amount, *, strict=False):
        raise OSError("inventory reserve failed")

    monkeypatch.setattr(prime._ledger, "write_transaction", _ledger_boom)
    monkeypatch.setattr(prime.inventory, "reserve", _reserve_boom)

    settled = prime.settle(allocated["loan"]["loan_id"], realized_pnl_usd=25.0)

    assert settled == {"ok": False, "reason_code": "prime_settlement_inventory_rollback_failed"}
    snap = prime.snapshot()
    assert snap["stateReady"] is False
    assert snap["stateReasonCode"] == "prime_settlement_inventory_rollback_failed"
    assert snap["borrowedUsd"] == 100000.0
    assert snap["loanCount"] == 1
