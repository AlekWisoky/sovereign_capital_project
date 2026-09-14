from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import victor_ai_bot.api_routes.withdraw_external_routes as external_routes


FROM = "0x1111111111111111111111111111111111111111"
TO = "0x2222222222222222222222222222222222222222"
DATA = "0xdeadbeef"
VALUE = "0x0"
TX_HASH = "0x" + "ab" * 32


def _intent_id():
    return external_routes._intent_digest(
        chain_id=1,
        from_address=FROM,
        to=TO,
        data=DATA,
        value=VALUE,
    )


class _Rpc:
    tx = {
        "from": FROM,
        "to": TO,
        "input": DATA,
        "value": VALUE,
        "chainId": "0x1",
    }
    receipt = None

    def __init__(self, url: str, **kwargs):
        self.url = url

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get_tx_by_hash(self, tx_hash):
        return self.__class__.tx

    async def call(self, method, params=None):
        if method == "eth_getTransactionReceipt":
            return SimpleNamespace(ok=True, result=self.__class__.receipt)
        return SimpleNamespace(ok=False, error="unsupported")


class _Runtime:
    cfg = SimpleNamespace(
        chain=SimpleNamespace(chain_id=1),
        execution=SimpleNamespace(public_allow_broadcast=False),
    )
    rpc_manager = SimpleNamespace(best_read=lambda self: "https://rpc.read")


def _client(monkeypatch, receipt=None, tx=None):
    app = FastAPI()
    app.state.runtime = _Runtime()
    monkeypatch.setattr(external_routes, "JsonRpcClient", _Rpc)
    _Rpc.receipt = receipt
    _Rpc.tx = tx
    app.include_router(external_routes.router)
    return TestClient(app)


def _payload(**overrides):
    body = {
        "intent_id": _intent_id(),
        "tx_hash": TX_HASH,
        "chain_id": 1,
        "from_address": FROM,
        "to": TO,
        "data": DATA,
        "value": VALUE,
    }
    body.update(overrides)
    return body


def test_reconcile_pending_is_submission_evidence_not_settlement(monkeypatch):
    client = _client(monkeypatch, receipt=None)
    response = client.post("/api/withdraw/external/reconcile", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["status"] == "pending"
    assert body["submission_evidence"] is True
    assert body["settlement_truth"] is False
    assert body["settled"] is False


def test_reconcile_mined_success_reports_receipt_truth_but_not_settlement(monkeypatch):
    client = _client(monkeypatch, receipt={"status": "0x1", "blockNumber": "0x10"})
    response = client.post("/api/withdraw/external/reconcile", json=_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "mined_success"
    assert body["receipt_status"] == 1
    assert body["settlement_truth"] is True
    assert body["settled"] is False
    assert body["canonical_receipt"]["status"] == "0x1"


def test_reconcile_rejects_sender_mismatch(monkeypatch):
    client = _client(
        monkeypatch,
        receipt=None,
        tx={
            "from": "0x3333333333333333333333333333333333333333",
            "to": TO,
            "input": DATA,
            "value": VALUE,
            "chainId": "0x1",
        },
    )
    response = client.post("/api/withdraw/external/reconcile", json=_payload())
    assert response.status_code == 200
    assert response.json()["reason_code"] == "submitted_sender_mismatch"


def test_reconcile_rejects_calldata_mismatch(monkeypatch):
    client = _client(
        monkeypatch,
        receipt=None,
        tx={"from": FROM, "to": TO, "input": "0xcafebabe", "value": VALUE, "chainId": "0x1"},
    )
    response = client.post("/api/withdraw/external/reconcile", json=_payload())
    assert response.status_code == 200
    assert response.json()["reason_code"] == "submitted_calldata_mismatch"


def test_reconcile_rejects_intent_mismatch(monkeypatch):
    client = _client(monkeypatch, receipt=None)
    response = client.post("/api/withdraw/external/reconcile", json=_payload(intent_id="0" * 64))
    assert response.status_code == 200
    assert response.json()["reason_code"] == "intent_mismatch"
