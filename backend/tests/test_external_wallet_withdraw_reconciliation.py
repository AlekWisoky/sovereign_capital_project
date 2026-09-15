from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.server import app
import victor_ai_bot.withdraw_external as withdraw_external


TX_HASH = "0x" + "ab" * 32
FROM = "0x1111111111111111111111111111111111111111"
EXECUTOR = "0x2222222222222222222222222222222222222222"
DATA = "0x1234"


def _runtime():
    return SimpleNamespace(
        cfg=SimpleNamespace(
            chain=SimpleNamespace(chain_id=1),
            execution=SimpleNamespace(executor_address=EXECUTOR),
        ),
        rpc_manager=SimpleNamespace(best_read=lambda: "https://rpc.read"),
    )


def _payload(**overrides):
    from copy import deepcopy
    base = {
        "intent_id": "".join("0" for _ in range(64)),
        "tx_hash": TX_HASH,
        "chain_id": 1,
        "from_address": FROM,
        "to": EXECUTOR,
        "data": DATA,
        "value": "0x0",
    }
    base.update(overrides)
    canonical = {
        "chainId": "0x1",
        "data": DATA.lower(),
        "from": FROM.lower(),
        "to": EXECUTOR.lower(),
        "value": "0x0",
    }
    import hashlib
    import json
    base["intent_id"] = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return deepcopy(base)


class _PendingRpc:
    tx = None

    def __init__(self, url: str, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_tx_by_hash(self, tx_hash: str):
        return self.__class__.tx


async def _pending_status(*args, **kwargs):
    return SimpleNamespace(tx_status="pending", proof_reason="tx_not_visible", receipt_status=None, block_number=None, receipt=None)


async def _mined_status(*args, **kwargs):
    return SimpleNamespace(tx_status="mined_success", proof_reason="receipt_success", receipt_status=1, block_number=16, receipt={"status": "0x1", "blockNumber": "0x10"})


def _client(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    monkeypatch.setattr(app.state, "runtime", _runtime(), raising=False)
    return TestClient(app)


def test_external_reconcile_rejects_submitted_sender_mismatch(monkeypatch):
    client = _client(monkeypatch)
    _PendingRpc.tx = {
        "from": "0x3333333333333333333333333333333333333333",
        "to": EXECUTOR,
        "input": DATA,
        "value": "0x0",
        "chainId": "0x1",
    }
    monkeypatch.setattr(withdraw_external, "JsonRpcClient", _PendingRpc)
    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", _pending_status)
    response = client.post("/api/withdraw/external/reconcile", headers={"X-Admin-Key": "secret"}, json=_payload())
    assert response.status_code == 200
    assert response.json()["reason_code"] == "submitted_sender_mismatch"


def test_external_reconcile_rejects_chain_mismatch_before_rpc(monkeypatch):
    client = _client(monkeypatch)
    response = client.post(
        "/api/withdraw/external/reconcile",
        headers={"X-Admin-Key": "secret"},
        json=_payload(chain_id=2),
    )
    assert response.status_code == 200
    assert response.json()["reason_code"] == "chain_mismatch"


def test_external_reconcile_rejects_submitted_transaction_field_mismatch(monkeypatch):
    client = _client(monkeypatch)
    _PendingRpc.tx = {
        "from": FROM,
        "to": EXECUTOR,
        "input": "0xbeef",
        "value": "0x0",
        "chainId": "0x1",
    }
    monkeypatch.setattr(withdraw_external, "JsonRpcClient", _PendingRpc)
    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", _pending_status)
    response = client.post("/api/withdraw/external/reconcile", headers={"X-Admin-Key": "secret"}, json=_payload())
    assert response.status_code == 200
    assert response.json()["reason_code"] == "submitted_calldata_mismatch"


def test_external_reconcile_returns_pending_submission_evidence_when_transaction_not_visible(monkeypatch):
    client = _client(monkeypatch)
    _PendingRpc.tx = None
    monkeypatch.setattr(withdraw_external, "JsonRpcClient", _PendingRpc)
    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", _pending_status)
    response = client.post("/api/withdraw/external/reconcile", headers={"X-Admin-Key": "secret"}, json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["settled"] is False
    assert body["submission_evidence"] is True
    assert body["settlement_truth"] is False


def test_external_reconcile_exposes_receipt_truth_without_claiming_canonical_settlement(monkeypatch):
    client = _client(monkeypatch)
    _PendingRpc.tx = {
        "from": FROM,
        "to": EXECUTOR,
        "input": DATA,
        "value": "0x0",
        "chainId": "0x1",
    }
    monkeypatch.setattr(withdraw_external, "JsonRpcClient", _PendingRpc)
    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", _mined_status)
    response = client.post("/api/withdraw/external/reconcile", headers={"X-Admin-Key": "secret"}, json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "mined_success"
    assert body["settlement_truth"] is True
    assert body["settled"] is False
    assert body["submission_evidence"] is True
