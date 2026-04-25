from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

import pytest

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
import victor_ai_bot.runtime_services.withdraw_all_service as withdraw_all_service
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllPersistenceError, WithdrawAllService


class _Chain:
    name = "ethereum"
    chain_id = 1


class _Execution:
    withdraw_allowlist = ["0x1111111111111111111111111111111111111111"]
    withdraw_tokens = []
    executor_address = "0x2222222222222222222222222222222222222222"
    withdraw_mode = "backend"
    private_key_env = "TEST_KEY"
    send_mode = "public"
    gas_mode = "standard"
    gas_presets = None
    gas_limit = 200000
    profit_to = ""


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _Runtime:
    cfg = _Cfg()
    _cc = None
    rpc_manager = SimpleNamespace(best_read=lambda: "http://rpc.read", best_send=lambda: "http://rpc.send", best_private=lambda: "")

    def capital_truth_state(self):
        return {
            "status": "ok",
            "withdrawal": {"available": True},
            "categories": {"withdrawable_balance_wei": "100"},
        }


def test_withdraw_all_config_rejects_unknown_fields_canonically(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    payload = svc.configure(runtime, {"enabled": True, "enabld": True})

    assert payload == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["enabld"]},
    }


def test_withdraw_all_config_parses_canonical_bool_strings(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    enabled = svc.configure(runtime, {"enabled": "true"})
    disabled = svc.configure(runtime, {"enabled": "false"})

    assert enabled["ok"] is True
    assert enabled["enabled"] is True
    assert disabled["ok"] is True
    assert disabled["enabled"] is False



def test_withdraw_all_config_empty_payload_is_a_true_no_op(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    payload = svc.configure(runtime, {})

    assert payload["ok"] is True
    assert payload["updated_ts_ms"] == 0
    from pathlib import Path as _Path

    assert not _Path(svc._path).exists()


def test_withdraw_all_config_requires_destination_when_activate_is_true(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    payload = svc.configure(runtime, {"activate_destination": True})

    assert payload == {
        "ok": False,
        "status": "invalid",
        "reason_code": "missing_destination",
        "reason": "missing_destination",
        "error": "missing_destination",
        "details": {"field": "destination"},
    }


def test_withdraw_all_config_rejects_non_hex_destination(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    payload = svc.configure(runtime, {"destination": "0xgggggggggggggggggggggggggggggggggggggggg"})

    assert payload == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_destination",
        "reason": "invalid_destination",
        "error": "invalid_destination",
        "details": {"field": "destination", "value": "0xgggggggggggggggggggggggggggggggggggggggg"},
    }



def test_withdraw_all_config_route_rejects_invalid_boolean_before_mutation(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/all/config",
        headers={"X-Admin-Key": "secret"},
        json={"enabled": "definitely", "destination": "0x1111111111111111111111111111111111111111"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_boolean_value",
        "reason": "invalid_boolean_value",
        "error": "invalid_boolean_value",
        "details": {"field": "enabled", "value": "definitely"},
    }


@pytest.mark.asyncio
async def test_withdraw_all_execute_rejects_unknown_fields_without_mutating_state(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

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
    before = svc._load()

    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": True,
            "dryrun": True,
        },
    )

    assert payload == {
        "ok": False,
        "status": "invalid",
        "reason_code": "unknown_request_fields",
        "reason": "unknown_request_fields",
        "error": "unknown_request_fields",
        "details": {"fields": ["dryrun"]},
    }
    assert svc._load() == before


@pytest.mark.asyncio
async def test_withdraw_all_execute_parses_canonical_dry_run_bool_strings(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

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
    execute = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": "true",
        },
    )

    assert execute["ok"] is True
    assert execute["result"]["status"] == "prepared"


@pytest.mark.asyncio
async def test_withdraw_all_execute_route_rejects_invalid_boolean_before_mutation(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(runtime._withdraw_all_service, "_token_balances", _fake_balances)
    runtime._withdraw_all_service.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    preview = await runtime._withdraw_all_service.preview(runtime)

    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/all/execute",
        headers={"X-Admin-Key": "secret"},
        json={
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": "definitely",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "status": "invalid",
        "reason_code": "invalid_boolean_value",
        "reason": "invalid_boolean_value",
        "error": "invalid_boolean_value",
        "details": {"field": "dry_run", "value": "definitely"},
    }


@pytest.mark.asyncio
async def test_withdraw_all_state_treats_non_hex_approved_destination_as_missing(tmp_path):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    svc._save({
        "enabled": True,
        "approved_destination": "0xgggggggggggggggggggggggggggggggggggggggg",
    })

    payload = await svc.state(runtime)

    assert payload["ok"] is True
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "approved_destination_missing"


def test_withdraw_all_preview_route_rejects_unknown_request_fields_before_preview(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    called = {"preview": False}

    async def _unexpected_preview(_runtime):
        called["preview"] = True
        return {"ok": True}

    monkeypatch.setattr(runtime._withdraw_all_service, "preview", _unexpected_preview)
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/all/preview",
        headers={"X-Admin-Key": "secret"},
        json={"dry_run": True},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["status"] == "invalid"
    assert body["reason_code"] == "unknown_request_fields"
    assert body["reason"] == "unknown_request_fields"
    assert body["error"] == "unknown_request_fields"
    assert body["details"] == {"fields": ["dry_run"]}
    assert body["summaryContract"]["truthFamily"] == "withdraw_all_preview"
    assert body["summaryContract"]["contractVersion"] == "canonical_summary_read_contract_v1"
    assert called["preview"] is False


def test_withdraw_all_preview_route_accepts_empty_object_body(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(runtime._withdraw_all_service, "_token_balances", _fake_balances)
    runtime._withdraw_all_service.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.post(
        "/api/withdraw/all/preview",
        headers={"X-Admin-Key": "secret"},
        json={},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["preview_id"]
    assert body["reason_code"] == "ok"
    assert isinstance(body["items"], list)


@pytest.mark.asyncio
async def test_withdraw_all_state_surfaces_persistence_load_failure_as_degraded(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return []

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    from pathlib import Path as _Path

    _Path(svc._path).write_text("{not-json", encoding="utf-8")

    payload = await svc.state(runtime)

    assert payload["ok"] is True
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "state_load_failed"
    assert payload["control_reason_code"] == "withdraw_all_disabled"
    assert payload["last_status"] == "degraded"
    assert payload["last_reason_code"] == "state_load_failed"


def test_withdraw_all_state_route_surfaces_persistence_load_failure_as_degraded(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return []

    monkeypatch.setattr(runtime._withdraw_all_service, "_token_balances", _fake_balances)
    from pathlib import Path as _Path

    _Path(runtime._withdraw_all_service._path).write_text("{not-json", encoding="utf-8")

    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    resp = client.get("/api/withdraw/all/state", headers={"X-Admin-Key": "secret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "degraded"
    assert body["reason_code"] == "state_load_failed"
    assert body["control_reason_code"] == "withdraw_all_disabled"


def test_withdraw_all_config_surfaces_persistence_save_failure_as_degraded(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    def _boom(_state):
        raise WithdrawAllPersistenceError("state_save_failed")

    monkeypatch.setattr(svc, "_save", _boom)

    payload = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )

    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "state_save_failed"
    assert payload["enabled"] is False
    assert payload["approved_destination"] == ""


@pytest.mark.asyncio
async def test_withdraw_all_preview_surfaces_persistence_save_failure_as_degraded(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    configured = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    assert configured["ok"] is True

    def _boom(_state):
        raise WithdrawAllPersistenceError("state_save_failed")

    monkeypatch.setattr(svc, "_save", _boom)

    payload = await svc.preview(runtime)

    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "state_save_failed"
    assert payload["preview_id"] == ""
    assert payload["approved_destination"] == "0x1111111111111111111111111111111111111111"
    assert isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_withdraw_all_execute_surfaces_persistence_save_failure_as_degraded(tmp_path, monkeypatch):
    runtime = _Runtime()
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

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

    def _boom(_state):
        raise WithdrawAllPersistenceError("state_save_failed")

    monkeypatch.setattr(svc, "_save", _boom)

    payload = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
            "dry_run": True,
        },
    )

    assert payload["ok"] is False
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == "state_save_failed"
    assert payload["attempted_status"] == "prepared"
    assert payload["attempted_reason_code"] == "ok"
    assert payload["attempted_preview_id"] == preview["preview_id"]
    assert payload["result_available"] is True
    assert payload["result_persisted"] is False
    assert payload["last_status"] == "preview_ready"
    assert payload["result"]["status"] == "prepared"


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



@pytest.mark.asyncio
async def test_withdraw_all_execute_invalid_private_key_env_is_blocked(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.withdraw_tokens = ["0x3333333333333333333333333333333333333333"]
    runtime.cfg.execution.withdraw_mode = "backend"
    runtime.cfg.execution.send_mode = "public"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    _install_fake_eth_account(monkeypatch, _InvalidKeyAccount)
    monkeypatch.setenv("TEST_KEY", "not-a-private-key")

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

    assert payload["ok"] is False
    assert payload["reason_code"] == "invalid_private_key_env"
    assert payload["result"]["reason_code"] == "invalid_private_key_env"
    assert payload["last_status"] == "execute_blocked"
    assert payload["last_reason_code"] == "invalid_private_key_env"

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


@pytest.mark.asyncio
async def test_withdraw_all_execute_blocks_when_private_key_is_not_executor_owner(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.withdraw_tokens = ["0x3333333333333333333333333333333333333333"]
    runtime.cfg.execution.withdraw_mode = "backend"
    runtime.cfg.execution.send_mode = "public"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _JsonRpcClientOwnerMismatch)
    _install_fake_eth_account(monkeypatch, _FakeAccount)
    monkeypatch.setenv("TEST_KEY", "0x" + ("11" * 32))

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

    assert payload["ok"] is False
    assert payload["reason_code"] == "executor_owner_mismatch"
    assert payload["result"] == {
        "ok": False,
        "reason_code": "executor_owner_mismatch",
        "private_key_env": "TEST_KEY",
        "signer_address": "0x3333333333333333333333333333333333333333",
        "executor_owner": "0x4444444444444444444444444444444444444444",
    }
    assert payload["last_status"] == "execute_blocked"
    assert payload["last_reason_code"] == "executor_owner_mismatch"


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

    async def block_number(self):
        return 123


async def _suggest_gas(*args, **kwargs):
    return 100, 2




@pytest.mark.asyncio
async def test_withdraw_all_execute_invalid_tx_hash_is_send_failed(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.withdraw_tokens = ["0x3333333333333333333333333333333333333333"]
    runtime.cfg.execution.withdraw_mode = "backend"
    runtime.cfg.execution.send_mode = "public"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _JsonRpcClientInvalidTxHash)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("TEST_KEY", "0x" + "11" * 32)

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

    assert payload["ok"] is False
    assert payload["reason_code"] == "send_failed"
    assert payload["result"]["reason_code"] == "send_failed"
    assert payload["last_status"] == "execute_failed"
    assert payload["last_reason_code"] == "send_failed"


@pytest.mark.asyncio
async def test_withdraw_all_execute_replay_preserves_failed_outcome(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.withdraw_tokens = ["0x3333333333333333333333333333333333333333"]
    runtime.cfg.execution.withdraw_mode = "backend"
    runtime.cfg.execution.send_mode = "public"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _JsonRpcClientSendFailure)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("TEST_KEY", "0x" + "11" * 32)

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
    first = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    replayed = await svc.execute(
        runtime,
        {
            "preview_id": preview["preview_id"],
            "confirm_text": "WITHDRAW EVERYTHING",
        },
    )

    assert first["ok"] is False
    assert first["reason_code"] == "send_failed"
    assert replayed["replayed"] is True
    assert replayed["ok"] is False
    assert replayed["reason_code"] == "send_failed"
    assert replayed["result"]["reason_code"] == "send_failed"

@pytest.mark.asyncio
async def test_withdraw_all_execute_send_failure_is_not_reported_as_completed(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.withdraw_tokens = ["0x3333333333333333333333333333333333333333"]
    runtime.cfg.execution.withdraw_mode = "backend"
    runtime.cfg.execution.send_mode = "public"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)
    monkeypatch.setattr(withdraw_all_service, "JsonRpcClient", _JsonRpcClientSendFailure)
    monkeypatch.setattr(withdraw_all_service, "suggest_gas", _suggest_gas)
    monkeypatch.setattr(withdraw_all_service, "build_withdraw_calldata", lambda **kwargs: "0xdeadbeef")
    _install_fake_eth_account(monkeypatch)
    monkeypatch.setenv("TEST_KEY", "0x" + "11" * 32)

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

    assert payload["ok"] is False
    assert payload["reason_code"] == "send_failed"
    assert payload["result"]["reason_code"] == "send_failed"
    assert payload["result"]["failed_item"]["token"] == "0x3333333333333333333333333333333333333333"
    assert payload["last_status"] == "execute_failed"
    assert payload["last_reason_code"] == "send_failed"
    assert payload["result"].get("status") != "completed"

    state = await svc.state(runtime)
    assert state["last_status"] == "execute_failed"
    assert state["last_reason_code"] == "send_failed"


@pytest.mark.asyncio
async def test_withdraw_all_state_surfaces_invalid_executor_address(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

    configured = svc.configure(
        runtime,
        {
            "destination": "0x1111111111111111111111111111111111111111",
            "enabled": True,
            "activate_destination": True,
        },
    )
    assert configured["ok"] is True

    state = await svc.state(runtime)

    assert state["ok"] is True
    assert state["status"] == "blocked"
    assert state["reason_code"] == "invalid_executor_address"


@pytest.mark.asyncio
async def test_withdraw_all_execute_blocks_invalid_executor_address(tmp_path, monkeypatch):
    runtime = _Runtime()
    runtime.cfg.execution.executor_address = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    svc = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": "0x3333333333333333333333333333333333333333", "balance": "250"}]

    monkeypatch.setattr(svc, "_token_balances", _fake_balances)

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
    assert preview["reason_code"] == "invalid_executor_address"
