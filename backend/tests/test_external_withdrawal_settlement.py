from types import SimpleNamespace

import pytest

from victor_ai_bot import withdraw_external
from victor_ai_bot.external_withdrawal_settlement import (
    CONVERT_WITHDRAW_SELECTOR,
    CONVERTED_EVENT_SIG,
    WITHDRAWAL_EVENT_SIG,
    WITHDRAW_SELECTOR,
    canonical_external_withdrawal_transaction,
    decode_external_withdrawal_effect,
    external_withdrawal_recipient,
)
from victor_ai_bot.abi_utils import topic0

SENDER = "0x" + "1" * 40
EXECUTOR = "0x" + "2" * 40
DESTINATION = "0x" + "3" * 40
TOKEN_IN = "0x" + "4" * 40
TOKEN_OUT = "0x" + "5" * 40
WITHDRAWAL_TOPIC0 = topic0(WITHDRAWAL_EVENT_SIG)
CONVERTED_TOPIC0 = topic0(CONVERTED_EVENT_SIG)


def _word(value: int) -> str:
    return f"{int(value):064x}"


def _topic_address(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def build_withdraw_calldata(token: str, destination: str, amount: int) -> str:
    return "0x" + WITHDRAW_SELECTOR + _word(int(token, 16)) + _word(int(destination, 16)) + _word(amount)


def build_convert_withdraw_calldata(
    token_in: str, token_out: str, amount_in: int, min_out: int, destination: str
) -> str:
    words = [
        int(token_in, 16),
        int(token_out, 16),
        amount_in,
        min_out,
        int(destination, 16),
        3000,
        0,
    ]
    return "0x" + CONVERT_WITHDRAW_SELECTOR + "".join(_word(word) for word in words)


def test_direct_withdrawal_recipient_is_decoded_from_calldata():
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, 1000)
    assert external_withdrawal_recipient(calldata) == DESTINATION.lower()


def test_convert_withdrawal_recipient_is_decoded_from_calldata():
    calldata = build_convert_withdraw_calldata(TOKEN_IN, TOKEN_OUT, 1000, 900, DESTINATION)
    assert external_withdrawal_recipient(calldata) == DESTINATION.lower()


def test_direct_withdrawal_receipt_event_is_exactly_proven():
    amount = 1000
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount)
    receipt = {
        "logs": [
            {
                "address": EXECUTOR,
                "topics": [WITHDRAWAL_TOPIC0, _topic_address(TOKEN_OUT), _topic_address(DESTINATION)],
                "data": "0x" + _word(amount),
            }
        ]
    }
    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect["ok"] is True
    assert effect["amount_out"] == str(amount)


def test_convert_withdrawal_uses_realized_event_amount_not_min_out():
    amount_in = 1000
    min_out = 900
    realized_out = 950
    calldata = build_convert_withdraw_calldata(TOKEN_IN, TOKEN_OUT, amount_in, min_out, DESTINATION)
    receipt = {
        "logs": [
            {
                "address": EXECUTOR,
                "topics": [
                    CONVERTED_TOPIC0,
                    _topic_address(TOKEN_IN),
                    _topic_address(TOKEN_OUT),
                    _topic_address(DESTINATION),
                ],
                "data": "0x" + _word(amount_in) + _word(realized_out),
            }
        ]
    }
    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect["ok"] is True
    assert effect["amount_out"] == str(realized_out)
    assert effect["min_out"] == str(min_out)


def test_success_without_matching_executor_event_is_not_settled():
    amount = 1000
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount)
    receipt = {"logs": []}
    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect == {"ok": False, "reason_code": "withdrawal_receipt_event_missing"}


def test_mismatched_event_cannot_settle():
    amount = 1000
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount)
    other_destination = "0x" + "6" * 40
    receipt = {
        "logs": [
            {
                "address": EXECUTOR,
                "topics": [WITHDRAWAL_TOPIC0, _topic_address(TOKEN_OUT), _topic_address(other_destination)],
                "data": "0x" + _word(amount),
            }
        ]
    }
    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect == {"ok": False, "reason_code": "withdrawal_receipt_event_missing"}


@pytest.mark.asyncio
async def test_reconcile_success_settles_to_calldata_recipient_and_is_idempotent(monkeypatch: pytest.MonkeyPatch):
    amount = 1000
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount)
    tx_hash = "0x" + "a" * 64
    chain_id = 1
    intent_id = withdraw_external._intent_digest(
        chain_id=chain_id, from_address=SENDER, to=EXECUTOR, data=calldata, value=0
    )
    receipt = {
        "logs": [
            {
                "address": EXECUTOR,
                "topics": [WITHDRAWAL_TOPIC0, _topic_address(TOKEN_OUT), _topic_address(DESTINATION)],
                "data": "0x" + _word(amount),
            }
        ]
    }

    class FakeRpc:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get_tx_by_hash(self, requested_hash):
            assert requested_hash == tx_hash
            return {
                "from": SENDER,
                "to": EXECUTOR,
                "input": calldata,
                "value": "0x0",
                "chainId": "0x1",
            }

    class FakeRepo:
        def __init__(self):
            self.payloads = []

        def append_receipt_idempotent(self, *, chain, payload):
            if any(existing["transaction_id"] == payload["transaction_id"] for existing in self.payloads):
                return False
            self.payloads.append(payload)
            return True

    repo = FakeRepo()
    runtime = SimpleNamespace(
        cfg=SimpleNamespace(
            chain=SimpleNamespace(chain_id=chain_id, name="ethereum"),
            execution=SimpleNamespace(executor_address=EXECUTOR),
        ),
        rpc_manager=SimpleNamespace(best_read=lambda: "https://rpc.example"),
        _ledger_repo=repo,
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(runtime=runtime)))
    status = SimpleNamespace(
        tx_status="mined_success",
        receipt_status=1,
        block_number=123,
        proof_reason="receipt_success",
        receipt=receipt,
    )

    monkeypatch.setattr(withdraw_external, "JsonRpcClient", lambda *args, **kwargs: FakeRpc())

    async def fake_assess(*args, **kwargs):
        return status

    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", fake_assess)
    monkeypatch.setattr(withdraw_external, "attach_summary_contract", lambda response, **kwargs: response)

    payload = {
        "intent_id": intent_id,
        "tx_hash": tx_hash,
        "chain_id": chain_id,
        "from_address": SENDER,
        "to": EXECUTOR,
        "data": calldata,
        "value": 0,
    }
    first = await withdraw_external.reconcile_external_withdraw(request, payload)
    second = await withdraw_external.reconcile_external_withdraw(request, payload)

    assert first["settled"] is True
    assert first["already_settled"] is False
    assert second["settled"] is True
    assert second["already_settled"] is True
    assert len(repo.payloads) == 1
    assert repo.payloads[0]["metadata"]["destination"] == DESTINATION
    assert repo.payloads[0]["metadata"]["destination"] != EXECUTOR
    assert first["settlement_transaction_id"] == second["settlement_transaction_id"]
    assert repo.payloads[0]["metadata"]["usd_value"] is None


def test_canonical_settlement_preserves_exact_asset_units_and_no_usd_value():
    amount = 12_345_678_901_234_567_890
    tx = canonical_external_withdrawal_transaction(
        chain="ethereum", receipt_id="0x" + "a" * 64, intent_id="b" * 64,
        from_address=SENDER, destination=DESTINATION,
        calldata=build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount),
        effect={
            "token_in": TOKEN_OUT, "token_out": TOKEN_OUT,
            "amount_in": str(amount), "amount_out": str(amount),
        },
        ts_ms=123,
    )

    assert tx["tx_type"] == "external_withdrawal_settlement"
    assert tx["metadata"]["destination"] == DESTINATION.lower()
    assert tx["metadata"]["amount_unit"] == "token_base_units"
    assert tx["metadata"]["usd_value"] is None
    assert sum(line["amount"] for line in tx["lines"]) == 0
