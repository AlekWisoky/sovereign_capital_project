from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.tx_confirmation import SubmittedTxStatus
import victor_ai_bot.api_routes.withdraw_routes as withdraw_routes


class _RpcManager:
    def best_read(self):
        return "https://rpc.read"

    def best_send(self):
        return "https://rpc.send"

    def best_private(self):
        return None


class _RpcManagerNoEndpoints:
    def best_read(self):
        return None

    def best_send(self):
        return None

    def best_private(self):
        return None


class _WithdrawRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(chain_id=1, usdc="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", usdt="0xcccccccccccccccccccccccccccccccccccccccc", name="ethereum"),
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


class _AuditSink:
    def __init__(self):
        self.calls = []

    def append(self, event: str, payload: dict, **meta):
        self.calls.append((event, payload, meta))
        return {"ok": True}


class _WithdrawRuntimeWithAudit(_WithdrawRuntime):
    def __init__(self):
        super().__init__()
        self._cc = SimpleNamespace(audit=_AuditSink())


class _JsonRpcClientMissingTxHash:
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
        return SimpleNamespace(ok=True, result=None)

    async def eth_send_raw_transaction(self, raw: str):
        return None

    async def block_number(self):
        return 123


class _JsonRpcClientInvalidTxHash:
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
        return SimpleNamespace(ok=True, result="not-a-tx-hash")

    async def eth_send_raw_transaction(self, raw: str):
        return "0xdeadbeef"

    async def block_number(self):
        return 123


class _JsonRpcClientSendFailure:
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
        return SimpleNamespace(ok=False, error="rpc_upstream_reverted")

    async def block_number(self):
        return 123


class _JsonRpcClientSendException:
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
        raise RuntimeError("rpc_send_boom")

    async def send_private_tx(self, raw: str, *, max_block_number=None):
        raise RuntimeError("rpc_private_boom")

    async def block_number(self):
        return 123


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


class _JsonRpcClientFalseOkTxHash:
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
        return SimpleNamespace(ok=False, result="0x" + ("12" * 32), error="rejected")

    async def block_number(self):
        return 123


class _JsonRpcClientFalseOkDictTxHash:
    def __init__(self, url: str, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def eth_call(self, to: str, data: str, *, block="latest"):
        return {
            "ok": True,
            "result": "0x" + ("0" * 24) + "3333333333333333333333333333333333333333",
        }

    async def get_nonce(self, addr: str):
        return 7

    async def estimate_gas(self, tx):
        return 210000

    async def send_raw_tx(self, raw: str):
        return {"ok": False, "result": "0x" + ("12" * 32), "error": "rejected"}

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


class _InvalidKeyAccount(_FakeAccount):
    @classmethod
    def from_key(cls, key: str):
        raise ValueError("invalid key")


def _install_fake_eth_account(monkeypatch, account_cls=_FakeAccount):
    module = ModuleType("eth_account")
    module.Account = account_cls
    monkeypatch.setitem(sys.modules, "eth_account", module)




def _assert_reject_response(
    body: dict,
    *,
    status: str,
    reason_code: str,
    action_reason: str | None = None,
    **context: str | int,
):
    assert body["ok"] is False
    assert body["status"] == status
    assert body["reason_code"] == reason_code
    assert body["reason"] == reason_code
    assert body["error"] == reason_code
    if action_reason is None:
        assert "action_reason" not in body
    else:
        assert body["action_reason"] == action_reason
    for key, value in context.items():
        normalized_key = "from" if key == "from_" else key
        assert body[normalized_key] == value

def _assert_send_failed_response(body: dict, *, action_reason: str | None = None):
    assert body["ok"] is False
    assert body["status"] == "degraded"
    assert body["reason_code"] == "send_failed"
    assert body["reason"] == "send_failed"
    assert body["error"] == "send_failed"
    assert body["to"] == "0x1111111111111111111111111111111111111111"
    assert body["executor"] == "0x2222222222222222222222222222222222222222"
    assert body["from_address"] == _FakeAccount.address
    assert body["from"] == _FakeAccount.address
    if "token" in body:
        assert body["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert body["amount"] == "100"
    else:
        assert body["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        assert body["token_out_requested"] == "USDC"
        assert body["token_out"] == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        assert body["amount_in"] == "100"
        assert body["fee"] == "3000"
        assert "min_out" in body
        assert isinstance(body["deadline"], int)
        assert body["deadline"] > 0
    if action_reason is None:
        assert "action_reason" not in body
    else:
        assert body["action_reason"] == action_reason



def test_withdraw_execute_accepts_reason_and_appends_audit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientMissingTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "send_failed"
    assert runtime._cc.audit.calls
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "send_failed"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["executor"] == "0x2222222222222222222222222222222222222222"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["from"] == _FakeAccount.address
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_accepts_reason_and_appends_audit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientMissingTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "send_failed"
    assert runtime._cc.audit.calls
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "send_failed"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["executor"] == "0x2222222222222222222222222222222222222222"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["from"] == _FakeAccount.address
    assert meta["reason"] == "operator override"


def test_withdraw_execute_invalid_private_key_env_returns_canonical_unavailable_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "not-a-private-key")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntimeWithAudit(), raising=False)
    _install_fake_eth_account(monkeypatch, _InvalidKeyAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_private_key_env",
        private_key_env="VICTOR_PRIVATE_KEY",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="1",
    )


def test_convert_withdraw_execute_invalid_private_key_env_returns_canonical_unavailable_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "not-a-private-key")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    _install_fake_eth_account(monkeypatch, _InvalidKeyAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_private_key_env",
        private_key_env="VICTOR_PRIVATE_KEY",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="1",
        min_out="0",
        fee="3000",
    )
    assert resp.json()["deadline"] > 0

class _JsonRpcClientOwnerMismatch:
    def __init__(self, url: str, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def eth_call(self, to: str, data: str, *, block="latest"):
        return SimpleNamespace(
            ok=True,
            result="0x" + ("0" * 24) + "4444444444444444444444444444444444444444",
        )


def test_withdraw_execute_blocks_when_private_key_is_not_executor_owner(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="blocked",
        reason_code="executor_owner_mismatch",
        private_key_env="VICTOR_PRIVATE_KEY",
        signer_address="0x3333333333333333333333333333333333333333",
        executor_owner="0x4444444444444444444444444444444444444444",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="1",
    )


def test_convert_withdraw_execute_blocks_when_private_key_is_not_executor_owner(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="blocked",
        reason_code="executor_owner_mismatch",
        private_key_env="VICTOR_PRIVATE_KEY",
        signer_address="0x3333333333333333333333333333333333333333",
        executor_owner="0x4444444444444444444444444444444444444444",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="1",
        min_out="0",
        fee="3000",
    )
    assert resp.json()["deadline"] > 0


def test_withdraw_prepare_invalid_amount_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="not-a-number",
    )

def test_convert_withdraw_prepare_invalid_from_address_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "from_address": "not-an-address",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_from_address",
        to="0x1111111111111111111111111111111111111111",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        from_address="not-an-address",
        from_="not-an-address",
    )


def test_withdraw_prepare_invalid_from_address_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "from_address": "not-an-address",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_from_address",
        to="0x1111111111111111111111111111111111111111",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        from_address="not-an-address",
        from_="not-an-address",
    )

def test_withdraw_prepare_zero_amount_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="0",
    )

def test_convert_withdraw_execute_zero_amount_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="0",
        min_out="0",
        fee="3000",
        deadline=0,
    )

def test_convert_withdraw_prepare_zero_amount_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="0",
        min_out="0",
        fee="3000",
        deadline=0,
    )

def test_convert_withdraw_prepare_negative_min_out_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "min_out": "-1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_min_out",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="-1",
        fee="3000",
        deadline=0,
    )

def test_convert_withdraw_prepare_non_positive_fee_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "fee": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_fee",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee="0",
        deadline=0,
    )

def test_convert_withdraw_prepare_out_of_range_fee_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "fee": str(16777216),
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_fee",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee="16777216",
        deadline=0,
    )

def test_convert_withdraw_prepare_explicit_non_positive_deadline_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "deadline": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_deadline",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee="3000",
        deadline=0,
    )

def test_withdraw_execute_zero_amount_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="0",
    )

def test_convert_withdraw_execute_negative_min_out_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
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
            "min_out": "-1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_min_out",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="-1",
        fee="3000",
        deadline=0,
    )


def test_convert_withdraw_execute_non_positive_fee_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
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
            "fee": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_fee",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee="0",
        deadline=0,
    )


def test_convert_withdraw_execute_out_of_range_fee_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
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
            "fee": str(16777216),
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_fee",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee=str(16777216),
        deadline=0,
    )


def test_convert_withdraw_execute_explicit_non_positive_deadline_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
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
            "deadline": "0",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_deadline",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="100",
        min_out="0",
        fee="3000",
        deadline=0,
    )

def test_withdraw_execute_send_failure_does_not_leak_raw_rpc_error(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientSendFailure)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    body = resp.json()
    _assert_send_failed_response(body)
    assert "rpc_upstream_reverted" not in str(body)


def test_withdraw_execute_send_exception_is_canonical_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.send_mode = "private"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientSendException)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_withdraw_execute_send_failed_with_reason_echoes_action_reason(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.send_mode = "private"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientSendException)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "reason": "operator requested cash transfer",
        },
    )

    assert resp.status_code == 200
    _assert_send_failed_response(resp.json(), action_reason="operator requested cash transfer")


def test_convert_withdraw_execute_send_failed_with_reason_echoes_action_reason(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.send_mode = "private"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientSendException)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "100",
            "min_out": "1",
            "fee": "3000",
            "reason": "operator requested cash transfer",
        },
    )

    assert resp.status_code == 200
    _assert_send_failed_response(resp.json(), action_reason="operator requested cash transfer")


def test_convert_withdraw_execute_send_exception_is_canonical_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.send_mode = "private"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientSendException)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_withdraw_execute_missing_tx_hash_is_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientMissingTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_withdraw_execute_invalid_tx_hash_is_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientInvalidTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_convert_withdraw_execute_missing_tx_hash_is_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientMissingTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_convert_withdraw_execute_invalid_tx_hash_is_send_failed(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientInvalidTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
    _assert_send_failed_response(resp.json())


def test_withdraw_all_state_unavailable_is_canonical(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.get("/api/withdraw/all/state", headers={"X-Admin-Key": "secret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "withdraw_all_service_unavailable"
    assert body["reason"] == "withdraw_all_service_unavailable"
    assert body["error"] == "withdraw_all_service_unavailable"
    assert body["summaryContract"]["truthFamily"] == "withdraw_all_state"
    assert body["summaryContract"]["readModel"] == "withdraw_all_state_projection_v1"


def test_withdraw_prepare_unknown_fields_are_rejected_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "ammount": "100",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["ammount"]},
    }



def test_convert_withdraw_prepare_unknown_fields_are_rejected_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "deadlinee": 123,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["deadlinee"]},
    }



def test_convert_withdraw_quote_unknown_fields_are_rejected_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "slippagebps": 50,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["slippagebps"]},
    }




def test_convert_withdraw_quote_invalid_fee_tiers_type_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "fee_tiers": "3000",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_fee_tiers",
        "reason": "invalid_fee_tiers",
        "error": "invalid_fee_tiers",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": "3000",
        "details": {"field": "fee_tiers"},
    }
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_quote"
    assert payload["outcome"] == "invalid_fee_tiers"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert payload["amount_in"] == "100"
    assert payload["fee_tiers"] == "3000"
    assert payload["details"] == {"field": "fee_tiers"}
    assert meta["reason"] == ""


def test_convert_withdraw_quote_invalid_fee_tier_entry_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "fee_tiers": ["500", "bad"],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_fee_tiers",
        "reason": "invalid_fee_tiers",
        "error": "invalid_fee_tiers",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["500", "bad"],
        "details": {"field": "fee_tiers", "index": 1},
    }


def test_convert_withdraw_quote_fractional_fee_tier_entry_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "fee_tiers": [500.5],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_fee_tiers",
        "reason": "invalid_fee_tiers",
        "error": "invalid_fee_tiers",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": [500.5],
        "details": {"field": "fee_tiers", "index": 0},
    }


def test_convert_withdraw_quote_out_of_range_fee_tier_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "fee_tiers": ["16777216"],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_fee_tiers",
        "reason": "invalid_fee_tiers",
        "error": "invalid_fee_tiers",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["16777216"],
        "details": {"field": "fee_tiers", "index": 0},
    }


def test_convert_withdraw_quote_invalid_slippage_bps_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "slippage_bps": "bad",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_slippage_bps",
        "reason": "invalid_slippage_bps",
        "error": "invalid_slippage_bps",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["500", "3000", "10000"],
        "slippage_bps": "bad",
        "details": {"field": "slippage_bps"},
    }


def test_convert_withdraw_quote_fractional_slippage_bps_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "slippage_bps": 1.5,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_slippage_bps",
        "reason": "invalid_slippage_bps",
        "error": "invalid_slippage_bps",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["500", "3000", "10000"],
        "slippage_bps": 1.5,
        "details": {"field": "slippage_bps"},
    }


def test_convert_withdraw_quote_out_of_range_slippage_bps_returns_canonical_invalid(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
            "slippage_bps": 5000,
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_slippage_bps",
        "reason": "invalid_slippage_bps",
        "error": "invalid_slippage_bps",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["500", "3000", "10000"],
        "slippage_bps": 5000,
        "details": {"field": "slippage_bps"},
    }

def test_convert_withdraw_quote_invalid_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "not-an-address",
            "token_out": "USDC",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_token",
        "reason": "invalid_token",
        "error": "invalid_token",
        "token_in": "not-an-address",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
    }



def test_withdraw_execute_unknown_fields_preempt_public_mode_block(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: True)
    _install_fake_eth_account(monkeypatch)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "memo": "should-not-be-here",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["memo"]},
    }

def test_withdraw_prepare_missing_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token="",
    )

def test_withdraw_execute_missing_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token="",
    )

def test_convert_withdraw_prepare_missing_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )


def test_convert_withdraw_execute_missing_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token_in="",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )

def test_withdraw_prepare_missing_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

def test_withdraw_execute_missing_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )

def test_convert_withdraw_prepare_missing_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )


def test_convert_withdraw_execute_missing_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )

def test_withdraw_prepare_invalid_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "not-an-address",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_token",
        to="0x1111111111111111111111111111111111111111",
        token="not-an-address",
    )



def test_withdraw_execute_invalid_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "not-an-address",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_destination",
        to="not-an-address",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )



def test_convert_withdraw_prepare_invalid_token_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "not-an-address",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_token",
        to="0x1111111111111111111111111111111111111111",
        token_in="not-an-address",
    )



def test_convert_withdraw_execute_invalid_destination_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "not-an-address",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_destination",
        to="not-an-address",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )


class _WithdrawRuntimeMissingStable(_WithdrawRuntime):
    def __init__(self):
        super().__init__()
        self.cfg.chain.usdc = ""


def test_convert_withdraw_quote_invalid_quoter_address_returns_canonical_unavailable(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntime()
    runtime.cfg.chain.univ3_quoter_v2 = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "invalid_quoter_address",
        "reason": "invalid_quoter_address",
        "error": "invalid_quoter_address",
        "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "token_out_requested": "USDC",
        "requested_token_out": "USDC",
        "amount_in": "100",
        "fee_tiers": ["500", "3000", "10000"],
        "slippage_bps": 50,
    }


def test_convert_withdraw_quote_no_rpc_endpoints_returns_contextual_unavailable(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    runtime.cfg.chain.univ3_quoter_v2 = "0x4444444444444444444444444444444444444444"
    runtime.rpc_manager = _RpcManagerNoEndpoints()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="no_rpc_endpoints",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
        amount_in="100",
        fee_tiers=["500", "3000", "10000"],
        slippage_bps=50,
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_quote"
    assert payload["outcome"] == "no_rpc_endpoints"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert payload["amount_in"] == "100"
    assert payload["fee_tiers"] == [500, 3000, 10000]
    assert payload["slippage_bps"] == 50
    assert meta["reason"] == ""


def test_convert_withdraw_quote_invalid_token_out_returns_canonical_invalid_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "not-an-address",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_token",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="not-an-address",
        requested_token_out="not-an-address",
    )


def test_convert_withdraw_quote_unresolved_default_stable_returns_canonical_unavailable(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntimeMissingStable(), raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="stable_not_configured",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )


def test_withdraw_prepare_invalid_executor_address_returns_canonical_unavailable_payload(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_executor_address",
        to="0x1111111111111111111111111111111111111111",
        executor="0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


def test_convert_withdraw_execute_invalid_executor_address_returns_canonical_unavailable_payload(monkeypatch):
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    runtime = _WithdrawRuntime()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "min_out": "0",
            "fee": "3000",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_executor_address",
        to="0x1111111111111111111111111111111111111111",
        executor="0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )


def test_convert_withdraw_prepare_invalid_executor_address_preserves_reason_and_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "min_out": "0",
            "fee": "3000",
            "reason": "preflight audit",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_executor_address",
        action_reason="preflight audit",
        to="0x1111111111111111111111111111111111111111",
        executor="0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "invalid_executor_address"
    assert payload["executor"] == "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    assert meta["reason"] == "preflight audit"


def test_withdraw_prepare_no_rpc_endpoints_returns_canonical_unavailable_and_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    runtime.rpc_manager = _RpcManagerNoEndpoints()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "from_address": "0x5555555555555555555555555555555555555555",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="no_rpc_endpoints",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="1",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        requested_from_address="0x5555555555555555555555555555555555555555",
        execution_from_address="0x3333333333333333333333333333333333333333",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "no_rpc_endpoints"
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["amount"] == "1"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["requested_from_address"] == "0x5555555555555555555555555555555555555555"
    assert payload["execution_from_address"] == _FakeAccount.address
    assert meta["reason"] == ""


def test_withdraw_execute_invalid_amount_preserves_action_reason_and_audits(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "invalid_amount"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "invalid_amount"
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_invalid_private_key_env_preserves_action_reason_and_audits(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "not-a-private-key")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _InvalidKeyAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "invalid_private_key_env"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "invalid_private_key_env"
    assert meta["reason"] == "operator override"


def test_withdraw_execute_owner_mismatch_preserves_action_reason_and_audits(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "executor_owner_mismatch"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "executor_owner_mismatch"
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_invalid_numeric_includes_raw_request_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_numeric",
        action_reason="operator override",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
        amount_in="not-a-number",
        min_out="0",
        fee="3000",
        deadline="",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "invalid_numeric"
    assert payload["amount_in"] == "not-a-number"
    assert payload["min_out"] == "0"
    assert payload["fee"] == "3000"
    assert payload["deadline"] == ""
    assert meta["reason"] == "operator override"


def test_withdraw_execute_invalid_amount_includes_raw_request_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        action_reason="operator override",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="not-a-number",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "invalid_amount"
    assert payload["amount"] == "not-a-number"
    assert meta["reason"] == "operator override"


def test_withdraw_execute_invalid_amount_preserves_action_reason_and_appends_audit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "invalid_amount"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "invalid_amount"
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_invalid_private_key_env_preserves_action_reason_and_appends_audit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "not-a-private-key")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _InvalidKeyAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "invalid_private_key_env"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "invalid_private_key_env"
    assert payload["private_key_env"] == "VICTOR_PRIVATE_KEY"
    assert meta["reason"] == "operator override"


def test_withdraw_execute_owner_mismatch_preserves_action_reason_and_appends_audit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "executor_owner_mismatch"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "executor_owner_mismatch"
    assert payload["private_key_env"] == "VICTOR_PRIVATE_KEY"
    assert payload["signer_address"] == "0x3333333333333333333333333333333333333333"
    assert payload["executor_owner"] == "0x4444444444444444444444444444444444444444"
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_owner_mismatch_audit_preserves_control_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reason_code"] == "executor_owner_mismatch"
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "executor_owner_mismatch"
    assert payload["private_key_env"] == "VICTOR_PRIVATE_KEY"
    assert payload["signer_address"] == "0x3333333333333333333333333333333333333333"
    assert payload["executor_owner"] == "0x4444444444444444444444444444444444444444"
    assert meta["reason"] == "operator override"



def test_convert_withdraw_prepare_no_rpc_endpoints_preserves_reason_and_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    runtime.rpc_manager = _RpcManagerNoEndpoints()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "1",
            "from_address": "0x5555555555555555555555555555555555555555",
            "reason": "rebalance leg",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="no_rpc_endpoints",
        action_reason="rebalance leg",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="1",
        min_out="0",
        fee="3000",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        requested_from_address="0x5555555555555555555555555555555555555555",
        execution_from_address="0x3333333333333333333333333333333333333333",
    )
    assert int(resp.json()["deadline"]) > 0
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "no_rpc_endpoints"
    assert payload["amount_in"] == "1"
    assert payload["fee"] == "3000"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["requested_from_address"] == "0x5555555555555555555555555555555555555555"
    assert payload["execution_from_address"] == _FakeAccount.address
    assert int(payload["deadline"]) > 0
    assert meta["reason"] == "rebalance leg"



def test_convert_withdraw_execute_no_rpc_endpoints_preserves_reason_and_audits_execute_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    runtime.rpc_manager = _RpcManagerNoEndpoints()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount_in": "1",
            "reason": "rebalance leg",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="no_rpc_endpoints",
        action_reason="rebalance leg",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        token_out="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        amount_in="1",
        min_out="0",
        fee="3000",
    )
    assert resp.json()["deadline"] > 0
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "no_rpc_endpoints"
    assert payload["from_address"] == _FakeAccount.address
    assert meta["reason"] == "rebalance leg"


def test_withdraw_execute_no_rpc_endpoints_preserves_reason_and_includes_signer_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + ("11" * 32))
    runtime = _WithdrawRuntimeWithAudit()
    runtime.rpc_manager = _RpcManagerNoEndpoints()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "reason": "rebalance leg",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="no_rpc_endpoints",
        action_reason="rebalance leg",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        from_address="0x3333333333333333333333333333333333333333",
        from_="0x3333333333333333333333333333333333333333",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="1",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "no_rpc_endpoints"
    assert payload["from_address"] == _FakeAccount.address
    assert meta["reason"] == "rebalance leg"


def test_convert_withdraw_prepare_allowlist_rejection_preserves_reason_and_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x9999999999999999999999999999999999999999",
            "amount": "1",
            "min_out": "0",
            "fee": "3000",
            "reason": "preflight allowlist",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="blocked",
        reason_code="dest_not_in_allowlist",
        action_reason="preflight allowlist",
        to="0x9999999999999999999999999999999999999999",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "dest_not_in_allowlist"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert meta["reason"] == "preflight allowlist"



def test_convert_withdraw_prepare_missing_stable_preserves_reason_and_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    runtime.cfg.chain.usdc = ""
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "min_out": "0",
            "fee": "3000",
            "reason": "stable required",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="stable_not_configured",
        action_reason="stable required",
        to="0x1111111111111111111111111111111111111111",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "stable_not_configured"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert meta["reason"] == "stable required"


def test_convert_withdraw_quote_missing_stable_preserves_requested_token_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    runtime.cfg.chain.usdc = ""
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/quote",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="stable_not_configured",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_quote"
    assert payload["outcome"] == "stable_not_configured"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert meta["reason"] == ""



def test_withdraw_prepare_invalid_executor_address_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="unavailable",
        reason_code="invalid_executor_address",
        to="0x1111111111111111111111111111111111111111",
        executor="0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "invalid_executor_address"
    assert payload["executor"] == "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    assert meta["reason"] == ""



def test_withdraw_prepare_allowlist_rejection_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x9999999999999999999999999999999999999999",
            "amount": "1",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="blocked",
        reason_code="dest_not_in_allowlist",
        to="0x9999999999999999999999999999999999999999",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "dest_not_in_allowlist"
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert meta["reason"] == ""


def test_withdraw_execute_raw_tx_hash_is_accepted(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", _WithdrawRuntime(), raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientRawTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
    async def _submitted(*args, **kwargs):
        return SubmittedTxStatus(
            tx_hash="0x" + ("12" * 32),
            tx_status="submitted",
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
        },
    )

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert resp.json()["status"] == "submitted"
    assert resp.json()["tx_hash"] == "0x" + ("12" * 32)


def test_convert_withdraw_execute_false_ok_hash_is_rejected(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientFalseOkTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
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
            "reason": "operator requested cash transfer",
        },
    )

    assert resp.status_code == 200
    _assert_send_failed_response(resp.json(), action_reason="operator requested cash transfer")
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "send_failed"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["executor"] == "0x2222222222222222222222222222222222222222"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["from"] == _FakeAccount.address
    assert meta["reason"] == "operator requested cash transfer"


def test_convert_withdraw_execute_false_ok_dict_hash_is_rejected(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientFalseOkDictTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)

    async def _owner_ok(*args, **kwargs):
        return None, "0x3333333333333333333333333333333333333333"

    monkeypatch.setattr(withdraw_routes, "validate_executor_owner_proof", _owner_ok)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
            "reason": "operator requested cash transfer",
        },
    )

    assert resp.status_code == 200
    _assert_send_failed_response(resp.json(), action_reason="operator requested cash transfer")
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "send_failed"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["executor"] == "0x2222222222222222222222222222222222222222"
    assert payload["from_address"] == _FakeAccount.address
    assert payload["from"] == _FakeAccount.address
    assert meta["reason"] == "operator requested cash transfer"


def test_withdraw_execute_mined_reverted_is_canonical_and_audited(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientRawTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )

    async def _submitted(*args, **kwargs):
        return SubmittedTxStatus(
            tx_hash="0x" + ("12" * 32),
            tx_status="mined_reverted",
            receipt_status=0,
            block_number=123,
            receipt={"status": "0x0", "blockNumber": "0x7b"},
            proof_reason="receipt_mined",
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
    assert resp.json() == {
        "ok": False,
        "status": "degraded",
        "reason_code": "receipt_reverted",
        "reason": "receipt_reverted",
        "error": "receipt_reverted",
        "tx_hash": "0x" + ("12" * 32),
        "from_address": "0x3333333333333333333333333333333333333333",
        "from": "0x3333333333333333333333333333333333333333",
        "to": "0x1111111111111111111111111111111111111111",
        "executor": "0x2222222222222222222222222222222222222222",
        "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "amount": "100",
        "tx_status": "mined_reverted",
        "tx_proof_reason": "receipt_mined",
        "receipt_status": 0,
        "block_number": 123,
        "receipt": {"status": "0x0", "blockNumber": "0x7b"},
        "action_reason": "operator override",
    }
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "receipt_reverted"
    assert payload["tx_hash"] == "0x" + ("12" * 32)
    assert payload["from_address"] == "0x3333333333333333333333333333333333333333"
    assert payload["from"] == "0x3333333333333333333333333333333333333333"
    assert payload["receipt_status"] == 0
    assert meta["reason"] == "operator override"


def test_convert_withdraw_execute_mined_reverted_is_canonical_and_audited(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientRawTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )

    async def _submitted(*args, **kwargs):
        return SubmittedTxStatus(
            tx_hash="0x" + ("12" * 32),
            tx_status="mined_reverted",
            receipt_status=0,
            block_number=123,
            receipt={"status": "0x0", "blockNumber": "0x7b"},
            proof_reason="receipt_mined",
        )

    monkeypatch.setattr(withdraw_routes, "assess_submitted_tx", _submitted)
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
            "reason": "operator override",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "degraded"
    assert body["reason_code"] == "receipt_reverted"
    assert body["reason"] == "receipt_reverted"
    assert body["error"] == "receipt_reverted"
    assert body["tx_hash"] == "0x" + ("12" * 32)
    assert body["from_address"] == "0x3333333333333333333333333333333333333333"
    assert body["from"] == "0x3333333333333333333333333333333333333333"
    assert body["to"] == "0x1111111111111111111111111111111111111111"
    assert body["executor"] == "0x2222222222222222222222222222222222222222"
    assert body["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert body["token_out_requested"] == "USDC"
    assert body["token_out"] == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert body["amount_in"] == "100"
    assert body["min_out"] == "0"
    assert body["fee"] == "3000"
    assert body["deadline"] > 0
    assert body["tx_status"] == "mined_reverted"
    assert body["tx_proof_reason"] == "receipt_mined"
    assert body["receipt_status"] == 0
    assert body["block_number"] == 123
    assert body["receipt"] == {"status": "0x0", "blockNumber": "0x7b"}
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "receipt_reverted"
    assert payload["tx_hash"] == "0x" + ("12" * 32)
    assert payload["from_address"] == "0x3333333333333333333333333333333333333333"
    assert payload["from"] == "0x3333333333333333333333333333333333333333"
    assert payload["receipt_status"] == 0
    assert meta["reason"] == "operator override"


def test_withdraw_execute_success_response_is_audited_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
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
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "pending"
    assert payload["tx_hash"] == "0x" + ("12" * 32)
    assert payload["tx_proof_reason"] == "tx_visible"
    assert payload["action_reason"] == "operator override"
    assert meta["reason"] == "operator override"



def test_convert_withdraw_execute_success_response_is_audited_canonically(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    _install_fake_eth_account(monkeypatch)
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "JsonRpcClient", _JsonRpcClientRawTxHash)
    monkeypatch.setattr(withdraw_routes, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(
        withdraw_routes,
        "build_convert_and_withdraw_calldata",
        lambda **kwargs: "0xdeadbeef",
    )

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
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
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
    assert body["action_reason"] == "operator override"
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "pending"
    assert payload["tx_hash"] == "0x" + ("12" * 32)
    assert payload["tx_proof_reason"] == "tx_visible"
    assert payload["deadline"] > 0
    assert payload["action_reason"] == "operator override"
    assert meta["reason"] == "operator override"


def test_withdraw_prepare_missing_destination_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "missing_destination"
    assert payload["to"] == ""
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert meta["reason"] == ""


def test_withdraw_prepare_missing_token_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token="",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "missing_token"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["token"] == ""
    assert meta["reason"] == ""


def test_withdraw_prepare_invalid_destination_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "not-an-address",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_destination",
        to="not-an-address",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "invalid_destination"
    assert payload["to"] == "not-an-address"
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert meta["reason"] == ""


def test_convert_withdraw_prepare_missing_destination_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "missing_destination"
    assert payload["to"] == ""
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert meta["reason"] == ""


def test_convert_withdraw_prepare_invalid_destination_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "not-an-address",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_destination",
        to="not-an-address",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "invalid_destination"
    assert payload["to"] == "not-an-address"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert meta["reason"] == ""


def test_convert_withdraw_prepare_invalid_from_address_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "1",
            "from_address": "not-an-address",
            "reason": "invalid from preflight",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_from_address",
        action_reason="invalid from preflight",
        to="0x1111111111111111111111111111111111111111",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        from_address="not-an-address",
        from_="not-an-address",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_prepare"
    assert payload["outcome"] == "invalid_from_address"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["from_address"] == "not-an-address"
    assert meta["reason"] == "invalid from preflight"


def test_withdraw_prepare_invalid_amount_audits_prepare_event(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _WithdrawRuntimeWithAudit()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/prepare",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "not-a-number",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="invalid_amount",
        to="0x1111111111111111111111111111111111111111",
        executor="0x2222222222222222222222222222222222222222",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        amount="not-a-number",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_prepare"
    assert payload["outcome"] == "invalid_amount"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["executor"] == "0x2222222222222222222222222222222222222222"
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["amount"] == "not-a-number"
    assert meta["reason"] == ""


def test_withdraw_execute_missing_destination_audits_token_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    runtime = _WithdrawRuntimeWithAudit()
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "missing_destination"
    assert payload["token"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert meta["reason"] == ""


def test_withdraw_execute_missing_token_audits_token_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    runtime = _WithdrawRuntimeWithAudit()
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token": "",
            "to": "0x1111111111111111111111111111111111111111",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_token",
        to="0x1111111111111111111111111111111111111111",
        token="",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "withdraw_execute"
    assert payload["outcome"] == "missing_token"
    assert payload["to"] == "0x1111111111111111111111111111111111111111"
    assert payload["token"] == ""
    assert meta["reason"] == ""


def test_convert_withdraw_execute_missing_destination_audits_convert_context(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setenv("VICTOR_PRIVATE_KEY", "0x" + "11" * 32)
    runtime = _WithdrawRuntimeWithAudit()
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    monkeypatch.setattr(withdraw_routes, "is_public_mode", lambda: False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/convert/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "token_in": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "token_out": "USDC",
            "to": "",
            "amount": "100",
        },
    )

    assert resp.status_code == 200
    _assert_reject_response(
        resp.json(),
        status="invalid",
        reason_code="missing_destination",
        to="",
        token_in="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        token_out_requested="USDC",
        requested_token_out="USDC",
    )
    event, payload, meta = runtime._cc.audit.calls[-1]
    assert event == "convert_withdraw_execute"
    assert payload["outcome"] == "missing_destination"
    assert payload["token_in"] == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert payload["token_out_requested"] == "USDC"
    assert payload["requested_token_out"] == "USDC"
    assert meta["reason"] == ""
