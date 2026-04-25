from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from victor_ai_bot.server import app
from victor_ai_bot.runtime_services.withdraw_all_service import WithdrawAllService


class _Chain:
    name = "ethereum"
    chain_id = 1
    usdc = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    usdt = "0xcccccccccccccccccccccccccccccccccccccccc"


class _Execution:
    withdraw_allowlist = ["0x1111111111111111111111111111111111111111"]
    withdraw_tokens = ["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    executor_address = "0x2222222222222222222222222222222222222222"
    withdraw_mode = "backend"
    private_key_env = "VICTOR_PRIVATE_KEY"
    send_mode = "public"
    gas_mode = "standard"
    gas_presets = None
    gas_limit = 200000
    profit_to = "0x1111111111111111111111111111111111111111"


class _Cfg:
    chain = _Chain()
    execution = _Execution()


class _DegradedWithdrawRuntime:
    cfg = _Cfg()
    _cc = None
    rpc_manager = SimpleNamespace(
        best_read=lambda: "http://rpc.read",
        best_send=lambda: "http://rpc.send",
        best_private=lambda: "",
    )

    def capital_truth_state(self):
        return {
            "ok": True,
            "status": "degraded",
            "reason_code": "capital_truth_freshness_stale",
            "reason_codes": ["capital_truth_freshness_stale"],
            "status_reasons": ["capital_truth_freshness_stale"],
            "freshness": {
                "class": "stale",
                "reason_codes": ["capital_truth_freshness_stale"],
            },
            "withdrawal": {
                "available": False,
                "previewable": True,
                "reason_code": "capital_truth_freshness_stale",
                "reason_codes": ["capital_truth_freshness_stale"],
            },
            "categories": {"withdrawable_balance_wei": "100"},
        }


@pytest.mark.asyncio
async def test_withdraw_all_state_surfaces_capital_truth_health_and_withdraw_control(tmp_path, monkeypatch):
    runtime = _DegradedWithdrawRuntime()
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

    payload = await svc.state(runtime)

    assert payload["reason_code"] == "capital_truth_degraded"
    assert payload["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert payload["capitalTruthHealth"]["nextAction"] == "refresh_capital_truth_snapshot"
    assert payload["withdrawControl"]["status"] == "preview_only"
    assert payload["withdrawControl"]["reasonCode"] == "capital_truth_freshness_stale"
    assert payload["withdrawControl"]["actionReasonCode"] == "capital_truth_degraded"
    assert payload["withdrawControl"]["previewAvailable"] is True
    assert payload["withdrawControl"]["executeAvailable"] is False


def test_withdraw_all_state_route_surfaces_summary_contract_and_capital_truth_health(tmp_path, monkeypatch):
    runtime = _DegradedWithdrawRuntime()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=str(tmp_path), chain="ethereum")

    async def _fake_balances(runtime, tokens):
        return [{"token": tokens[0], "balance": "250"}]

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

    resp = client.get("/api/withdraw/all/state", headers={"X-Admin-Key": "secret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["summaryContract"]["truthFamily"] == "withdraw_all_state"
    assert body["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert body["withdrawControl"]["status"] == "preview_only"


def test_direct_withdraw_execute_blocks_on_capital_truth_freshness(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _DegradedWithdrawRuntime(), raising=False)
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
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["reason_code"] == "capital_truth_degraded"
    assert body["capital_truth_reason_code"] == "capital_truth_freshness_stale"
    assert body["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert body["withdrawControl"]["status"] == "preview_only"


def test_convert_withdraw_execute_blocks_on_capital_truth_freshness(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _DegradedWithdrawRuntime(), raising=False)
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
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["reason_code"] == "capital_truth_degraded"
    assert body["capital_truth_reason_code"] == "capital_truth_freshness_stale"
    assert body["capitalTruthHealth"]["freshnessClass"] == "stale"
    assert body["withdrawControl"]["status"] == "preview_only"
