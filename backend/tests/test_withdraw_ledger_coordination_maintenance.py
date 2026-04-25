from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

from fastapi.testclient import TestClient

from victor_ai_bot.api_routes import withdraw_routes
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.capital_event_repository import CapitalEventRepository
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.capital_truth_service import CapitalTruthService
from victor_ai_bot.server import app
from victor_ai_bot.treasury.ledger import TreasuryLedger
from victor_ai_bot.tx_confirmation import SubmittedTxStatus


class _RpcManager:
    def best_read(self):
        return "https://rpc.read"

    def best_send(self):
        return "https://rpc.send"

    def best_private(self):
        return None


class _JsonRpcClientRawTxHash:
    def __init__(self, url: str, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def eth_call(self, to: str, data: str, *, block="latest"):
        return SimpleNamespace(
            ok=True,
            result="0x" + ("0" * 24) + "3333333333333333333333333333333333333333",
        )

    async def get_nonce(self, addr: str):
        return 7

    async def estimate_gas(self, tx):
        return 210000

    async def send_raw_tx(self, raw: str):
        return "0x" + ("12" * 32)

    async def block_number(self):
        return 123


async def _suggest_gas(*args, **kwargs):
    return 100, 2


class _FakeSignedTx:
    raw_transaction = bytes.fromhex("12" * 32)


class _FakeAccount:
    address = "0x3333333333333333333333333333333333333333"

    @classmethod
    def from_key(cls, key: str):
        return cls()

    @staticmethod
    def sign_transaction(tx, key_hex: str):
        return _FakeSignedTx()


def _install_fake_eth_account(monkeypatch):
    module = ModuleType("eth_account")
    module.Account = _FakeAccount
    monkeypatch.setitem(sys.modules, "eth_account", module)


class _WithdrawLedgerRuntime:
    def __init__(self, tmp_path):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(
                chain_id=1,
                usdc="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                usdt="0xcccccccccccccccccccccccccccccccccccccccc",
                name="ethereum",
            ),
            execution=SimpleNamespace(
                withdraw_allowlist=["0x1111111111111111111111111111111111111111"],
                executor_address="0x2222222222222222222222222222222222222222",
                withdraw_mode="backend",
                private_key_env="VICTOR_PRIVATE_KEY",
                gas_mode="standard",
                gas_presets=None,
                gas_limit=200_000,
                send_mode="public",
                withdraw_tokens=[],
                profit_to="",
            ),
        )
        self.rpc_manager = _RpcManager()
        self._withdraw_all_service = None
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._capital_event_repo = CapitalEventRepository(self._db, chain=self.cfg.chain.name)
        self._ledger_repo = LedgerRepository(
            self._db, capital_event_repo=self._capital_event_repo, chain=self.cfg.chain.name
        )
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain=self.cfg.chain.name)

    def treasury_state(self):
        return {"enabled": True}

    def capital_engine_state(self):
        return {
            "capital_engine": {
                "deployable_bankroll_wei": 0,
                "estimated_capital_wei": 0,
                "drawdown_buffer_wei": 0,
                "family_targets": {},
            },
            "capital_efficiency_metrics": {},
            "reinvestment_policy": {},
        }

    def internal_prime_state(self):
        return {
            "borrowedUsd": 0.0,
            "capacityUsd": 1_000_000.0,
            "utilization": 0.0,
            "familyExposure": {},
            "loanCount": 0,
        }

    def launch_state(self):
        return {}

    def ledger_state(self):
        return {"balances": {}, "transactions": self._ledger_repo.transactions_tail(chain=self.cfg.chain.name, limit=50)}


class _AuditTail:
    def __init__(self, rows):
        self._rows = list(rows)

    def tail(self, *, limit=2000):
        return list(self._rows)[-int(limit) :]


def test_withdraw_execute_writes_ledger_and_capital_truth_prefers_ledger(monkeypatch, tmp_path):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawLedgerRuntime(tmp_path)
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientRawTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")

    async def _submitted(*args, **kwargs):
        return SubmittedTxStatus(
            tx_hash="0x" + ("12" * 32),
            tx_status="pending",
            receipt_status=None,
            block_number=None,
            receipt=None,
            proof_reason="tx_visible",
        )

    monkeypatch.setattr(withdraw_routes, "assess_submitted_tx", _submitted)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert body["tx_hash"] == "0x" + ("12" * 32)

    rows = runtime._ledger_repo.transactions_tail(chain=runtime.cfg.chain.name, limit=5)
    assert rows[-1]["tx_type"] == "withdraw_execute"
    assert rows[-1]["receipt_id"] == "0x" + ("12" * 32)
    assert rows[-1]["metadata"]["source"] == "withdraw_route"
    assert rows[-1]["metadata"]["tx_status"] == "pending"
    ledger_event = runtime._capital_event_repo.latest_event(domain="ledger")
    assert ledger_event["event_type"] == "withdraw_execute"
    assert ledger_event["receipt_id"] == "0x" + ("12" * 32)

    truth = CapitalTruthService().summary(runtime)
    withdraw_history = truth["reconciliation"]["receipt_settlement"]["withdraw_history"]
    assert withdraw_history["count"] == 1
    assert withdraw_history["source_counts"]["ledger"] == 1
    assert withdraw_history["items"][0]["source"] == "ledger"
    assert withdraw_history["items"][0]["outcome"] == "submitted"


def test_capital_truth_withdraw_history_falls_back_to_audit_when_ledger_missing():
    runtime = SimpleNamespace(
        _cc=SimpleNamespace(
            audit=_AuditTail(
                [
                    {
                        "ts_ms": 123,
                        "kind": "withdraw_execute",
                        "reason": "manual_withdraw",
                        "payload": {
                            "outcome": "submitted",
                            "token": "USDC",
                            "amount_wei": "25",
                            "tx_hash": "0xw1",
                        },
                    }
                ]
            )
        )
    )
    history = CapitalTruthService()._withdraw_history(runtime)
    assert history["count"] == 1
    assert history["source_counts"]["audit"] == 1
    assert history["items"][0]["source"] == "audit"
    assert history["items"][0]["tx_hash"] == "0xw1"
