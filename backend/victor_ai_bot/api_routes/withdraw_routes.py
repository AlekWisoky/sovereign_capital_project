from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, Request

from ..auth import require_admin
from ..deploy_mode import is_public_mode
from ..executor_owner import validate_executor_owner_proof
from ..gas import suggest_gas
from ..jsonsafe import to_json_safe as json_safe
from ..offramp_tx_status import submitted_tx_status_payload
from ..tx_confirmation import SubmittedTxStatus, assess_submitted_tx
from ..quote_univ3 import quote_exact_input_single
from ..rpc import JsonRpcClient
from ..withdraw_builder import build_convert_and_withdraw_calldata, build_withdraw_calldata
from ..runtime_services.withdraw_control_contract import build_withdraw_control_view
from ..runtime_services.withdraw_ledger_service import record_withdraw_lifecycle_event
from ._route_helpers import (
    attach_summary_contract,
    append_optional_audit,
    invalid_request_payload,
    unexpected_request_fields,
)

router = APIRouter(tags=["withdraw"])


@dataclass(frozen=True)
class WithdrawRpcPlan:
    read_url: str
    send_url: str


_INVALID_REASONS = {
    "invalid_numeric",
    "invalid_amount",
    "missing_token",
    "missing_destination",
    "invalid_token",
    "invalid_destination",
    "invalid_fee_tiers",
    "invalid_slippage_bps",
    "invalid_fee",
    "invalid_min_out",
    "invalid_deadline",
    "invalid_from_address",
}
_UNAVAILABLE_REASONS = {
    "stable_not_configured",
    "executor_not_configured",
    "no_rpc_endpoints",
    "quoter_not_configured",
    "invalid_quoter_address",
    "missing_private_key_env",
    "invalid_private_key_env",
    "withdraw_all_service_unavailable",
    "invalid_executor_address",
    "executor_owner_lookup_failed",
}
_BLOCKED_REASONS = {
    "dest_not_in_allowlist",
    "withdraw_execute_disabled_in_public_mode",
    "withdraw_mode_not_backend",
    "executor_owner_mismatch",
}
_DEGRADED_REASONS = {"send_failed", "quote_failed", "receipt_reverted"}
_MAX_UNISWAP_V3_FEE = (1 << 24) - 1


def _reject(reason: str, *, status: str | None = None, **extra: Any) -> Dict[str, Any]:
    reason_code = str(reason)
    resolved = status or _status_for_reason(reason_code)
    return {
        "ok": False,
        "status": resolved,
        "reason_code": reason_code,
        "reason": reason_code,
        "error": reason_code,
        **extra,
    }


def _reject_unknown_fields(
    payload: Dict[str, Any], *, allowed_fields: set[str] | frozenset[str]
) -> Dict[str, Any] | None:
    unexpected = unexpected_request_fields(payload, allowed_fields=allowed_fields)
    if not unexpected:
        return None
    return invalid_request_payload("unknown_request_fields", details={"fields": unexpected})


async def _preview_request_body_error(request: Request) -> Dict[str, Any] | None:
    raw = await request.body()
    if not raw or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return invalid_request_payload("unexpected_request_body")
    if payload == {}:
        return None
    if isinstance(payload, dict):
        return invalid_request_payload(
            "unknown_request_fields", details={"fields": sorted(str(key) for key in payload.keys())}
        )
    return invalid_request_payload("unexpected_request_body")


def _status_for_reason(reason_code: str) -> str:
    if reason_code in _INVALID_REASONS:
        return "invalid"
    if reason_code in _UNAVAILABLE_REASONS:
        return "unavailable"
    if reason_code in _BLOCKED_REASONS:
        return "blocked"
    if reason_code in _DEGRADED_REASONS:
        return "degraded"
    return "degraded"


def _runtime_cfg(request: Request):
    return request.app.state.runtime.cfg  # type: ignore[attr-defined]


def _runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


def _withdraw_control_projection(request: Request) -> Dict[str, Any]:
    runtime = _runtime(request)
    truth_method = getattr(runtime, "capital_truth_state", None)
    truth: Dict[str, Any] = {}
    if callable(truth_method):
        try:
            raw = truth_method()
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            raw = {}
        if isinstance(raw, dict):
            truth = dict(raw)
    return build_withdraw_control_view(runtime, capital_truth=truth)


def _resolve_stable(cfg: Any, token_out: str) -> str:
    token = str(token_out or "").strip()
    if not token:
        return ""
    if token.lower() == "usdc":
        return str(getattr(cfg.chain, "usdc", "") or "")
    if token.lower() == "usdt":
        return str(getattr(cfg.chain, "usdt", "") or "")
    return token


def _normalize_requested_token_out(raw_token_out: Any) -> str:
    requested = str(raw_token_out if raw_token_out is not None else "USDC" or "USDC").strip()
    return requested or "USDC"


def _resolve_convert_token_out(cfg: Any, raw_token_out: Any) -> tuple[str | None, str]:
    requested = _normalize_requested_token_out(raw_token_out)

    if requested.lower() in {"usdc", "usdt"}:
        resolved = _resolve_stable(cfg, requested)
        if not resolved or not _is_evm_address(resolved):
            return "stable_not_configured", ""
        return None, resolved

    if not _is_evm_address(requested):
        return "invalid_token", ""
    return None, requested


def _convert_token_out_context(*, token_in: str = "", token_out_requested: str) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "token_out_requested": str(token_out_requested),
        "requested_token_out": str(token_out_requested),
    }
    if str(token_in or "").strip():
        payload["token_in"] = str(token_in)
    return payload


def _convert_quote_context(
    *,
    token_in: str = "",
    token_out_requested: str,
    amount_in: Any | None = None,
    fee_tiers: Any | None = None,
    slippage_bps: Any | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = _convert_token_out_context(
        token_in=token_in,
        token_out_requested=token_out_requested,
    )
    if amount_in is not None and str(amount_in or "").strip():
        payload["amount_in"] = str(amount_in)
    if fee_tiers is not None:
        payload["fee_tiers"] = fee_tiers
    if slippage_bps is not None:
        payload["slippage_bps"] = slippage_bps
    return payload


def _is_evm_address(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return False
    try:
        bytes.fromhex(text[2:])
    except (TypeError, ValueError):
        return False
    return True


def _allowlisted_destination(cfg: Any, to: str) -> bool:
    allow = [str(a).lower() for a in (getattr(cfg.execution, "withdraw_allowlist", []) or [])]
    return not allow or str(to or "").lower() in set(allow)


def _executor_address(cfg: Any) -> str:
    return str(getattr(cfg.execution, "executor_address", "") or "")


def _parse_int(raw: Any, *, reason: str) -> int:
    text = str(raw or "0")
    try:
        return int(text, 0) if text.startswith("0x") else int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc


def _parse_strict_int_like(raw: Any, *, reason: str) -> int:
    if isinstance(raw, bool):
        raise ValueError(reason)
    if isinstance(raw, int):
        return int(raw)
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValueError(reason)
        return int(raw)
    text = str(raw or "")
    try:
        return int(text, 0) if text.startswith("0x") else int(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc


def _is_tx_hash(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) != 66 or not text.startswith("0x"):
        return False
    try:
        bytes.fromhex(text[2:])
    except (TypeError, ValueError):
        return False
    return True


def _extract_tx_hash(value: Any) -> str | None:
    txh = value
    if isinstance(txh, dict):
        txh = txh.get("txHash") or txh.get("hash") or txh.get("result")
    if not isinstance(txh, str):
        return None
    txh = txh.strip()
    if not _is_tx_hash(txh):
        return None
    return txh


def _submitted_tx_hash(result: Any) -> str | None:
    if result is None:
        return None
    if isinstance(result, dict):
        ok_flag = result.get("ok")
        payload = result.get("result", result)
    else:
        ok_flag = getattr(result, "ok", None)
        payload = getattr(result, "result", result)
    if ok_flag is False:
        return None
    return _extract_tx_hash(payload)


def _execute_response_payload(
    *,
    tx_hash: str,
    from_addr: str,
    tx_result: SubmittedTxStatus,
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "ok": True,
        "status": str(tx_result.tx_status),
        "tx_hash": tx_hash,
        "from": from_addr,
        "from_address": from_addr,
        **dict(extra),
        **submitted_tx_status_payload(tx_result),
    }
    return payload


def _success_execute_response(
    request: Request,
    *,
    event: str,
    action_reason: str,
    tx_hash: str,
    from_addr: str,
    tx_result: SubmittedTxStatus,
    extra: Dict[str, Any],
):
    response = _execute_response_payload(
        tx_hash=tx_hash,
        from_addr=from_addr,
        tx_result=tx_result,
        extra=extra,
    )
    _append_withdraw_audit(
        request,
        event=event,
        reason=action_reason,
        payload={
            "outcome": str(tx_result.tx_status),
            **response,
        },
    )
    return json_safe(response)


def _optional_action_reason(action_reason: str) -> Dict[str, Any]:
    return {"action_reason": action_reason} if str(action_reason or "").strip() else {}


def _execute_request_context(
    *,
    to: str,
    executor: str,
    from_addr: str | None = None,
    **extra: Any,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"to": to, "executor": executor}
    if str(from_addr or "").strip():
        payload["from_address"] = str(from_addr)
    payload.update(dict(extra))
    return payload


def _bound_execute_request_context(
    *,
    to: str,
    executor: str,
    **base_extra: Any,
):
    def build(
        *,
        from_addr: str | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload = dict(base_extra)
        payload.update(dict(extra))
        return _execute_request_context(
            to=to,
            executor=executor,
            from_addr=from_addr,
            **payload,
        )

    return build


def _bound_request_context(**base: Any):
    def build(**extra: Any) -> Dict[str, Any]:
        payload = dict(base)
        payload.update(dict(extra))
        return payload

    return build


def _bound_convert_request_context(
    *,
    token_in: str = "",
    token_out_requested: str,
    **base: Any,
):
    return _bound_request_context(
        **base,
        **_convert_token_out_context(
            token_in=token_in,
            token_out_requested=token_out_requested,
        ),
    )


def _bound_direct_request_context(
    *,
    token: str = "",
    **base: Any,
):
    return _bound_request_context(
        **base,
        token=token,
    )


def _bound_convert_quote_context(
    *,
    token_in: str = "",
    token_out_requested: str,
):
    build_base = _bound_convert_request_context(
        token_in=token_in,
        token_out_requested=token_out_requested,
    )

    def build(
        *,
        amount_in: Any | None = None,
        fee_tiers: Any | None = None,
        slippage_bps: Any | None = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        payload = build_base(**extra)
        if amount_in is not None and str(amount_in or "").strip():
            payload["amount_in"] = str(amount_in)
        if fee_tiers is not None:
            payload["fee_tiers"] = fee_tiers
        if slippage_bps is not None:
            payload["slippage_bps"] = slippage_bps
        return payload

    return build


def _bound_control_reject(
    request: Request,
    *,
    event: str,
    action_reason: str,
):
    def reject(
        reason_code: str,
        *,
        audit_payload: Dict[str, Any] | None = None,
        **extra: Any,
    ):
        return _control_reject_response(
            request,
            event=event,
            action_reason=action_reason,
            reason_code=reason_code,
            audit_payload=audit_payload,
            **extra,
        )

    return reject


def _bound_execute_outcomes(
    request: Request,
    *,
    event: str,
    action_reason: str,
):
    def send_failed(*, audit_payload: Dict[str, Any]):
        return _send_failed_response(
            request,
            event=event,
            action_reason=action_reason,
            audit_payload=audit_payload,
        )

    def receipt_reverted(
        *,
        tx_hash: str,
        from_addr: str,
        tx_result: SubmittedTxStatus,
        reject_payload: Dict[str, Any],
    ):
        return _receipt_reverted_response(
            request,
            event=event,
            action_reason=action_reason,
            tx_hash=tx_hash,
            from_addr=from_addr,
            tx_result=tx_result,
            reject_payload=reject_payload,
        )

    def success(
        *,
        tx_hash: str,
        from_addr: str,
        tx_result: SubmittedTxStatus,
        extra: Dict[str, Any],
    ):
        return _success_execute_response(
            request,
            event=event,
            action_reason=action_reason,
            tx_hash=tx_hash,
            from_addr=from_addr,
            tx_result=tx_result,
            extra=extra,
        )

    return send_failed, receipt_reverted, success


async def _send_signed_withdraw_tx(*, rpc_r: Any, rpc_s: Any, send_mode: str, raw: str) -> Any:
    normalized_send_mode = str(send_mode or "public").strip().lower()
    if normalized_send_mode == "private":
        current_block = await rpc_r.block_number() or 0
        return await rpc_s.send_private_tx(raw, max_block_number=current_block + 2)
    return await rpc_s.send_raw_tx(raw)


def _append_withdraw_audit(
    request: Request,
    *,
    event: str,
    reason: str,
    payload: Dict[str, Any],
) -> bool:
    runtime = _runtime(request)
    audited = append_optional_audit(
        getattr(getattr(runtime, "_cc", None), "audit", None),
        event,
        payload,
        actor="operator",
        reason=str(reason or ""),
    )
    record_withdraw_lifecycle_event(
        runtime,
        event=str(event or ""),
        reason=str(reason or ""),
        payload=dict(payload or {}),
    )
    return audited


def _control_reject_response(
    request: Request,
    *,
    event: str,
    action_reason: str,
    reason_code: str,
    audit_payload: Dict[str, Any] | None = None,
    **extra: Any,
):
    payload: Dict[str, Any] = {"outcome": str(reason_code or "")}
    normalized_audit_payload: Dict[str, Any] = {}
    normalized_extra: Dict[str, Any] = {}
    if audit_payload:
        normalized_audit_payload = dict(audit_payload)
        payload.update(normalized_audit_payload)
    if extra:
        normalized_extra = dict(extra)
        payload.update(normalized_extra)
    _append_withdraw_audit(
        request,
        event=event,
        reason=action_reason,
        payload=payload,
    )
    response = _reject(reason_code, **_optional_action_reason(action_reason))
    response.update(normalized_audit_payload)
    response.update(normalized_extra)
    from_addr = str(response.get("from_address", "") or "")
    if from_addr and "from" not in response:
        response["from"] = from_addr
    return json_safe(response)


def _send_failed_response(
    request: Request,
    *,
    event: str,
    action_reason: str,
    audit_payload: Dict[str, Any],
):
    payload = dict(audit_payload)
    from_addr = str(payload.get("from_address", "") or "")
    if from_addr and "from" not in payload:
        payload["from"] = from_addr
    _append_withdraw_audit(
        request,
        event=event,
        reason=action_reason,
        payload={"outcome": "send_failed", **payload},
    )
    reject_extra: Dict[str, Any] = dict(payload)
    reject_extra.update(_optional_action_reason(action_reason))
    return json_safe(_reject("send_failed", **reject_extra))


def _receipt_reverted_response(
    request: Request,
    *,
    event: str,
    action_reason: str,
    tx_hash: str,
    from_addr: str,
    tx_result: SubmittedTxStatus,
    reject_payload: Dict[str, Any],
):
    tx_status_payload = submitted_tx_status_payload(tx_result)
    _append_withdraw_audit(
        request,
        event=event,
        reason=action_reason,
        payload={
            "outcome": "receipt_reverted",
            "tx_hash": tx_hash,
            "from_address": from_addr,
            "from": from_addr,
            **dict(reject_payload),
            **tx_status_payload,
        },
    )
    reject_extra: Dict[str, Any] = {
        "tx_hash": tx_hash,
        "from_address": from_addr,
        "from": from_addr,
        **dict(reject_payload),
        **tx_status_payload,
    }
    if action_reason:
        reject_extra["action_reason"] = action_reason
    return json_safe(_reject("receipt_reverted", **reject_extra))


def _withdraw_rpc_plan(request: Request) -> WithdrawRpcPlan | None:
    runtime = _runtime(request)
    cfg = runtime.cfg
    read_url = runtime.rpc_manager.best_read()
    send_url = runtime.rpc_manager.best_send()
    if str(getattr(cfg.execution, "send_mode", "public")) in {"private", "protected_rpc"}:
        send_url = runtime.rpc_manager.best_private() or send_url
    if not read_url or not send_url:
        return None
    return WithdrawRpcPlan(read_url=str(read_url), send_url=str(send_url))


def _backend_execution_signer_address(cfg: Any) -> str | None:
    if str(getattr(cfg.execution, "withdraw_mode", "txdata") or "txdata") != "backend":
        return None
    key_env = str(
        getattr(cfg.execution, "private_key_env", "VICTOR_PRIVATE_KEY") or "VICTOR_PRIVATE_KEY"
    )
    key_hex = os.environ.get(key_env, "").strip()
    if not key_hex:
        return None
    try:
        from eth_account import Account

        acct = Account.from_key(key_hex)
    except (ImportError, AttributeError, TypeError, ValueError):
        return None
    address = str(getattr(acct, "address", "") or "")
    return address if _is_evm_address(address) else None


@router.get("/api/withdraw/config")
async def withdraw_config(request: Request):
    cfg = _runtime_cfg(request)
    ex = getattr(cfg, "execution", None)
    payload = {
        "ok": True,
        "chain": getattr(cfg.chain, "name", ""),
        "chain_id": int(getattr(cfg.chain, "chain_id", 0) or 0),
        "executor_address": str(getattr(ex, "executor_address", "") or ""),
        "withdraw_mode": str(getattr(ex, "withdraw_mode", "txdata") or "txdata"),
        "allowlist": list(getattr(ex, "withdraw_allowlist", []) or []),
        "tokens": list(getattr(ex, "withdraw_tokens", []) or []),
        "stables": {
            "usdc": str(getattr(cfg.chain, "usdc", "") or ""),
            "usdt": str(getattr(cfg.chain, "usdt", "") or ""),
        },
        "profit_to": str(getattr(ex, "profit_to", "") or ""),
    }
    return json_safe(
        attach_summary_contract(
            payload,
            family="withdraw_config",
            read_model="withdraw_config_projection_v1",
            runtime=_runtime(request),
        )
    )


@router.post("/api/withdraw/convert/prepare", dependencies=[Depends(require_admin)])
async def convert_withdraw_prepare(request: Request, payload: Dict[str, Any] = Body(...)):
    unknown = _reject_unknown_fields(
        payload,
        allowed_fields={
            "token_in",
            "token_out",
            "to",
            "from_address",
            "amount_in",
            "amount",
            "min_out",
            "fee",
            "deadline",
            "reason",
        },
    )
    if unknown is not None:
        return json_safe(unknown)

    action_reason = str(payload.get("reason", "") or "").strip()
    reject = _bound_control_reject(
        request,
        event="convert_withdraw_prepare",
        action_reason=action_reason,
    )

    cfg = _runtime_cfg(request)
    token_in = str(payload.get("token_in", "") or "")
    token_out_requested = _normalize_requested_token_out(payload.get("token_out", "USDC"))
    token_out_reason, token_out = _resolve_convert_token_out(cfg, token_out_requested)
    to = str(payload.get("to", "") or "")
    requested_from_addr = str(payload.get("from_address", "") or "")
    build_prepare_context = _bound_convert_request_context(
        to=to,
        token_in=token_in,
        token_out_requested=token_out_requested,
    )

    if not to:
        return reject(
            "missing_destination",
            audit_payload=build_prepare_context(),
        )
    if not _is_evm_address(to):
        return reject(
            "invalid_destination",
            audit_payload=build_prepare_context(),
        )
    if not _allowlisted_destination(cfg, to):
        return reject(
            "dest_not_in_allowlist",
            audit_payload=build_prepare_context(token_in=token_in),
        )
    if not token_in:
        return reject(
            "missing_token",
            audit_payload=build_prepare_context(token_in=""),
        )
    if not _is_evm_address(token_in):
        return reject(
            "invalid_token",
            audit_payload=build_prepare_context(token_in=token_in),
        )
    if requested_from_addr and not _is_evm_address(requested_from_addr):
        return reject(
            "invalid_from_address",
            audit_payload=build_prepare_context(
                token_in=token_in, from_address=requested_from_addr
            ),
        )
    if token_out_reason:
        return reject(
            token_out_reason,
            audit_payload=build_prepare_context(
                token_in=token_in, requested_token_out=token_out_requested
            ),
        )
    executor = _executor_address(cfg)
    if not executor:
        return reject(
            "executor_not_configured",
            audit_payload=build_prepare_context(token_in=token_in),
        )
    if not _is_evm_address(executor):
        return reject(
            "invalid_executor_address",
            audit_payload=build_prepare_context(executor=executor, token_in=token_in),
        )
    execution_from_addr = _backend_execution_signer_address(cfg)
    estimate_from_addr = execution_from_addr or requested_from_addr or ""

    try:
        amount_in = _parse_int(
            payload.get("amount_in", payload.get("amount", "0")), reason="invalid_numeric"
        )
        min_out = _parse_int(payload.get("min_out", "0"), reason="invalid_numeric")
        fee = _parse_int(payload.get("fee", "3000"), reason="invalid_numeric")
        deadline = _parse_int(payload.get("deadline", ""), reason="invalid_numeric")
    except ValueError as exc:
        return reject(
            str(exc),
            audit_payload=build_prepare_context(
                executor=executor,
                token_in=token_in,
                amount_in=str(payload.get("amount_in", payload.get("amount", "0")) or ""),
                min_out=str(payload.get("min_out", "0") or ""),
                fee=str(payload.get("fee", "3000") or ""),
                deadline=str(payload.get("deadline", "") or ""),
            ),
        )

    prepare_context = build_prepare_context(
        executor=executor,
        token_in=token_in,
        token_out=token_out,
        amount_in=str(amount_in),
        min_out=str(min_out),
        fee=str(fee),
        deadline=int(deadline),
    )

    if amount_in <= 0:
        return reject(
            "invalid_amount",
            audit_payload=prepare_context,
        )
    if min_out < 0:
        return reject(
            "invalid_min_out",
            audit_payload=prepare_context,
        )
    if fee <= 0 or fee > _MAX_UNISWAP_V3_FEE:
        return reject(
            "invalid_fee",
            audit_payload=prepare_context,
        )
    if "deadline" in payload:
        if deadline <= 0:
            return reject(
                "invalid_deadline",
                audit_payload=prepare_context,
            )
    elif deadline <= 0:
        deadline = int(time.time()) + 300

    late_prepare_context = build_prepare_context(
        executor=executor,
        token_in=token_in,
        token_out=token_out,
        amount_in=str(amount_in),
        min_out=str(min_out),
        fee=str(fee),
        deadline=int(deadline),
        from_address=estimate_from_addr,
        requested_from_address=requested_from_addr,
        execution_from_address=execution_from_addr,
    )

    calldata = build_convert_and_withdraw_calldata(
        token_in=token_in,
        token_out=token_out,
        amount_in=int(amount_in),
        min_out=int(min_out),
        to=to,
        fee=int(fee),
        deadline=int(deadline),
    )

    runtime = _runtime(request)
    read_url = runtime.rpc_manager.best_read()
    if not read_url:
        return reject(
            "no_rpc_endpoints",
            audit_payload=late_prepare_context,
        )

    async with JsonRpcClient(read_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc_r:
        max_fee, prio = await suggest_gas(
            rpc_r,
            mode=str(getattr(cfg.execution, "gas_mode", "standard")),
            presets=getattr(cfg.execution, "gas_presets", None),
        )
        gas_limit = int(getattr(cfg.execution, "gas_limit", 250_000) or 250_000)
        nonce = None
        if estimate_from_addr:
            tx_for_est = {
                "to": executor,
                "from": estimate_from_addr,
                "data": calldata,
                "value": hex(0),
            }
            try:
                est = await rpc_r.estimate_gas(tx_for_est)
                if est is not None:
                    gas_limit = max(gas_limit, int(est) + 30_000)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            try:
                nonce = await rpc_r.get_nonce(estimate_from_addr)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                nonce = None

    return json_safe(
        {
            "ok": True,
            "to": to,
            "executor": executor,
            "from_address": estimate_from_addr or None,
            "requested_from_address": requested_from_addr or None,
            "execution_from_address": execution_from_addr or None,
            "token_in": token_in,
            "token_out_requested": token_out_requested,
            "requested_token_out": token_out_requested,
            "token_out": token_out,
            "amount_in": str(amount_in),
            "min_out": str(min_out),
            "fee": str(fee),
            "deadline": int(deadline),
            "tx": {
                "to": executor,
                "data": calldata,
                "value": hex(0),
                "chainId": int(getattr(cfg.chain, "chain_id", 0) or 0),
            },
            "suggested": {
                "gas_limit": int(gas_limit),
                "max_fee_wei": str(int(max_fee)),
                "priority_fee_wei": str(int(prio)),
                "nonce": int(nonce) if nonce is not None else None,
                "deadline": int(deadline),
                "fee": int(fee),
                "token_out": str(token_out),
            },
        }
    )


@router.post("/api/withdraw/convert/quote", dependencies=[Depends(require_admin)])
async def convert_withdraw_quote(request: Request, payload: Dict[str, Any] = Body(...)):
    unknown = _reject_unknown_fields(
        payload,
        allowed_fields={
            "token_in",
            "token_out",
            "amount_in",
            "amount",
            "fee_tiers",
            "slippage_bps",
        },
    )
    if unknown is not None:
        return json_safe(unknown)

    action_reason = ""
    reject = _bound_control_reject(
        request,
        event="convert_withdraw_quote",
        action_reason=action_reason,
    )

    cfg = _runtime_cfg(request)
    token_in = str(payload.get("token_in", "") or "")
    token_out_requested = _normalize_requested_token_out(payload.get("token_out", "USDC"))
    token_out_reason, token_out = _resolve_convert_token_out(cfg, token_out_requested)

    quote_context = _bound_convert_quote_context(
        token_in=token_in,
        token_out_requested=token_out_requested,
    )

    if not token_in:
        return reject("missing_token", audit_payload=quote_context())
    if not _is_evm_address(token_in):
        return reject("invalid_token", audit_payload=quote_context())
    if token_out_reason:
        return reject(token_out_reason, audit_payload=quote_context())

    try:
        amount_in = _parse_int(
            payload.get("amount_in", payload.get("amount", "0")), reason="invalid_amount"
        )
    except ValueError as exc:
        return reject(
            str(exc),
            audit_payload=quote_context(
                amount_in=str(payload.get("amount_in", payload.get("amount", "0")) or "")
            ),
        )
    if amount_in <= 0:
        return reject(
            "invalid_amount",
            audit_payload=quote_context(amount_in=str(amount_in)),
        )

    raw_fee_tiers = payload.get("fee_tiers")
    if raw_fee_tiers is None:
        tiers: List[int] = [500, 3000, 10000]
    else:
        if not isinstance(raw_fee_tiers, list) or not raw_fee_tiers:
            return reject(
                "invalid_fee_tiers",
                audit_payload=quote_context(amount_in=str(amount_in), fee_tiers=raw_fee_tiers),
                details={"field": "fee_tiers"},
            )
        tiers = []
        for idx, value in enumerate(raw_fee_tiers):
            if isinstance(value, bool):
                return reject(
                    "invalid_fee_tiers",
                    audit_payload=quote_context(amount_in=str(amount_in), fee_tiers=raw_fee_tiers),
                    details={"field": "fee_tiers", "index": idx},
                )
            try:
                tier = _parse_strict_int_like(value, reason="invalid_fee_tiers")
            except ValueError:
                return reject(
                    "invalid_fee_tiers",
                    audit_payload=quote_context(amount_in=str(amount_in), fee_tiers=raw_fee_tiers),
                    details={"field": "fee_tiers", "index": idx},
                )
            if tier <= 0 or tier > _MAX_UNISWAP_V3_FEE:
                return reject(
                    "invalid_fee_tiers",
                    audit_payload=quote_context(amount_in=str(amount_in), fee_tiers=raw_fee_tiers),
                    details={"field": "fee_tiers", "index": idx},
                )
            tiers.append(tier)
        tiers = sorted(set(tiers))

    slip_bps = payload.get("slippage_bps")
    if slip_bps is None:
        safety_cfg = getattr(cfg, "safety", None)
        try:
            slippage_bps = int(getattr(safety_cfg, "slippage_bps", 50) or 50)
        except (AttributeError, TypeError, ValueError):
            slippage_bps = 50
        slippage_bps = max(0, min(2000, slippage_bps))
    else:
        if isinstance(slip_bps, bool):
            return reject(
                "invalid_slippage_bps",
                audit_payload=quote_context(
                    amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=slip_bps
                ),
                details={"field": "slippage_bps"},
            )
        try:
            slippage_bps = _parse_strict_int_like(slip_bps, reason="invalid_slippage_bps")
        except ValueError:
            return reject(
                "invalid_slippage_bps",
                audit_payload=quote_context(
                    amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=slip_bps
                ),
                details={"field": "slippage_bps"},
            )
        if slippage_bps < 0 or slippage_bps > 2000:
            return reject(
                "invalid_slippage_bps",
                audit_payload=quote_context(
                    amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=slip_bps
                ),
                details={"field": "slippage_bps"},
            )

    quoter = str(getattr(cfg.chain, "univ3_quoter_v2", "") or "")
    if not quoter:
        return reject(
            "quoter_not_configured",
            audit_payload=quote_context(
                amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=int(slippage_bps)
            ),
        )
    if not _is_evm_address(quoter):
        return reject(
            "invalid_quoter_address",
            audit_payload=quote_context(
                amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=int(slippage_bps)
            ),
        )

    runtime = _runtime(request)
    read_url = runtime.rpc_manager.best_read()
    if not read_url:
        return reject(
            "no_rpc_endpoints",
            audit_payload=quote_context(
                amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=int(slippage_bps)
            ),
        )

    best_fee = int(sorted(set(int(t) for t in tiers))[0])
    best_out = 0
    async with JsonRpcClient(read_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc_r:
        for fee in sorted(set(int(t) for t in tiers)):
            try:
                quote = await quote_exact_input_single(
                    rpc_r, quoter, token_in, token_out, int(fee), int(amount_in), block="latest"
                )
            except (AttributeError, RuntimeError, TypeError, ValueError):
                quote = None
            if quote is None:
                continue
            amount_out = int(getattr(quote, "amount_out", 0) or 0)
            if amount_out > best_out or (amount_out == best_out and int(fee) < best_fee):
                best_out = amount_out
                best_fee = int(fee)

    if best_out <= 0:
        return reject(
            "quote_failed",
            audit_payload=quote_context(
                amount_in=str(amount_in), fee_tiers=tiers, slippage_bps=int(slippage_bps)
            ),
        )

    min_out = best_out - (best_out * slippage_bps // 10_000)
    return json_safe(
        {
            "ok": True,
            "token_in": str(token_in),
            "amount_in": str(amount_in),
            "token_out_requested": token_out_requested,
            "requested_token_out": token_out_requested,
            "token_out": str(token_out),
            "expected_out": str(best_out),
            "min_out": str(max(0, int(min_out))),
            "fee": int(best_fee),
            "fee_tiers": [int(t) for t in sorted(set(int(t) for t in tiers))],
            "slippage_bps": int(slippage_bps),
        }
    )


@router.post("/api/withdraw/convert/execute", dependencies=[Depends(require_admin)])
async def convert_withdraw_execute(request: Request, payload: Dict[str, Any] = Body(...)):
    unknown = _reject_unknown_fields(
        payload,
        allowed_fields={
            "token_in",
            "token_out",
            "to",
            "amount_in",
            "amount",
            "min_out",
            "fee",
            "deadline",
            "reason",
        },
    )
    if unknown is not None:
        return json_safe(unknown)

    action_reason = str(payload.get("reason", "") or "").strip()
    reject = _bound_control_reject(
        request,
        event="convert_withdraw_execute",
        action_reason=action_reason,
    )
    send_failed, receipt_reverted, success = _bound_execute_outcomes(
        request,
        event="convert_withdraw_execute",
        action_reason=action_reason,
    )

    if is_public_mode():
        return reject(
            "withdraw_execute_disabled_in_public_mode",
        )

    cfg = _runtime_cfg(request)
    if str(getattr(cfg.execution, "withdraw_mode", "txdata")) != "backend":
        return reject(
            "withdraw_mode_not_backend",
        )

    token_in = str(payload.get("token_in", "") or "")
    token_out_requested = _normalize_requested_token_out(payload.get("token_out", "USDC"))
    token_out_reason, token_out = _resolve_convert_token_out(cfg, token_out_requested)
    to = str(payload.get("to", "") or "")
    build_pre_sign_context = _bound_convert_request_context(
        to=to,
        token_in=token_in,
        token_out_requested=token_out_requested,
    )

    if not to:
        return reject(
            "missing_destination",
            audit_payload=build_pre_sign_context(),
        )
    if not _is_evm_address(to):
        return reject(
            "invalid_destination",
            audit_payload=build_pre_sign_context(),
        )
    if not _allowlisted_destination(cfg, to):
        return reject(
            "dest_not_in_allowlist",
            audit_payload=build_pre_sign_context(),
        )
    if not token_in:
        return reject(
            "missing_token",
            audit_payload=build_pre_sign_context(token_in=""),
        )
    if not _is_evm_address(token_in):
        return reject(
            "invalid_token",
            audit_payload=build_pre_sign_context(token_in=token_in),
        )
    if token_out_reason:
        return reject(
            token_out_reason,
            audit_payload=build_pre_sign_context(
                **_convert_token_out_context(
                    token_in=token_in, token_out_requested=token_out_requested
                )
            ),
        )
    executor = _executor_address(cfg)
    if not executor:
        return reject(
            "executor_not_configured",
            audit_payload=build_pre_sign_context(token_in=token_in),
        )
    if not _is_evm_address(executor):
        return reject(
            "invalid_executor_address",
            audit_payload=build_pre_sign_context(executor=executor, token_in=token_in),
        )

    try:
        amount_in = _parse_int(
            payload.get("amount_in", payload.get("amount", "0")), reason="invalid_numeric"
        )
        min_out = _parse_int(payload.get("min_out", "0"), reason="invalid_numeric")
        fee = _parse_int(payload.get("fee", "3000"), reason="invalid_numeric")
        deadline = _parse_int(payload.get("deadline", ""), reason="invalid_numeric")
    except ValueError as exc:
        return reject(
            str(exc),
            audit_payload=build_pre_sign_context(
                executor=executor,
                token_in=token_in,
                amount_in=str(payload.get("amount_in", payload.get("amount", "0")) or ""),
                min_out=str(payload.get("min_out", "0") or ""),
                fee=str(payload.get("fee", "3000") or ""),
                deadline=str(payload.get("deadline", "") or ""),
            ),
        )

    build_execute_context = _bound_execute_request_context(
        to=to,
        executor=executor,
        token_in=token_in,
        token_out_requested=token_out_requested,
        requested_token_out=token_out_requested,
        token_out=token_out,
    )

    execute_context = build_execute_context(
        amount_in=str(amount_in),
        min_out=str(min_out),
        fee=str(fee),
        deadline=int(deadline),
    )

    if amount_in <= 0:
        return reject(
            "invalid_amount",
            audit_payload=execute_context,
        )
    if min_out < 0:
        return reject(
            "invalid_min_out",
            audit_payload=execute_context,
        )
    if fee <= 0 or fee > _MAX_UNISWAP_V3_FEE:
        return reject(
            "invalid_fee",
            audit_payload=execute_context,
        )
    if "deadline" in payload:
        if deadline <= 0:
            return reject(
                "invalid_deadline",
                audit_payload=execute_context,
            )
    elif deadline <= 0:
        deadline = int(time.time()) + 300

    execute_context["deadline"] = int(deadline)

    withdraw_control = _withdraw_control_projection(request)
    if not bool(withdraw_control.get("executeAvailable")):
        return reject(
            str(withdraw_control.get("actionReasonCode") or "capital_truth_degraded"),
            audit_payload={
                **execute_context,
                "capital_truth_reason_code": str(withdraw_control.get("reasonCode") or ""),
                "capital_truth_reason_codes": list(withdraw_control.get("reasonCodes") or []),
            },
            capital_truth_reason_code=str(withdraw_control.get("reasonCode") or ""),
            capital_truth_reason_codes=list(withdraw_control.get("reasonCodes") or []),
            capitalTruthHealth=dict(withdraw_control.get("capitalTruthHealth") or {}),
            withdrawControl=withdraw_control,
        )

    from eth_account import Account

    key_env = str(
        getattr(cfg.execution, "private_key_env", "VICTOR_PRIVATE_KEY") or "VICTOR_PRIVATE_KEY"
    )
    key_hex = os.environ.get(key_env, "").strip()
    if not key_hex:
        return reject(
            "missing_private_key_env",
            audit_payload=execute_context,
            private_key_env=key_env,
        )

    try:
        acct = Account.from_key(key_hex)
    except (TypeError, ValueError):
        return reject(
            "invalid_private_key_env",
            audit_payload=execute_context,
            private_key_env=key_env,
        )
    from_addr = acct.address
    calldata = build_convert_and_withdraw_calldata(
        token_in=token_in,
        token_out=token_out,
        amount_in=int(amount_in),
        min_out=int(min_out),
        to=to,
        fee=int(fee),
        deadline=int(deadline),
    )
    signed_context = build_execute_context(
        from_addr=from_addr,
        amount_in=str(amount_in),
        min_out=str(min_out),
        fee=str(fee),
        deadline=int(deadline),
    )

    rpc_plan = _withdraw_rpc_plan(request)
    if rpc_plan is None:
        return reject(
            "no_rpc_endpoints",
            audit_payload=signed_context,
        )

    async with (
        JsonRpcClient(rpc_plan.read_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc_r,
        JsonRpcClient(rpc_plan.send_url, timeout_s=10.0, max_concurrency=5, max_batch=10) as rpc_s,
    ):
        owner_reason, executor_owner = await validate_executor_owner_proof(
            rpc_r, executor_address=executor, signer_address=from_addr
        )
        if owner_reason is not None:
            return reject(
                owner_reason,
                audit_payload=signed_context,
                private_key_env=key_env,
                signer_address=from_addr,
                executor_owner=executor_owner or "",
            )

        max_fee, prio = await suggest_gas(
            rpc_r,
            mode=str(getattr(cfg.execution, "gas_mode", "standard")),
            presets=getattr(cfg.execution, "gas_presets", None),
        )
        nonce = await rpc_r.get_nonce(from_addr)
        gas_limit = int(getattr(cfg.execution, "gas_limit", 250_000) or 250_000)
        try:
            est = await rpc_r.estimate_gas(
                {"to": executor, "from": from_addr, "data": calldata, "value": hex(0)}
            )
            if est is not None:
                gas_limit = max(gas_limit, int(est) + 30_000)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        tx = {
            "chainId": int(getattr(cfg.chain, "chain_id", 0) or 0),
            "to": executor,
            "nonce": int(nonce),
            "data": calldata,
            "value": 0,
            "gas": int(gas_limit),
            "maxFeePerGas": int(max_fee),
            "maxPriorityFeePerGas": int(prio),
            "type": 2,
        }
        signed = Account.sign_transaction(tx, key_hex)
        raw_bytes = getattr(signed, "rawTransaction", None) or getattr(
            signed, "raw_transaction", None
        )
        raw = raw_bytes.hex() if raw_bytes is not None else ""
        raw = raw if raw.startswith("0x") else ("0x" + raw)

        try:
            result = await _send_signed_withdraw_tx(
                rpc_r=rpc_r,
                rpc_s=rpc_s,
                send_mode=str(getattr(cfg.execution, "send_mode", "public") or "public"),
                raw=raw,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return send_failed(
                audit_payload=signed_context,
            )

        tx_hash = _submitted_tx_hash(result)
        if tx_hash is None:
            return send_failed(
                audit_payload=signed_context,
            )

        tx_result = await assess_submitted_tx(
            rpc_r,
            tx_hash=tx_hash,
            send_mode=str(getattr(cfg.execution, "send_mode", "public") or "public"),
        )
        if tx_result.tx_status == "mined_reverted":
            return receipt_reverted(
                tx_hash=tx_hash,
                from_addr=from_addr,
                tx_result=tx_result,
                reject_payload=execute_context,
            )

        extra = dict(execute_context)
        if action_reason:
            extra["action_reason"] = action_reason
        return success(
            tx_hash=tx_hash,
            from_addr=from_addr,
            tx_result=tx_result,
            extra=extra,
        )


@router.post("/api/withdraw/prepare", dependencies=[Depends(require_admin)])
async def withdraw_prepare(request: Request, payload: Dict[str, Any] = Body(...)):
    unknown = _reject_unknown_fields(
        payload, allowed_fields={"token", "to", "from_address", "amount"}
    )
    if unknown is not None:
        return json_safe(unknown)

    action_reason = ""
    reject = _bound_control_reject(
        request,
        event="withdraw_prepare",
        action_reason=action_reason,
    )

    cfg = _runtime_cfg(request)
    token = str(payload.get("token", "") or "")
    to = str(payload.get("to", "") or "")
    requested_from_addr = str(payload.get("from_address", "") or "")
    build_prepare_context = _bound_direct_request_context(
        to=to,
        token=token,
    )

    if not to:
        return reject(
            "missing_destination",
            audit_payload=build_prepare_context(),
        )
    if not _is_evm_address(to):
        return reject(
            "invalid_destination",
            audit_payload=build_prepare_context(),
        )
    if not _allowlisted_destination(cfg, to):
        return reject(
            "dest_not_in_allowlist",
            audit_payload=build_prepare_context(token=token),
        )
    if not token:
        return reject(
            "missing_token",
            audit_payload=build_prepare_context(token=""),
        )
    if not _is_evm_address(token):
        return reject(
            "invalid_token",
            audit_payload=build_prepare_context(token=token),
        )
    if requested_from_addr and not _is_evm_address(requested_from_addr):
        return reject(
            "invalid_from_address",
            audit_payload=build_prepare_context(token=token, from_address=requested_from_addr),
        )
    executor = _executor_address(cfg)
    if not executor:
        return reject(
            "executor_not_configured",
            audit_payload=build_prepare_context(token=token),
        )
    if not _is_evm_address(executor):
        return reject(
            "invalid_executor_address",
            audit_payload=build_prepare_context(executor=executor, token=token),
        )
    execution_from_addr = _backend_execution_signer_address(cfg)
    estimate_from_addr = execution_from_addr or requested_from_addr or ""

    try:
        amount = _parse_int(payload.get("amount", "0"), reason="invalid_amount")
    except ValueError as exc:
        return reject(
            str(exc),
            audit_payload=build_prepare_context(
                executor=executor, token=token, amount=str(payload.get("amount", "0") or "")
            ),
        )
    prepare_context = build_prepare_context(
        executor=executor,
        token=token,
        amount=str(amount),
        from_address=estimate_from_addr,
        requested_from_address=requested_from_addr,
        execution_from_address=execution_from_addr,
    )
    if amount <= 0:
        return reject(
            "invalid_amount",
            audit_payload=prepare_context,
        )

    calldata = build_withdraw_calldata(token=token, to=to, amount=amount)
    rpc_plan = _withdraw_rpc_plan(request)
    if rpc_plan is None:
        return reject(
            "no_rpc_endpoints",
            audit_payload=prepare_context,
        )

    async with JsonRpcClient(
        rpc_plan.read_url, timeout_s=10.0, max_concurrency=10, max_batch=20
    ) as rpc_r:
        max_fee, prio = await suggest_gas(
            rpc_r,
            mode=str(getattr(cfg.execution, "gas_mode", "standard")),
            presets=getattr(cfg.execution, "gas_presets", None),
        )
        gas_limit = int(getattr(cfg.execution, "gas_limit", 200_000) or 200_000)
        nonce = None
        if estimate_from_addr:
            tx_for_est = {
                "to": executor,
                "from": estimate_from_addr,
                "data": calldata,
                "value": hex(0),
            }
            try:
                est = await rpc_r.estimate_gas(tx_for_est)
                if est is not None:
                    gas_limit = max(gas_limit, int(est) + 20_000)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
            try:
                nonce = await rpc_r.get_nonce(estimate_from_addr)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                nonce = None

    return json_safe(
        {
            "ok": True,
            "to": to,
            "executor": executor,
            "from_address": estimate_from_addr or None,
            "requested_from_address": requested_from_addr or None,
            "execution_from_address": execution_from_addr or None,
            "token": token,
            "amount": str(amount),
            "tx": {
                "to": executor,
                "data": calldata,
                "value": hex(0),
                "chainId": int(getattr(cfg.chain, "chain_id", 0) or 0),
            },
            "suggested": {
                "gas_limit": int(gas_limit),
                "max_fee_wei": str(int(max_fee)),
                "priority_fee_wei": str(int(prio)),
                "nonce": int(nonce) if nonce is not None else None,
            },
        }
    )


@router.post("/api/withdraw/execute", dependencies=[Depends(require_admin)])
async def withdraw_execute(request: Request, payload: Dict[str, Any] = Body(...)):
    unknown = _reject_unknown_fields(payload, allowed_fields={"token", "to", "amount", "reason"})
    if unknown is not None:
        return json_safe(unknown)

    action_reason = str(payload.get("reason", "") or "").strip()
    reject = _bound_control_reject(
        request,
        event="withdraw_execute",
        action_reason=action_reason,
    )
    send_failed, receipt_reverted, success = _bound_execute_outcomes(
        request,
        event="withdraw_execute",
        action_reason=action_reason,
    )

    if is_public_mode():
        return reject(
            "withdraw_execute_disabled_in_public_mode",
        )

    cfg = _runtime_cfg(request)
    if str(getattr(cfg.execution, "withdraw_mode", "txdata")) != "backend":
        return reject(
            "withdraw_mode_not_backend",
        )

    token = str(payload.get("token", "") or "")
    to = str(payload.get("to", "") or "")
    build_pre_sign_context = _bound_direct_request_context(to=to, token=token)
    if not to:
        return reject(
            "missing_destination",
            audit_payload=build_pre_sign_context(),
        )
    if not _is_evm_address(to):
        return reject(
            "invalid_destination",
            audit_payload=build_pre_sign_context(),
        )
    if not _allowlisted_destination(cfg, to):
        return reject(
            "dest_not_in_allowlist",
            audit_payload=build_pre_sign_context(),
        )
    if not token:
        return reject(
            "missing_token",
            audit_payload=build_pre_sign_context(),
        )
    if not _is_evm_address(token):
        return reject(
            "invalid_token",
            audit_payload=build_pre_sign_context(token=token),
        )
    executor = _executor_address(cfg)
    if not executor:
        return reject(
            "executor_not_configured",
            audit_payload=build_pre_sign_context(token=token),
        )
    if not _is_evm_address(executor):
        return reject(
            "invalid_executor_address",
            audit_payload=build_pre_sign_context(executor=executor, token=token),
        )

    try:
        amount = _parse_int(payload.get("amount", "0"), reason="invalid_amount")
    except ValueError as exc:
        return reject(
            str(exc),
            audit_payload=build_pre_sign_context(
                executor=executor,
                token=token,
                amount=str(payload.get("amount", "0") or ""),
            ),
        )

    build_execute_context = _bound_execute_request_context(
        to=to,
        executor=executor,
        token=token,
    )

    execute_context = build_execute_context(
        amount=str(amount),
    )

    if amount <= 0:
        return reject(
            "invalid_amount",
            audit_payload=execute_context,
        )

    withdraw_control = _withdraw_control_projection(request)
    if not bool(withdraw_control.get("executeAvailable")):
        return reject(
            str(withdraw_control.get("actionReasonCode") or "capital_truth_degraded"),
            audit_payload={
                **execute_context,
                "capital_truth_reason_code": str(withdraw_control.get("reasonCode") or ""),
                "capital_truth_reason_codes": list(withdraw_control.get("reasonCodes") or []),
            },
            capital_truth_reason_code=str(withdraw_control.get("reasonCode") or ""),
            capital_truth_reason_codes=list(withdraw_control.get("reasonCodes") or []),
            capitalTruthHealth=dict(withdraw_control.get("capitalTruthHealth") or {}),
            withdrawControl=withdraw_control,
        )

    from eth_account import Account

    key_env = str(
        getattr(cfg.execution, "private_key_env", "VICTOR_PRIVATE_KEY") or "VICTOR_PRIVATE_KEY"
    )
    key_hex = os.environ.get(key_env, "").strip()
    if not key_hex:
        return reject(
            "missing_private_key_env",
            audit_payload=execute_context,
            private_key_env=key_env,
        )

    try:
        acct = Account.from_key(key_hex)
    except (TypeError, ValueError):
        return reject(
            "invalid_private_key_env",
            audit_payload=execute_context,
            private_key_env=key_env,
        )
    from_addr = acct.address
    calldata = build_withdraw_calldata(token=token, to=to, amount=amount)
    signed_context = build_execute_context(
        from_addr=from_addr,
        amount=str(amount),
    )
    rpc_plan = _withdraw_rpc_plan(request)
    if rpc_plan is None:
        return reject(
            "no_rpc_endpoints",
            audit_payload=signed_context,
        )

    async with (
        JsonRpcClient(rpc_plan.read_url, timeout_s=10.0, max_concurrency=10, max_batch=20) as rpc_r,
        JsonRpcClient(rpc_plan.send_url, timeout_s=10.0, max_concurrency=5, max_batch=10) as rpc_s,
    ):
        owner_reason, executor_owner = await validate_executor_owner_proof(
            rpc_r, executor_address=executor, signer_address=from_addr
        )
        if owner_reason is not None:
            return reject(
                owner_reason,
                audit_payload=signed_context,
                private_key_env=key_env,
                signer_address=from_addr,
                executor_owner=executor_owner or "",
            )

        max_fee, prio = await suggest_gas(
            rpc_r,
            mode=str(getattr(cfg.execution, "gas_mode", "standard")),
            presets=getattr(cfg.execution, "gas_presets", None),
        )
        nonce = await rpc_r.get_nonce(from_addr)
        gas_limit = int(getattr(cfg.execution, "gas_limit", 200_000) or 200_000)
        try:
            est = await rpc_r.estimate_gas(
                {"to": executor, "from": from_addr, "data": calldata, "value": hex(0)}
            )
            if est is not None:
                gas_limit = max(gas_limit, int(est) + 20_000)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        tx = {
            "chainId": int(getattr(cfg.chain, "chain_id", 0) or 0),
            "to": executor,
            "nonce": int(nonce),
            "data": calldata,
            "value": 0,
            "gas": int(gas_limit),
            "maxFeePerGas": int(max_fee),
            "maxPriorityFeePerGas": int(prio),
            "type": 2,
        }
        signed = Account.sign_transaction(tx, key_hex)
        raw_bytes = getattr(signed, "rawTransaction", None) or getattr(
            signed, "raw_transaction", None
        )
        raw = raw_bytes.hex() if raw_bytes is not None else ""
        raw = raw if raw.startswith("0x") else ("0x" + raw)

        try:
            result = await _send_signed_withdraw_tx(
                rpc_r=rpc_r,
                rpc_s=rpc_s,
                send_mode=str(getattr(cfg.execution, "send_mode", "public") or "public"),
                raw=raw,
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return send_failed(
                audit_payload=signed_context,
            )

        tx_hash = _submitted_tx_hash(result)
        if tx_hash is None:
            return send_failed(
                audit_payload=signed_context,
            )

        tx_result = await assess_submitted_tx(
            rpc_r,
            tx_hash=tx_hash,
            send_mode=str(getattr(cfg.execution, "send_mode", "public") or "public"),
        )
        if tx_result.tx_status == "mined_reverted":
            return receipt_reverted(
                tx_hash=tx_hash,
                from_addr=from_addr,
                tx_result=tx_result,
                reject_payload=execute_context,
            )

        extra = dict(execute_context)
        if action_reason:
            extra["action_reason"] = action_reason
        return success(
            tx_hash=tx_hash,
            from_addr=from_addr,
            tx_result=tx_result,
            extra=extra,
        )
