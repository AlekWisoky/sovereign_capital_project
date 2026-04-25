from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys
import time

import pytest
from fastapi.testclient import TestClient

from victor_ai_bot.server import app
import victor_ai_bot.api_routes.withdraw_routes as withdraw_routes
import victor_ai_bot.runtime_services.withdraw_all_service as withdraw_all_service
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllService
from victor_ai_bot.tx_confirmation import assess_submitted_tx


class _RpcManager:
    def best_read(self):
        return "https://rpc.read"

    def best_send(self):
        return "https://rpc.send"

    def best_private(self):
        return "https://rpc.private"


class _WithdrawRuntime:
    def __init__(self, *, send_mode: str = "public"):
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
                send_mode=send_mode,
                withdraw_tokens=["0x3333333333333333333333333333333333333333"],
                profit_to="",
            ),
        )
        self.rpc_manager = _RpcManager()
        self._withdraw_all_service = None
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(paused=False, allocations_frozen=False, evolution_enabled=True)
        )
        self._launch_rollout = None

    def capital_truth_state(self):
        return {
            "status": "ok",
            "withdrawal": {"available": True},
            "categories": {"withdrawable_balance_wei": "100"},
        }


class _TxStatusRpcClient:
    receipt = None
    tx_visible = None
    tx_hash = "0x" + "ab" * 32
    send_raw_calls = 0
    send_private_calls = 0

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

    async def call(self, method: str, params=None):
        if method == "eth_getTransactionReceipt":
            return SimpleNamespace(ok=True, result=self.__class__.receipt)
        return SimpleNamespace(ok=False, error="unsupported")

    async def get_tx_by_hash(self, tx_hash: str):
        return self.__class__.tx_visible

    async def get_nonce(self, addr: str):
        return 7

    async def estimate_gas(self, tx):
        return 210000

    async def send_raw_tx(self, raw: str):
        self.__class__.send_raw_calls += 1
        return SimpleNamespace(ok=True, result=self.__class__.tx_hash)

    async def eth_send_raw_transaction(self, raw: str):
        return self.__class__.tx_hash

    async def send_private_tx(self, raw: str, *, max_block_number=None):
        self.__class__.send_private_calls += 1
        return SimpleNamespace(ok=True, result=self.__class__.tx_hash)

    async def block_number(self):
        return 123


class _RpcReceiptSuccess(_TxStatusRpcClient):
    receipt = {"status": "0x1", "blockNumber": "0x10"}
    tx_visible = None


class _RpcReceiptReverted(_TxStatusRpcClient):
    receipt = {"status": "0x0", "blockNumber": "0x11"}
    tx_visible = None


class _RpcPending(_TxStatusRpcClient):
    receipt = None
    tx_visible = {"hash": _TxStatusRpcClient.tx_hash}


class _RpcReceiptUnavailable(_TxStatusRpcClient):
    receipt = None
    tx_visible = None


class _RpcCallError(_TxStatusRpcClient):
    receipt = None
    tx_visible = None

    async def call(self, method: str, params=None):
        if method == "eth_getTransactionReceipt":
            return SimpleNamespace(ok=False, error="rpc_down")
        return SimpleNamespace(ok=False, error="unsupported")


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


def _reset_rpc_send_counters(client_cls):
    client_cls.send_raw_calls = 0
    client_cls.send_private_calls = 0


@pytest.mark.asyncio
async def test_assess_submitted_tx_classifies_success_pending_private_sent_and_unavailable():
    mined = await assess_submitted_tx(_RpcReceiptSuccess("https://rpc.read"), tx_hash=_RpcReceiptSuccess.tx_hash, send_mode="public")
    assert mined.tx_status == "mined_success"
    assert mined.receipt_status == 1
    assert mined.block_number == 16

    pending = await assess_submitted_tx(_RpcPending("https://rpc.read"), tx_hash=_RpcPending.tx_hash, send_mode="public")
    assert pending.tx_status == "pending"
    assert pending.receipt_status is None

    sent = await assess_submitted_tx(_RpcReceiptUnavailable("https://rpc.read"), tx_hash=_RpcReceiptUnavailable.tx_hash, send_mode="private")
    assert sent.tx_status == "sent"

    unavailable = await assess_submitted_tx(_RpcReceiptUnavailable("https://rpc.read"), tx_hash=_RpcReceiptUnavailable.tx_hash, send_mode="public")
    assert unavailable.tx_status == "receipt_unavailable"

    degraded = await assess_submitted_tx(_RpcCallError("https://rpc.read"), tx_hash=_RpcCallError.tx_hash, send_mode="public")
    assert degraded.tx_status == "receipt_unavailable"
    assert degraded.proof_reason == "receipt_lookup_degraded"


def test_withdraw_execute_returns_pending_not_completed_when_public_tx_is_visible(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "status": "pending",
        "tx_hash": _RpcPending.tx_hash,
        "from": "0x3333333333333333333333333333333333333333",
        "from_address": "0x3333333333333333333333333333333333333333",
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "amount": "100",
        "tx_status": "pending",
        "tx_proof_reason": "tx_visible",
    }


def test_withdraw_execute_exposes_receipt_lookup_degraded_proof_reason(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcCallError)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "status": "receipt_unavailable",
        "tx_hash": _RpcCallError.tx_hash,
        "from": "0x3333333333333333333333333333333333333333",
        "from_address": "0x3333333333333333333333333333333333333333",
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "amount": "100",
        "tx_status": "receipt_unavailable",
        "tx_proof_reason": "receipt_lookup_degraded",
    }



def test_withdraw_prepare_exposes_destination_and_executor_taxonomy(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xfeedbeef")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "from_address": "0x4444444444444444444444444444444444444444",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "from_address": "0x4444444444444444444444444444444444444444",
        "requested_from_address": "0x4444444444444444444444444444444444444444",
        "execution_from_address": None,
        "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "amount": "100",
        "tx": {
            "to": "0x2222222222222222222222222222222222222222",
            "data": "0xfeedbeef",
            "value": "0x0",
            "chainId": 1,
        },
        "suggested": {
            "gas_limit": "230000",
            "max_fee_wei": "100",
            "priority_fee_wei": "2",
            "nonce": "7",
        },
    }


def test_convert_withdraw_quote_exposes_quote_execution_shape(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntime(send_mode="public")
    runtime.cfg.chain.univ3_quoter_v2 = "0xdddddddddddddddddddddddddddddddddddddddd"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)

    async def _fake_quote(*args, **kwargs):
        fee = int(args[4])
        if fee == 3000:
            return SimpleNamespace(amount_out=1234)
        return SimpleNamespace(amount_out=1000)

    monkeypatch.setattr(withdraw_routes, "quote_exact_input_single", _fake_quote)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount_in": "250",
            "slippage_bps": 50,
            "fee_tiers": [500, 3000, 10000],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "amount_in": "250",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "token_out": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "expected_out": "1234",
        "min_out": "1228",
        "fee": "3000",
        "fee_tiers": ["500", "3000", "10000"],
        "slippage_bps": 50,
    }


def test_convert_withdraw_prepare_exposes_destination_executor_and_execution_shape(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdecafbad")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "250",
            "min_out": "200",
            "fee": "3000",
            "deadline": 1700000000,
            "from_address": "0x4444444444444444444444444444444444444444",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "from_address": "0x4444444444444444444444444444444444444444",
        "requested_from_address": "0x4444444444444444444444444444444444444444",
        "execution_from_address": None,
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "token_out": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "amount_in": "250",
        "min_out": "200",
        "fee": "3000",
        "deadline": 1700000000,
        "tx": {
            "to": "0x2222222222222222222222222222222222222222",
            "data": "0xdecafbad",
            "value": "0x0",
            "chainId": 1,
        },
        "suggested": {
            "gas_limit": "240000",
            "max_fee_wei": "100",
            "priority_fee_wei": "2",
            "nonce": "7",
            "deadline": 1700000000,
            "fee": "3000",
            "token_out": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        },
    }


def test_withdraw_prepare_defaults_sender_context_to_backend_execution_signer(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xfeedbeef")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["requested_from_address"] is None
    assert body["execution_from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["suggested"]["nonce"] == "7"


def test_convert_withdraw_prepare_defaults_sender_context_to_backend_execution_signer(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdecafbad")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "250",
            "min_out": "200",
            "fee": "3000",
            "deadline": 1700000000,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["requested_from_address"] is None
    assert body["execution_from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["suggested"]["nonce"] == "7"


def test_withdraw_prepare_prefers_backend_execution_signer_over_requested_from_address(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_withdraw_calldata", lambda **kwargs: "0xfeedbeef")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "from_address": "0x4444444444444444444444444444444444444444",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["requested_from_address"] == "0x4444444444444444444444444444444444444444"
    assert body["execution_from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["suggested"]["nonce"] == "7"


def test_convert_withdraw_prepare_prefers_backend_execution_signer_over_requested_from_address(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _TxStatusRpcClient)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdecafbad")
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "250",
            "min_out": "200",
            "fee": "3000",
            "deadline": 1700000000,
            "from_address": "0x4444444444444444444444444444444444444444",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["requested_from_address"] == "0x4444444444444444444444444444444444444444"
    assert body["execution_from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["suggested"]["nonce"] == "7"


def test_convert_routes_normalize_token_out_requested_in_responses(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntime(send_mode="public")
    runtime.cfg.chain.univ3_quoter_v2 = "0xdddddddddddddddddddddddddddddddddddddddd"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    async def _fake_quote(*args, **kwargs):
        return SimpleNamespace(amount_out=1234)

    monkeypatch.setattr(withdraw_routes, "quote_exact_input_single", _fake_quote)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    quote = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "  USDC  ",
            "amount_in": "250",
        },
    )
    assert quote.status_code == 200
    assert quote.json()["token_out_requested"] == "USDC"

    prepared = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "  USDC  ",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "250",
            "min_out": "200",
            "fee": "3000",
        },
    )
    assert prepared.status_code == 200
    assert prepared.json()["token_out_requested"] == "USDC"

    executed = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "  USDC  ",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )
    assert executed.status_code == 200
    assert executed.json()["token_out_requested"] == "USDC"

def test_convert_withdraw_execute_uses_send_raw_tx_in_public_mode(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    _reset_rpc_send_counters(_RpcPending)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert body["from"] == "0x3333333333333333333333333333333333333333"
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["to"] == "0x1111111111111111111111111111111111111111"
    assert body["executor"] == "0x2222222222222222222222222222222222222222"
    assert body["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert body["token_out_requested"] == "USDC"
    assert body["token_out"] == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert body["amount_in"] == "100"
    assert body["min_out"] == "0"
    assert body["fee"] == "3000"
    assert isinstance(body["deadline"], int)
    assert _RpcPending.send_raw_calls == 1
    assert _RpcPending.send_private_calls == 0


def test_convert_withdraw_execute_uses_private_send_when_configured(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    _reset_rpc_send_counters(_RpcReceiptUnavailable)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="private"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcReceiptUnavailable)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "sent"
    assert body["from"] == "0x3333333333333333333333333333333333333333"
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["to"] == "0x1111111111111111111111111111111111111111"
    assert body["executor"] == "0x2222222222222222222222222222222222222222"
    assert body["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert body["token_out_requested"] == "USDC"
    assert body["token_out"] == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert body["amount_in"] == "100"
    assert body["min_out"] == "0"
    assert body["fee"] == "3000"
    assert isinstance(body["deadline"], int)
    assert body["tx_proof_reason"] == "private_no_public_receipt"
    assert _RpcReceiptUnavailable.send_private_calls == 1
    assert _RpcReceiptUnavailable.send_raw_calls == 0


def test_convert_withdraw_execute_reports_immediate_receipt_revert_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(send_mode="public"), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _RpcReceiptReverted)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_routes, "build_convert_and_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "ok": False,
        "status": "degraded",
        "reason_code": "receipt_reverted",
        "reason": "receipt_reverted",
        "error": "receipt_reverted",
        "tx_hash": _RpcReceiptReverted.tx_hash,
        "from": "0x3333333333333333333333333333333333333333",
        "from_address": "0x3333333333333333333333333333333333333333",
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "token_out": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "amount_in": "100",
        "min_out": "0",
        "fee": "3000",
        "deadline": body["deadline"],
        "tx_status": "mined_reverted",
        "tx_proof_reason": "receipt_mined",
        "receipt_status": 0,
        "block_number": 17,
        "receipt": {"status": "0x0", "blockNumber": "0x11"},
    }


@pytest.mark.asyncio
async def test_withdraw_all_execute_pending_submission_is_not_reported_as_completed(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

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
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    assert payload["ok"] is True
    assert payload["last_status"] == "submitted"
    assert payload["result"]["status"] == "submitted"
    assert payload["result"]["submission_state"] == "pending"
    assert payload["result"]["submission_proof_reason"] == "tx_visible"
    assert payload["result"]["items"][0]["tx_status"] == "pending"
    assert payload["result"]["items"][0]["tx_proof_reason"] == "tx_visible"
    assert runtime._cc.controls.paused is True
    assert runtime._cc.controls.allocations_frozen is True
    assert runtime._cc.controls.evolution_enabled is False




@pytest.mark.asyncio
async def test_withdraw_all_execute_private_submission_persists_item_and_summary_proof_reason(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="private")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptUnavailable)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    assert payload["result"]["status"] == "submitted"
    assert payload["result"]["submission_state"] == "sent"
    assert payload["result"]["submission_proof_reason"] == "private_no_public_receipt"
    assert payload["result"]["items"][0]["tx_status"] == "sent"
    assert payload["result"]["items"][0]["tx_proof_reason"] == "private_no_public_receipt"
    assert payload["result"]["lifecycle_summary"]["submission_proof_reason"] == "private_no_public_receipt"


@pytest.mark.asyncio
async def test_withdraw_all_execute_only_marks_completed_on_immediate_mined_success(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptSuccess)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

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
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    assert payload["ok"] is True
    assert payload["last_status"] == "completed"
    assert payload["result"]["status"] == "completed"
    assert payload["result"]["items"][0]["tx_status"] == "mined_success"


@pytest.mark.asyncio
async def test_withdraw_all_execution_persists_lifecycle_summary_for_submitted_state(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

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
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )
    state = await svc.state(runtime)

    assert payload["result"]["items"][0]["tx_proof_reason"] == "tx_visible"
    assert payload["result"]["submission_proof_reason"] == "tx_visible"
    assert payload["result"]["lifecycle_summary"] == {
        "status": "submitted",
        "reason_code": "ok",
        "submission_state": "pending",
        "submission_proof_reason": "tx_visible",
        "item_count": 1,
        "attempted_item_count": 1,
        "confirmed_item_count": 0,
        "outstanding_item_count": 1,
        "reverted_item_count": 0,
        "failed_item_count": 0,
        "item_status_counts": {"pending": 1},
    }
    assert state["last_result_summary"] == {
        "status": "submitted",
        "reason_code": "ok",
        "submission_state": "pending",
        "submission_proof_reason": "tx_visible",
        "item_count": 1,
        "attempted_item_count": 1,
        "confirmed_item_count": 0,
        "outstanding_item_count": 1,
        "reverted_item_count": 0,
        "failed_item_count": 0,
        "item_status_counts": {"pending": 1},
    }


@pytest.mark.asyncio
async def test_withdraw_all_state_refresh_promotes_submitted_progress_to_completed(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )
    assert payload["last_status"] == "submitted"

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptSuccess)
    state = await svc.state(runtime)

    assert state["last_status"] == "completed"
    assert state["last_reason_code"] == "ok"
    assert state["last_result"]["status"] == "completed"
    assert state["last_result"]["items"][0]["tx_status"] == "mined_success"
    assert state["last_result_refresh_status"] == "refreshed"
    assert state["last_result_refresh_reason_code"] == "refreshed_updated"
    assert state["last_result_summary"] == {
        "status": "completed",
        "reason_code": "ok",
        "submission_state": "",
        "item_count": 1,
        "attempted_item_count": 1,
        "confirmed_item_count": 1,
        "outstanding_item_count": 0,
        "reverted_item_count": 0,
        "failed_item_count": 0,
        "item_status_counts": {"mined_success": 1},
    }


@pytest.mark.asyncio
async def test_withdraw_all_state_refresh_promotes_submitted_progress_to_execute_failed_on_revert(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )
    assert payload["last_status"] == "submitted"

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptReverted)
    state = await svc.state(runtime)

    assert state["last_status"] == "execute_failed"
    assert state["last_reason_code"] == "receipt_reverted"
    assert state["last_result"]["status"] == "execute_failed"
    assert state["last_result"]["failed_item"]["tx_status"] == "mined_reverted"
    assert state["last_result_refresh_status"] == "refreshed"
    assert state["last_result_refresh_reason_code"] == "refreshed_updated"
    assert state["last_result_summary"] == {
        "status": "execute_failed",
        "reason_code": "receipt_reverted",
        "submission_state": "",
        "item_count": 1,
        "attempted_item_count": 1,
        "confirmed_item_count": 0,
        "outstanding_item_count": 0,
        "reverted_item_count": 1,
        "failed_item_count": 1,
        "item_status_counts": {"mined_reverted": 1},
        "failed_tx_hash": _RpcReceiptReverted.tx_hash,
    }


@pytest.mark.asyncio
async def test_withdraw_all_state_refresh_does_not_downgrade_pending_visibility_when_receipt_lookup_is_weaker(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )
    assert payload["result"]["items"][0]["tx_status"] == "pending"

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptUnavailable)
    state = await svc.state(runtime)

    assert state["last_status"] == "submitted"
    assert state["last_result"]["items"][0]["tx_status"] == "pending"
    assert state["last_result_summary"]["outstanding_item_count"] == 1
    assert state["last_result_summary"]["item_status_counts"] == {"pending": 1}


@pytest.mark.asyncio
async def test_withdraw_all_state_reports_refresh_cooldown_metadata_without_requerying_immediately(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptSuccess)
    state = await svc.state(runtime)

    assert state["last_status"] == "submitted"
    assert state["last_result"]["items"][0]["tx_status"] == "pending"
    assert state["last_result_refresh"]["performed"] is False
    assert state["last_result_refresh"]["reason_code"] == "refresh_cooldown_active"
    assert state["last_result_refresh"]["refreshable"] is True
    assert state["last_result_refresh"]["outstanding_item_count"] == 1
    assert state["last_result_refresh"]["checked_ts_ms"] > 0
    assert state["last_result_refresh"]["next_eligible_refresh_ts_ms"] > state["last_result_refresh"]["checked_ts_ms"]
    assert state["last_result_refresh"]["fresh"] is True


@pytest.mark.asyncio
async def test_withdraw_all_state_revalidates_after_cooldown_and_exposes_refresh_metadata(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptSuccess)
    state = await svc.state(runtime)

    assert state["last_status"] == "completed"
    assert state["last_result"]["items"][0]["tx_status"] == "mined_success"
    assert state["last_result_refresh"]["performed"] is True
    assert state["last_result_refresh"]["status"] == "refreshed"
    assert state["last_result_refresh"]["reason_code"] == "refreshed_updated"
    assert state["last_result_refresh"]["refreshable"] is False
    assert state["last_result_refresh"]["outstanding_item_count"] == 0
    assert state["last_result_refresh"]["next_eligible_refresh_ts_ms"] == 0
    assert state["last_result_refresh"]["checked_ts_ms"] > 0
    assert state["last_result_refresh_status"] == "refreshed"
    assert state["last_result_refresh_reason_code"] == "refreshed_updated"


@pytest.mark.asyncio
async def test_withdraw_all_state_persists_refresh_failure_memory_when_read_rpc_cannot_revalidate(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcCallError)
    first = await svc.state(runtime)
    second = await svc.state(runtime)

    assert first["last_status"] == "submitted"
    assert first["last_result"]["items"][0]["tx_status"] == "pending"
    assert first["last_result_refresh"]["performed"] is False
    assert first["last_result_refresh"]["reason_code"] == "refresh_receipt_lookup_degraded"
    assert first["last_result_refresh"]["failure_active"] is True
    assert first["last_result_refresh"]["failure_reason_code"] == "refresh_receipt_lookup_degraded"
    assert first["last_result_refresh_status"] == "skipped"
    assert first["last_result_refresh_reason_code"] == "refresh_receipt_lookup_degraded"
    assert first["last_result_refresh_failure"]["count"] == 1
    assert first["last_result_refresh_failure"]["severity"] == "transient"
    assert first["last_result_refresh"]["failure_severity"] == "transient"
    assert first["last_result_refresh_failure_reason_code"] == "refresh_receipt_lookup_degraded"
    assert second["last_result_refresh"]["reason_code"] == "refresh_cooldown_active"
    assert second["last_result_refresh_failure"]["count"] == 1
    assert second["last_result_refresh_failure"]["severity"] == "transient"
    assert second["last_result_refresh"]["failure_severity"] == "transient"


@pytest.mark.asyncio
async def test_withdraw_all_state_buckets_refresh_failure_severity_for_prolonged_degradation(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    now_ms = int(time.time() * 1000)
    persisted = svc._load()
    persisted["last_result_refresh_failure_count"] = 4
    persisted["last_result_refresh_failure_reason_code"] = "refresh_receipt_lookup_degraded"
    persisted["last_result_refresh_failure_ts_ms"] = now_ms
    persisted["last_result_refresh_ts_ms"] = now_ms
    svc._save(persisted)

    state = await svc.state(runtime)

    assert state["last_result_refresh"]["failure_severity"] == "severe"
    assert state["last_result_refresh_failure"]["severity"] == "severe"


@pytest.mark.asyncio
async def test_withdraw_all_state_reports_missing_read_rpc_with_distinct_refresh_failure_reason(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )
    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)
    runtime.rpc_manager.best_read = lambda: ""

    state = await svc.state(runtime)

    assert state["last_result_refresh"]["reason_code"] == "refresh_read_rpc_missing"
    assert state["last_result_refresh"]["failure_reason_code"] == "refresh_read_rpc_missing"
    assert state["last_result_refresh_status"] == "skipped"
    assert state["last_result_refresh_reason_code"] == "refresh_read_rpc_missing"
    assert state["last_result_refresh_failure_reason_code"] == "refresh_read_rpc_missing"
    assert state["last_result_refresh_failure"]["reason_code"] == "refresh_read_rpc_missing"


@pytest.mark.asyncio
async def test_withdraw_all_state_clears_refresh_failure_memory_after_successful_revalidation(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcCallError)
    first = await svc.state(runtime)
    assert first["last_result_refresh_failure"]["count"] == 1

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcReceiptSuccess)
    second = await svc.state(runtime)

    assert second["last_status"] == "completed"
    assert second["last_result_refresh"]["performed"] is True
    assert second["last_result_refresh"]["reason_code"] == "refreshed_updated"
    assert second["last_result_refresh"]["failure_active"] is False
    assert second["last_result_refresh_failure"]["count"] == 0
    assert second["last_result_refresh_failure"]["severity"] == "none"
    assert second["last_result_refresh"]["failure_severity"] == "none"
    assert second["last_result_refresh_failure_reason_code"] == ""


@pytest.mark.asyncio
async def test_withdraw_all_state_self_heals_stale_refresh_metadata_once_submission_is_no_longer_active(tmp_path):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    persisted = svc._default_state()
    persisted["enabled"] = True
    persisted["approved_destination"] = "0x1111111111111111111111111111111111111111"
    persisted["last_status"] = "completed"
    persisted["last_reason_code"] = "ok"
    persisted["last_result"] = {
        "ok": True,
        "status": "completed",
        "items": [
            {
                "token": "0x3333333333333333333333333333333333333333",
                "amount": "250",
                "to": "0x1111111111111111111111111111111111111111",
                "mode": "backend",
                "tx_hash": "0x" + ("ab" * 32),
                "tx_status": "mined_success",
                "receipt_status": 1,
                "block_number": 16,
            }
        ],
        "lifecycle_summary": {
            "status": "completed",
            "reason_code": "ok",
            "submission_state": "",
            "item_count": 1,
            "attempted_item_count": 1,
            "confirmed_item_count": 1,
            "outstanding_item_count": 0,
            "reverted_item_count": 0,
            "failed_item_count": 0,
            "item_status_counts": {"mined_success": 1},
        },
    }
    persisted["last_result_refresh_ts_ms"] = 42_000
    persisted["last_result_refresh_status"] = "refreshed"
    persisted["last_result_refresh_reason_code"] = "refreshed_updated"
    svc._save(persisted)

    state = await svc.state(runtime)

    assert state["last_status"] == "completed"
    assert state["last_result_refresh"]["performed"] is False
    assert state["last_result_refresh"]["reason_code"] == "not_submitted"
    assert state["last_result_refresh_status"] == "idle"
    assert state["last_result_refresh_reason_code"] == "not_submitted"
    assert state["last_result_refresh_ts_ms"] == 0


@pytest.mark.asyncio
async def test_withdraw_all_state_decays_refresh_failure_memory_without_successful_revalidation(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    persisted = svc._load()
    persisted["last_result_refresh_ts_ms"] = max(0, int(persisted.get("last_result_refresh_ts_ms") or 0) - 11_000)
    svc._save(persisted)

    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcCallError)
    first = await svc.state(runtime)
    assert first["last_result_refresh_failure"]["count"] == 1

    now_ms = int(time.time() * 1000)
    persisted = svc._load()
    persisted["last_result_refresh_failure_count"] = 3
    persisted["last_result_refresh_failure_ts_ms"] = now_ms - ((withdraw_all_service._REFRESH_FAILURE_DECAY_INTERVAL_MS * 2) + 1_000)
    persisted["last_result_refresh_ts_ms"] = now_ms
    svc._save(persisted)

    decayed = await svc.state(runtime)

    assert decayed["last_result_refresh_failure"]["active"] is True
    assert decayed["last_result_refresh_failure"]["count"] == 1
    assert decayed["last_result_refresh_failure"]["severity"] == "transient"
    assert decayed["last_result_refresh"]["failure_severity"] == "transient"
    assert decayed["last_result_refresh_failure_reason_code"] == "refresh_receipt_lookup_degraded"
    assert decayed["last_result_refresh"]["reason_code"] == "refresh_cooldown_active"
    assert decayed["last_result_refresh_failure"]["next_decay_ts_ms"] > decayed["last_result_refresh_failure"]["ts_ms"]


@pytest.mark.asyncio
async def test_withdraw_all_state_clears_stale_refresh_failure_memory_without_successful_revalidation(tmp_path, monkeypatch):
    runtime = _WithdrawRuntime(send_mode="public")
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _RpcPending)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)

    svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await svc.preview(runtime)
    await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    now_ms = int(time.time() * 1000)
    persisted = svc._load()
    persisted["last_result_refresh_failure_count"] = 1
    persisted["last_result_refresh_failure_reason_code"] = "refresh_receipt_lookup_degraded"
    persisted["last_result_refresh_failure_ts_ms"] = now_ms - (withdraw_all_service._REFRESH_FAILURE_DECAY_INTERVAL_MS + 1_000)
    persisted["last_result_refresh_ts_ms"] = now_ms
    svc._save(persisted)

    cleared = await svc.state(runtime)

    assert cleared["last_result_refresh_failure"]["active"] is False
    assert cleared["last_result_refresh_failure"]["count"] == 0
    assert cleared["last_result_refresh_failure"]["severity"] == "none"
    assert cleared["last_result_refresh"]["failure_severity"] == "none"
    assert cleared["last_result_refresh_failure_reason_code"] == ""
    assert cleared["last_result_refresh_failure_ts_ms"] == 0
    assert cleared["last_result_refresh"]["reason_code"] == "refresh_cooldown_active"
