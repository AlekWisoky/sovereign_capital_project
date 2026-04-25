from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllService
from victor_ai_bot.treasury.ledger import TreasuryLedger


class _Chain:
    name = "ethereum"


class _Execution:
    executor_address = "0x2222222222222222222222222222222222222222"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _FailingLedgerRepo:
    def __init__(self, real_repo: LedgerRepository) -> None:
        self.real_repo = real_repo
        self.append_calls = 0

    def append_transaction(self, *, chain: str, payload: dict) -> None:
        del chain, payload
        self.append_calls += 1
        raise RuntimeError("repo_append_failed")

    def all_transactions(self, *, chain: str) -> list[dict]:
        return self.real_repo.all_transactions(chain=chain)


class _Runtime:
    def __init__(self, *, data_dir: str) -> None:
        self.cfg = _Cfg()
        self._ledger = TreasuryLedger(data_dir=data_dir, chain="ethereum")
        self._db = PersistenceDB(f"{data_dir}/state/runtime.sqlite3")
        self._ledger_repo = _FailingLedgerRepo(LedgerRepository(self._db))


class _FlakyLedgerRepo:
    def __init__(self, real_repo: LedgerRepository) -> None:
        self.real_repo = real_repo
        self.append_calls = 0
        self.fail_next = True

    def append_transaction(self, *, chain: str, payload: dict) -> None:
        self.append_calls += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("repo_append_failed")
        self.real_repo.append_transaction(chain=chain, payload=payload)

    def all_transactions(self, *, chain: str) -> list[dict]:
        return self.real_repo.all_transactions(chain=chain)


def test_withdraw_all_ledger_event_is_deduplicated_after_repo_failure(tmp_path):
    runtime = _Runtime(data_dir=str(tmp_path))
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")
    state = {"enabled": True}
    result = {"ok": True, "items": []}

    first = svc._persist_execute_outcome(
        runtime,
        state=dict(state),
        status="completed",
        reason_code="ok",
        result=dict(result),
        preview_id="preview-1",
        event="withdraw_all_completed",
        persisted_state=dict(state),
    )
    second = svc._persist_execute_outcome(
        runtime,
        state=dict(state),
        status="completed",
        reason_code="ok",
        result=dict(result),
        preview_id="preview-1",
        event="withdraw_all_completed",
        persisted_state=dict(state),
    )

    assert first["last_status"] == "completed"
    assert second["last_status"] == "completed"
    tx_rows = runtime._ledger.transactions_all()
    assert len(tx_rows) == 1
    assert tx_rows[0]["tx_type"] == "withdraw_all_completed"
    assert tx_rows[0]["metadata"]["event_key"] == "withdraw_all_completed|preview-1|completed|ok"
    assert runtime._ledger_repo.append_calls == 2


def test_withdraw_all_ledger_event_backfills_repo_once_it_recovers(tmp_path):
    runtime = _Runtime(data_dir=str(tmp_path))
    real_repo = LedgerRepository(runtime._db)
    runtime._ledger_repo = _FlakyLedgerRepo(real_repo)
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")
    state = {"enabled": True}
    result = {"ok": True, "items": []}

    first = svc._persist_execute_outcome(
        runtime,
        state=dict(state),
        status="completed",
        reason_code="ok",
        result=dict(result),
        preview_id="preview-2",
        event="withdraw_all_completed",
        persisted_state=dict(state),
    )
    second = svc._persist_execute_outcome(
        runtime,
        state=dict(state),
        status="completed",
        reason_code="ok",
        result=dict(result),
        preview_id="preview-2",
        event="withdraw_all_completed",
        persisted_state=dict(state),
    )

    assert first["last_status"] == "completed"
    assert second["last_status"] == "completed"
    tx_rows = runtime._ledger.transactions_all()
    assert len(tx_rows) == 1
    assert runtime._ledger_repo.append_calls == 2
    repo_rows = real_repo.all_transactions(chain="ethereum")
    assert len(repo_rows) == 1
    assert repo_rows[0]["metadata"]["event_key"] == "withdraw_all_completed|preview-2|completed|ok"
