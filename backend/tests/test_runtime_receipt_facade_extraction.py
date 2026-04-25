from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services import runtime_receipt_facade as receipt_module
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


EXTRACTED_METHODS = {
    "_receipt_loop",
    "_handle_receipt_loop_failure",
    "_receipt_retry_count_from_pending",
    "_record_receipt_finalize_failure",
    "_run_receipt_finalize_step",
    "_observe_receipt_finalize_critical_failure",
    "_safe_finalize_receipt_side_effects",
}


class _ReceiptServiceOk:
    def __init__(self):
        self.calls = []
        self.health_calls = []

    def finalize_replay(self, *args, **kwargs):
        self.calls.append("finalize_replay")

    def observe_outcome_truth_health(self, *args, **kwargs):
        self.calls.append("observe_outcome_truth_health")
        payload = dict(kwargs)
        payload.pop("runtime", None)
        self.health_calls.append(payload)

    def record_outcome_truth_gap(self, *args, **kwargs):
        self.calls.append("record_outcome_truth_gap")

    def _realized_usd_from_wei(self, value):
        return float(value)

    def synchronize_settlement_accounting(self, *args, **kwargs):
        self.calls.append("synchronize_settlement_accounting")
        return {"ok": True, "transactionId": "tx-settle"}

    def persist_execution_outcome(self, *args, **kwargs):
        self.calls.append("persist_execution_outcome")
        return {
            "route_family": "flashloan_atomic",
            "strategy_family": "flashloan_atomic",
            "realized_usd": 10.0,
            "expected_usd": 11.0,
        }

    def update_execution_learning(self, *args, **kwargs):
        self.calls.append("update_execution_learning")

    def observe_settlement_memory(self, *args, **kwargs):
        self.calls.append("observe_settlement_memory")

    def update_agent_performance(self, *args, **kwargs):
        self.calls.append("update_agent_performance")

    def observe_blockspace(self, *args, **kwargs):
        self.calls.append("observe_blockspace")

    def notify_governance(self, *args, **kwargs):
        self.calls.append("notify_governance")

    def notify_narrative(self, *args, **kwargs):
        self.calls.append("notify_narrative")


class _ReceiptServiceFinalizeReplayValueError(_ReceiptServiceOk):
    def finalize_replay(self, *args, **kwargs):
        raise ValueError("replay store unavailable")


class _ReceiptServiceOutcomeTruthGapValueError(_ReceiptServiceOk):
    def record_outcome_truth_gap(self, *args, **kwargs):
        raise ValueError("gap audit unavailable")


class _ReceiptServicePersistValueError(_ReceiptServiceOk):
    def persist_execution_outcome(self, *args, **kwargs):
        self.calls.append("persist_execution_outcome")
        raise ValueError("execution outcome store unavailable")


class _ReceiptServicePersistInvalidPayload(_ReceiptServiceOk):
    def persist_execution_outcome(self, *args, **kwargs):
        self.calls.append("persist_execution_outcome")
        return []


class _ReceiptServiceSettlementSyncValueError(_ReceiptServiceOk):
    def synchronize_settlement_accounting(self, *args, **kwargs):
        raise ValueError("settlement sync unavailable")


class _ReceiptServiceSettlementSyncInvalidPayload(_ReceiptServiceOk):
    def synchronize_settlement_accounting(self, *args, **kwargs):
        self.calls.append("synchronize_settlement_accounting")
        return []


class _ReceiptServiceMissingCanonicalSettlementSync:
    def __init__(self):
        self.calls = []
        self.health_calls = []

    def finalize_replay(self, *args, **kwargs):
        self.calls.append("finalize_replay")

    def observe_outcome_truth_health(self, *args, **kwargs):
        self.calls.append("observe_outcome_truth_health")
        payload = dict(kwargs)
        payload.pop("runtime", None)
        self.health_calls.append(payload)


class _Runtime(RuntimeReceiptFacade):
    def __init__(self):
        self._errors = []
        self._pending = {}
        self._receipt_q = asyncio.Queue()
        self._receipt_finalize_failures = []


class _ReceiptPnl:
    def __init__(self):
        self.calls = 0

    async def update_receipt(self, *_args, **_kwargs):
        self.calls += 1
        return {}


class _RpcManager:
    def best_read(self):
        return "http://example.invalid"


class _JsonRpcClientRetryStub:
    calls = 0

    def __init__(self, *_args, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def wait_for_receipt(self, *_args, **_kwargs):
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError("temporary receipt rpc failure")
        return {
            "gasUsed": "0x1",
            "effectiveGasPrice": "0x1",
            "blockNumber": "0x1",
            "logs": [],
            "status": "0x1",
        }


class _ReceiptLoopRuntime(RuntimeReceiptFacade):
    def __init__(self):
        self._errors = []
        self._pending = {"0xabc": {"gas_est_wei": "1"}}
        self._receipt_q = asyncio.Queue()
        self.rpc_manager = _RpcManager()
        self._pnl = _ReceiptPnl()
        self._receipt_service = None
        self.cache = {}
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(executor_address="0xexecutor", usd_accounting_enabled=False),
            chain=SimpleNamespace(weth="0xweth", name="base"),
        )


def test_runtime_bundle_inherits_extracted_receipt_facade():
    assert issubclass(RuntimeBundle, RuntimeReceiptFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_receipt_facade_preserves_safe_finalize_surface():
    runtime = _Runtime()
    service = _ReceiptServiceOk()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == []
    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "synchronize_settlement_accounting",
        "persist_execution_outcome",
        "update_execution_learning",
        "observe_settlement_memory",
        "update_agent_performance",
        "observe_blockspace",
        "notify_governance",
        "notify_narrative",
    ]


def test_runtime_receipt_facade_preserves_persistence_when_finalize_replay_fails():
    runtime = _Runtime()
    service = _ReceiptServiceFinalizeReplayValueError()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == ["receipt_loop_error:replay store unavailable"]
    assert runtime._receipt_finalize_failures == [
        {
            "tx_hash": "0xabc",
            "step": "finalize_replay",
            "error": "replay store unavailable",
            "critical": False,
            "ts_ms": runtime._receipt_finalize_failures[0]["ts_ms"],
        }
    ]
    assert service.calls == [
        "observe_outcome_truth_health",
        "synchronize_settlement_accounting",
        "persist_execution_outcome",
        "update_execution_learning",
        "observe_settlement_memory",
        "update_agent_performance",
        "observe_blockspace",
        "notify_governance",
        "notify_narrative",
    ]


def test_runtime_receipt_facade_skips_learning_and_governance_when_settled_profit_truth_missing():
    runtime = _Runtime()
    service = _ReceiptServiceOk()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": False, "reason_code": "settled_profit_truth_unavailable"},
    )

    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "record_outcome_truth_gap",
        "observe_blockspace",
        "notify_narrative",
    ]


def test_runtime_receipt_facade_marks_health_degraded_when_persist_execution_outcome_fails():
    runtime = _Runtime()
    service = _ReceiptServicePersistValueError()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == ["receipt_loop_error:execution outcome store unavailable"]
    assert runtime._receipt_finalize_failures == [
        {
            "tx_hash": "0xabc",
            "step": "persist_execution_outcome",
            "error": "execution outcome store unavailable",
            "critical": True,
            "ts_ms": runtime._receipt_finalize_failures[0]["ts_ms"],
        }
    ]
    assert service.health_calls == [
        {"verified": True, "reason_code": "ok"},
        {
            "verified": False,
            "reason_code": "receipt_finalize_persist_execution_outcome_failed",
        },
    ]
    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "synchronize_settlement_accounting",
        "persist_execution_outcome",
        "observe_outcome_truth_health",
    ]


def test_runtime_receipt_facade_marks_health_degraded_when_persisted_payload_is_invalid():
    runtime = _Runtime()
    service = _ReceiptServicePersistInvalidPayload()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == []
    assert runtime._receipt_finalize_failures == []
    assert service.health_calls == [
        {"verified": True, "reason_code": "ok"},
        {
            "verified": False,
            "reason_code": "receipt_finalize_persist_execution_outcome_invalid_payload_failed",
        },
    ]
    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "synchronize_settlement_accounting",
        "persist_execution_outcome",
        "observe_outcome_truth_health",
    ]


def test_runtime_receipt_facade_records_gap_failure_without_skipping_blockspace_and_narrative():
    runtime = _Runtime()
    service = _ReceiptServiceOutcomeTruthGapValueError()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": False, "reason_code": "settled_profit_truth_unavailable"},
    )

    assert runtime._errors == ["receipt_loop_error:gap audit unavailable"]
    assert runtime._receipt_finalize_failures == [
        {
            "tx_hash": "0xabc",
            "step": "record_outcome_truth_gap",
            "error": "gap audit unavailable",
            "critical": True,
            "ts_ms": runtime._receipt_finalize_failures[0]["ts_ms"],
        }
    ]
    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "observe_blockspace",
        "notify_narrative",
    ]


def test_runtime_receipt_facade_marks_health_degraded_when_settlement_sync_fails():
    runtime = _Runtime()
    service = _ReceiptServiceSettlementSyncValueError()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == ["receipt_loop_error:settlement sync unavailable"]
    assert runtime._receipt_finalize_failures == [
        {
            "tx_hash": "0xabc",
            "step": "synchronize_settlement_accounting",
            "error": "settlement sync unavailable",
            "critical": True,
            "ts_ms": runtime._receipt_finalize_failures[0]["ts_ms"],
        }
    ]
    assert service.health_calls == [
        {"verified": True, "reason_code": "ok"},
        {
            "verified": False,
            "reason_code": "receipt_finalize_synchronize_settlement_accounting_failed",
        },
    ]


def test_runtime_receipt_facade_marks_health_degraded_when_missing_canonical_settlement_sync():
    runtime = _Runtime()
    service = _ReceiptServiceMissingCanonicalSettlementSync()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == ["receipt_loop_error:canonical settlement sync unavailable"]
    assert runtime._receipt_finalize_failures == [
        {
            "tx_hash": "0xabc",
            "step": "synchronize_settlement_accounting",
            "error": "canonical settlement sync unavailable",
            "critical": True,
            "ts_ms": runtime._receipt_finalize_failures[0]["ts_ms"],
        }
    ]
    assert service.health_calls == [
        {"verified": True, "reason_code": "ok"},
        {
            "verified": False,
            "reason_code": "receipt_finalize_synchronize_settlement_accounting_failed",
        },
    ]
    assert service.calls == [
        "finalize_replay",
        "observe_outcome_truth_health",
        "observe_outcome_truth_health",
    ]


def test_runtime_receipt_facade_marks_health_degraded_when_settlement_sync_payload_is_invalid():
    runtime = _Runtime()
    service = _ReceiptServiceSettlementSyncInvalidPayload()

    runtime._safe_finalize_receipt_side_effects(
        service,
        tx_hash="0xabc",
        receipt={},
        decoded={},
        pending={},
        status=1,
        submit_to_receipt_ms=10,
        expected_after=20,
        realized_after=30,
        amount_in=40,
        gas_est_wei=50,
        route_id="route-1",
        reward_trace={},
        capture_lane_pending="private",
        capture_relay_pending="relay",
        outcome_truth={"ok": True, "reason_code": "ok"},
    )

    assert runtime._errors == []
    assert runtime._receipt_finalize_failures == []
    assert service.health_calls == [
        {"verified": True, "reason_code": "ok"},
        {
            "verified": False,
            "reason_code": "receipt_finalize_synchronize_settlement_accounting_invalid_payload_failed",
        },
    ]


def test_receipt_loop_failure_requeues_pending_with_retry_metadata():
    runtime = _Runtime()
    runtime._pending["0xabc"] = {"route_id": "route-1"}

    runtime._handle_receipt_loop_failure(
        tx_hash="0xabc",
        error=RuntimeError("temporary receipt rpc failure"),
        receipt_seen=False,
        pending_popped=False,
    )

    pending = runtime._pending["0xabc"]
    assert pending["_receipt_retry_count"] == 1
    assert pending["_receipt_retry_last_error"] == "temporary receipt rpc failure"
    assert pending["_receipt_retry_receipt_seen"] is False
    assert pending["_receipt_retry_exhausted"] is False
    assert pending["_receipt_retry_state"] == "retrying"
    assert runtime._receipt_q.get_nowait() == "0xabc"
    assert runtime._errors == ["receipt_loop_error:temporary receipt rpc failure"]


def test_receipt_loop_failure_marks_pending_for_manual_recovery_after_receipt_seen():
    runtime = _Runtime()
    runtime._pending["0xabc"] = {"route_id": "route-1"}

    runtime._handle_receipt_loop_failure(
        tx_hash="0xabc",
        error=RuntimeError("bad receipt state"),
        receipt_seen=True,
        pending_popped=False,
    )

    pending = runtime._pending["0xabc"]
    assert pending["_receipt_retry_count"] == 1
    assert pending["_receipt_retry_receipt_seen"] is True
    assert pending["_receipt_retry_exhausted"] is True
    assert pending["_receipt_retry_state"] == "awaiting_manual_recovery"
    assert runtime._receipt_q.empty() is True
    assert runtime._errors == ["receipt_loop_error:bad receipt state"]


async def _exercise_receipt_loop_retry(monkeypatch):
    _JsonRpcClientRetryStub.calls = 0
    monkeypatch.setattr(receipt_module, "JsonRpcClient", _JsonRpcClientRetryStub)
    runtime = _ReceiptLoopRuntime()
    await runtime._receipt_q.put("0xabc")

    task = asyncio.create_task(runtime._receipt_loop())
    try:
        for _ in range(50):
            if "0xabc" not in runtime._pending and runtime._pnl.calls == 1:
                break
            await asyncio.sleep(0)
        await asyncio.wait_for(runtime._receipt_q.join(), 0.5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    return runtime


def test_receipt_loop_retries_transient_rpc_failure_and_drains_queue(monkeypatch):
    runtime = asyncio.run(_exercise_receipt_loop_retry(monkeypatch))

    assert runtime._pnl.calls == 1
    assert _JsonRpcClientRetryStub.calls == 2
    assert runtime._pending == {}
    assert runtime._errors == ["receipt_loop_error:temporary receipt rpc failure"]
