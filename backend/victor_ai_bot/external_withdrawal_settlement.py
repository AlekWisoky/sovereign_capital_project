from __future__ import annotations

from typing import Any, Dict, Mapping

from .abi_utils import topic0, selector

WITHDRAW_SIG = "withdraw(address,address,uint256)"
CONVERT_WITHDRAW_SIG = "convertAndWithdraw(address,address,uint256,uint256,address,uint24,uint256)"
WITHDRAWAL_EVENT_SIG = "Withdrawal(address,address,uint256)"
CONVERTED_EVENT_SIG = "ConvertedAndWithdrawn(address,address,uint256,uint256,address)"

WITHDRAW_SELECTOR = selector(WITHDRAW_SIG).hex()
CONVERT_WITHDRAW_SELECTOR = selector(CONVERT_WITHDRAW_SIG).hex()
WITHDRAWAL_TOPIC0 = topic0(WITHDRAWAL_EVENT_SIG)
CONVERTED_TOPIC0 = topic0(CONVERTED_EVENT_SIG)


def _hex_bytes(value: Any) -> bytes | None:
    text = str(value or "").strip()
    if not text.startswith("0x") or len(text) % 2:
        return None
    try:
        return bytes.fromhex(text[2:])
    except (TypeError, ValueError):
        return None


def _address(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("0x") and len(text) == 42:
        try:
            bytes.fromhex(text[2:])
            return text
        except (TypeError, ValueError):
            pass
    return ""


def _topic_address(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    if len(raw) != 64:
        return ""
    try:
        bytes.fromhex(raw)
    except (TypeError, ValueError):
        return ""
    return "0x" + raw[-40:]


def _uint_word(data: bytes, index: int) -> int | None:
    start = int(index) * 32
    end = start + 32
    if len(data) < end:
        return None
    return int.from_bytes(data[start:end], "big")


def _calldata_words(data: str, count: int) -> list[int] | None:
    raw = _hex_bytes(data)
    if raw is None or len(raw) < 4 + (32 * count):
        return None
    return [int.from_bytes(raw[4 + i * 32 : 4 + (i + 1) * 32], "big") for i in range(count)]


def _word_address(word: int) -> str:
    return "0x" + f"{int(word):064x}"[-40:]


def external_withdrawal_recipient(calldata: str) -> str:
    """Return the recipient encoded by a supported withdrawal calldata payload."""
    raw = _hex_bytes(calldata)
    if raw is None or len(raw) < 4:
        return ""
    selector_hex = raw[:4].hex()
    if selector_hex == WITHDRAW_SELECTOR:
        words = _calldata_words(calldata, 3)
        return _word_address(words[1]) if words is not None else ""
    if selector_hex == CONVERT_WITHDRAW_SELECTOR:
        words = _calldata_words(calldata, 7)
        return _word_address(words[4]) if words is not None else ""
    return ""


def _log_matches_withdrawal_destination(log: Mapping[str, Any], *, executor: str, destination: str) -> bool:
    if not isinstance(log, Mapping) or _address(log.get("address")) != executor:
        return False
    topics = log.get("topics")
    if not isinstance(topics, list) or not topics:
        return False
    topic = str(topics[0] or "").lower()
    if topic == WITHDRAWAL_TOPIC0.lower():
        return len(topics) >= 3 and _topic_address(topics[2]) == destination
    if topic == CONVERTED_TOPIC0.lower():
        return len(topics) >= 4 and _topic_address(topics[3]) == destination
    return False


def _matching_logs(receipt: Mapping[str, Any], *, executor: str, destination: str) -> list[Mapping[str, Any]]:
    logs = receipt.get("logs")
    if not isinstance(logs, list):
        return []
    executor_s = _address(executor)
    destination_s = _address(destination)
    return [
        log for log in logs
        if _log_matches_withdrawal_destination(log, executor=executor_s, destination=destination_s)
    ]


def _event_log(
    *, receipt: Mapping[str, Any], executor: str, destination: str,
    event_topic: str, destination_topic_index: int, missing_reason: str, ambiguous_reason: str,
) -> tuple[list[Any] | None, bytes | None, Dict[str, Any] | None]:
    matches = [
        log for log in _matching_logs(receipt, executor=executor, destination=destination)
        if str((log.get("topics") or [""])[0]).lower() == event_topic.lower()
    ]
    if len(matches) != 1:
        reason = ambiguous_reason if matches else missing_reason
        return None, None, {"ok": False, "reason_code": reason}
    topics = list(matches[0].get("topics") or [])
    if len(topics) <= destination_topic_index:
        return None, None, {"ok": False, "reason_code": missing_reason}
    data = _hex_bytes(str(matches[0].get("data") or "0x")) or b""
    return topics, data, None


def _withdrawal_inputs(calldata: str, destination: str, *, converted: bool) -> tuple[dict[str, Any] | None, Dict[str, Any] | None]:
    count = 7 if converted else 3
    words = _calldata_words(calldata, count)
    if words is None:
        reason = "invalid_convert_withdraw_calldata" if converted else "invalid_withdraw_calldata"
        return None, {"ok": False, "reason_code": reason}
    if converted:
        expected = {
            "token_in": _word_address(words[0]), "token_out": _word_address(words[1]),
            "amount_in": words[2], "min_out": words[3], "destination": _word_address(words[4]),
        }
        invalid_amount_reason = "invalid_convert_amount_in"
    else:
        expected = {"token": _word_address(words[0]), "destination": _word_address(words[1]), "amount": words[2]}
        invalid_amount_reason = "invalid_withdraw_amount"
    if expected["destination"] != destination:
        return None, {"ok": False, "reason_code": "calldata_destination_mismatch"}
    amount_in = expected["amount_in"] if converted else expected["amount"]
    if amount_in <= 0:
        return None, {"ok": False, "reason_code": invalid_amount_reason}
    return expected, None


def _withdrawal_event(
    *, receipt: Mapping[str, Any], executor: str, destination: str, converted: bool
) -> tuple[dict[str, Any] | None, Dict[str, Any] | None]:
    event_topic = CONVERTED_TOPIC0 if converted else WITHDRAWAL_TOPIC0
    destination_topic_index = 3 if converted else 2
    missing_reason = "convert_receipt_event_missing" if converted else "withdrawal_receipt_event_missing"
    ambiguous_reason = "ambiguous_convert_receipt_event" if converted else "ambiguous_withdrawal_receipt_event"
    topics, data, error = _event_log(
        receipt=receipt, executor=executor, destination=destination,
        event_topic=event_topic, destination_topic_index=destination_topic_index,
        missing_reason=missing_reason, ambiguous_reason=ambiguous_reason,
    )
    if error is not None:
        return None, error
    assert topics is not None and data is not None
    if converted:
        return {
            "token_in": _topic_address(topics[1]), "token_out": _topic_address(topics[2]),
            "amount_in": _uint_word(data, 0), "amount_out": _uint_word(data, 1),
        }, None
    return {"token": _topic_address(topics[1]), "amount": _uint_word(data, 0)}, None


def _build_effect(
    expected: Mapping[str, Any], event: Mapping[str, Any], *, converted: bool
) -> Dict[str, Any]:
    if converted:
        amount_out = event["amount_out"]
        valid = (
            event["token_in"] == expected["token_in"]
            and event["token_out"] == expected["token_out"]
            and event["amount_in"] == expected["amount_in"]
            and amount_out is not None
            and amount_out >= expected["min_out"]
            and amount_out > 0
        )
        if not valid:
            return {"ok": False, "reason_code": "convert_event_mismatch"}
        return {
            "ok": True, "kind": "convert_and_withdraw", "token": event["token_out"],
            "amount": str(amount_out), "amount_unit": "token_base_units",
            "token_in": event["token_in"], "token_out": event["token_out"],
            "amount_in": str(event["amount_in"]), "amount_out": str(amount_out),
            "min_out": str(expected["min_out"]),
        }

    if event["token"] != expected["token"] or event["amount"] != expected["amount"]:
        return {"ok": False, "reason_code": "withdrawal_event_mismatch"}
    amount = event["amount"]
    return {
        "ok": True, "kind": "withdraw", "token": event["token"],
        "amount": str(amount), "amount_unit": "token_base_units",
        "token_in": event["token"], "token_out": event["token"],
        "amount_in": str(amount), "amount_out": str(amount),
    }


def decode_external_withdrawal_effect(
    *, receipt: Mapping[str, Any], executor: str, calldata: str, destination: str
) -> Dict[str, Any]:
    """Prove the mined receipt contains exactly one executor withdrawal effect.

    The result is asset-unit only. No USD valuation is inferred from token amounts,
    wei, gas, or conversion limits.
    """
    executor_s = _address(executor)
    destination_s = _address(destination)
    if not executor_s or not destination_s:
        return {"ok": False, "reason_code": "invalid_settlement_identity"}
    raw_calldata = _hex_bytes(calldata)
    if raw_calldata is None or len(raw_calldata) < 4:
        return {"ok": False, "reason_code": "invalid_settlement_calldata"}
    selector_hex = raw_calldata[:4].hex()
    converted = selector_hex == CONVERT_WITHDRAW_SELECTOR
    if selector_hex not in {WITHDRAW_SELECTOR, CONVERT_WITHDRAW_SELECTOR}:
        return {"ok": False, "reason_code": "unsupported_withdrawal_calldata"}
    expected, error = _withdrawal_inputs(calldata, destination_s, converted=converted)
    if error is not None:
        return error
    event, error = _withdrawal_event(
        receipt=receipt, executor=executor_s, destination=destination_s, converted=converted
    )
    if error is not None:
        return error
    assert expected is not None and event is not None
    return _build_effect(expected, event, converted=converted)


def _external_withdrawal_lines(token: str, amount: int) -> list[Dict[str, Any]]:
    return [
        {"account": f"asset:{token}", "asset": token, "amount": -amount,
         "family": "", "venue": "WITHDRAW", "note": "external_withdrawal_settlement",
         "amount_raw": str(-amount)},
        {"account": "equity:external_withdrawal", "asset": token, "amount": amount,
         "family": "", "venue": "WITHDRAW", "note": "external_withdrawal_offset",
         "amount_raw": str(amount)},
    ]


def _external_withdrawal_metadata(
    *, intent_id: str, receipt_id: str, from_address: str, destination: str,
    calldata: str, token: str, effect: Mapping[str, Any], amount: int,
) -> Dict[str, Any]:
    return {
        "settlement_kind": "external_withdrawal", "settlement_status": "settled",
        "intent_id": str(intent_id), "tx_hash": str(receipt_id),
        "from_address": str(from_address).lower(), "destination": str(destination).lower(),
        "calldata": str(calldata).lower(), "token_in": str(effect.get("token_in") or "").lower(),
        "token_out": token, "amount_in_base_units": str(effect.get("amount_in") or ""),
        "amount_out_base_units": str(effect.get("amount_out") or amount),
        "amount_unit": "token_base_units", "usd_value": None, "usd_value_status": "unvalued",
    }


def canonical_external_withdrawal_transaction(
    *, chain: str, receipt_id: str, intent_id: str, from_address: str,
    destination: str, calldata: str, effect: Mapping[str, Any], ts_ms: int,
) -> Dict[str, Any]:
    token = _address(effect.get("token_out"))
    amount = int(str(effect.get("amount_out") or effect.get("amount") or "0"))
    if not token or amount <= 0:
        raise ValueError("invalid_external_withdrawal_effect")
    return {
        "transaction_id": f"external-withdrawal-{receipt_id.lower()}",
        "ts_ms": int(ts_ms), "tx_type": "external_withdrawal_settlement",
        "chain": str(chain or ""), "receipt_id": str(receipt_id),
        "lines": _external_withdrawal_lines(token, amount),
        "metadata": _external_withdrawal_metadata(
            intent_id=intent_id, receipt_id=receipt_id, from_address=from_address,
            destination=destination, calldata=calldata, token=token,
            effect=effect, amount=amount,
        ),
    }
