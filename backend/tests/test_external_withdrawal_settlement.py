from types import SimpleNamespace

import pytest

import victor_ai_bot.withdraw_external as withdraw_external
from victor_ai_bot.external_withdrawal_settlement import (
    CONVERTED_TOPIC0,
    WITHDRAWAL_TOPIC0,
    canonical_external_withdrawal_transaction,
    decode_external_withdrawal_effect,
    external_withdrawal_recipient,
)
from victor_ai_bot.withdraw_builder import build_convert_and_withdraw_calldata, build_withdraw_calldata


EXECUTOR = "0x1111111111111111111111111111111111111111"
SENDER = "0x2222222222222222222222222222222222222222"
TOKEN_IN = "0x3333333333333333333333333333333333333333"
TOKEN_OUT = "0x4444444444444444444444444444444444444444"
DESTINATION = "0x5555555555555555555555555555555555555555"


def _topic_address(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def _word(value: int) -> str:
    return f"{int(value):064x}"


def test_direct_withdrawal_recipient_is_decoded_from_calldata():
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, 1000)
    assert EXECUTOR != DESTINATION
    assert external_withdrawal_recipient(calldata) == DESTINATION


def test_convert_withdrawal_recipient_is_decoded_from_calldata():
    calldata = build_convert_and_withdraw_calldata(
        TOKEN_IN, TOKEN_OUT, 2_000_000, 1_500_000, DESTINATION, 3000, 2_000_000_000
    )
    assert EXECUTOR != DESTINATION
    assert external_withdrawal_recipient(calldata) == DESTINATION


def test_direct_withdrawal_receipt_event_is_exactly_proven():
    amount = 1_234_567_890_123_456_789
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
    assert effect["token_out"] == TOKEN_OUT
    assert effect["amount_out"] == str(amount)


def test_convert_withdrawal_uses_realized_event_amount_not_min_out():
    amount_in = 2_000_000
    min_out = 1_500_000
    amount_out = 1_750_321
    calldata = build_convert_and_withdraw_calldata(
        TOKEN_IN, TOKEN_OUT, amount_in, min_out, DESTINATION, 3000, 2_000_000_000
    )
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
                "data": "0x" + _word(amount_in) + _word(amount_out),
            }
        ]
    }

    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )

    assert effect["ok"] is True
    assert effect["amount_out"] == str(amount_out)
    assert effect["amount_out"] != str(min_out)


def test_success_without_matching_executor_event_is_not_settled():
    amount = 1000
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, amount)
    receipt = {
        "logs": [
            {
                "address": "0x9999999999999999999999999999999999999999",
                "topics": [WITHDRAWAL_TOPIC0, _topic_address(TOKEN_OUT), _topic_address(DESTINATION)],
                "data": "0x" + _word(amount),
            }
        ]
    }

    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect == {"ok": False, "reason_code": "withdrawal_receipt_event_missing"}


def test_mismatched_event_cannot_settle():
    calldata = build_withdraw_calldata(TOKEN_OUT, DESTINATION, 1000)
    receipt = {
        "logs": [
            {
                "address": EXECUTOR,
                "topics": [WITHDRAWAL_TOPIC0, _topic_address(TOKEN_OUT), _topic_address(DESTINATION)],
                "data": "0x" + _word(999),
            }
        ]
    }
    effect = decode_external_withdrawal_effect(
        receipt=receipt, executor=EXECUTOR, calldata=calldata, destination=DESTINATION
    )
    assert effect == {"ok": False, "reason_code": "withdrawal_event_mismatch"}


def test_reconcile_success_settles_to_calldata_recipient_and_is_idempotent(monkeypatch: pytest.MonkeyPatch):
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
            self.payloads.append(payload)
            return len(self.payloads) == 1

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
    monkeypatch.setattr(withdraw_external, "assess_submitted_tx", lambda *args, **kwargs: status)
    monkeypatch.setattr(withdraw_external, "attach_summary_contract", lambda response, **kwargs: response)

    first = await withdraw_external.reconcile_external_withdraw(request, {
        "intent_id": intent_id,
        "tx_hash": tx_hash,
        "chain_id": chain_id,
        "from_address": SENDER,
        "to": EXECUTOR,
        "data": calldata,
        "value": 0,
    })
    second = await withdraw_external.reconcile_external_withdraw(request, {
        "intent_id": intent_id,
        "tx_hash": tx_hash,
        "chain_id": chain_id,
        "from_address": SENDER,
        "to": EXECUTOR,
        "data": calldata,
        "value": 0,
    })

    assert first["settled"] is True
    assert first["already_settled"] is False
    assert second["settled"] is True
    assert second["already_settled"] is True
    assert len(repo.payloads) == 2
    assert repo.payloads[0]["metadata"]["destination"] == DESTINATION
    assert repo.payloads[0]["metadata"]["destination"] != EXECUTOR
    assert repo.payloads[0]["transaction_id"] == repo.payloads[1]["transaction_id"]


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
    assert tx["receipt_id"] == "0x" + "a" * 64
    assert tx["lines"][0]["amount"] == -amount
    assert tx["lines"][0]["amount_raw"] == str(-amount)
    assert tx["lines"][1]["amount"] == amount
    assert tx["metadata"]["amount_out_base_units"] == str(amount)
    assert tx["metadata"]["usd_value"] is None
    assert tx["metadata"]["usd_value_status"] == "unvalued"
