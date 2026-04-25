from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_legacy import RuntimeBundle


class _DecisionReturns:
    def annotate_and_decide(self, opps, **kwargs):
        return {"ok": True, "count": len(opps), "kwargs": kwargs}


class _DecisionValueError:
    def annotate_and_decide(self, opps, **kwargs):
        raise ValueError("bad local state")


class _DecisionKeyError:
    def annotate_and_decide(self, opps, **kwargs):
        raise KeyError("unexpected bug")


def _bundle(decision):
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._decision = decision
    bundle._errors = []
    bundle.cfg = SimpleNamespace()
    return bundle


def test_safe_decide_opportunities_returns_decision_payload() -> None:
    bundle = _bundle(_DecisionReturns())

    result = bundle._safe_decide_opportunities(
        [{"id": "opp-1"}],
        current_block=123,
        pending_txs=2,
        auto_enabled=True,
        gas_budget_remaining_wei=456,
    )

    assert result["ok"] is True
    assert result["count"] == 1
    assert result["kwargs"]["current_block"] == 123
    assert result["kwargs"]["pending_txs"] == 2
    assert result["kwargs"]["auto_enabled"] is True
    assert result["kwargs"]["gas_budget_remaining_wei"] == 456
    assert bundle._errors == []


def test_safe_decide_opportunities_swallows_expected_local_failure() -> None:
    bundle = _bundle(_DecisionValueError())

    result = bundle._safe_decide_opportunities(
        [],
        current_block=1,
        pending_txs=0,
        auto_enabled=False,
        gas_budget_remaining_wei=0,
    )

    assert result is None
    assert bundle._errors == ["decision_engine_failed:bad local state"]


def test_safe_decide_opportunities_does_not_swallow_unexpected_bug() -> None:
    bundle = _bundle(_DecisionKeyError())

    with pytest.raises(KeyError, match="unexpected bug"):
        bundle._safe_decide_opportunities(
            [],
            current_block=1,
            pending_txs=0,
            auto_enabled=False,
            gas_budget_remaining_wei=0,
        )


class _BundleAnnotateOk(RuntimeBundle):
    async def _annotate_can_execute(self, rpc, opps):
        self._annotated = (rpc, list(opps))


class _BundleAnnotateValueError(RuntimeBundle):
    async def _annotate_can_execute(self, rpc, opps):
        raise ValueError("bad annotate state")


class _BundleAnnotateKeyError(RuntimeBundle):
    async def _annotate_can_execute(self, rpc, opps):
        raise KeyError("unexpected annotate bug")


@pytest.mark.asyncio
async def test_safe_annotate_can_execute_records_expected_local_failure() -> None:
    bundle = _BundleAnnotateValueError.__new__(_BundleAnnotateValueError)
    bundle._errors = []

    await bundle._safe_annotate_can_execute(SimpleNamespace(), [])

    assert bundle._errors == ["annotate_can_execute_failed:bad annotate state"]


@pytest.mark.asyncio
async def test_safe_annotate_can_execute_does_not_swallow_unexpected_bug() -> None:
    bundle = _BundleAnnotateKeyError.__new__(_BundleAnnotateKeyError)
    bundle._errors = []

    with pytest.raises(KeyError, match="unexpected annotate bug"):
        await bundle._safe_annotate_can_execute(SimpleNamespace(), [])


@pytest.mark.asyncio
async def test_safe_annotate_can_execute_passes_through_valid_path() -> None:
    bundle = _BundleAnnotateOk.__new__(_BundleAnnotateOk)
    bundle._errors = []
    rpc = SimpleNamespace(name="rpc")
    opps = [{"id": "opp-1"}]

    await bundle._safe_annotate_can_execute(rpc, opps)

    assert bundle._annotated == (rpc, opps)
    assert bundle._errors == []


class _ReceiptServiceOk:
    def __init__(self):
        self.calls = []

    def finalize_replay(self, *args, **kwargs):
        self.calls.append("finalize_replay")

    def _realized_usd_from_wei(self, value):
        return float(value)

    def persist_execution_outcome(self, *args, **kwargs):
        self.calls.append("persist_execution_outcome")
        return {
            "route_family": "rf",
            "strategy_family": "sf",
            "realized_usd": 1.5,
            "expected_usd": 2.5,
        }

    def synchronize_settlement_accounting(self, *args, **kwargs):
        self.calls.append("synchronize_settlement_accounting")
        return {"ok": True, "transactionId": "tx-settle"}

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


class _ReceiptServiceValueError(_ReceiptServiceOk):
    def persist_execution_outcome(self, *args, **kwargs):
        raise ValueError("bad receipt state")


class _ReceiptServiceKeyError(_ReceiptServiceOk):
    def persist_execution_outcome(self, *args, **kwargs):
        raise KeyError("unexpected receipt bug")


def _receipt_bundle():
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._errors = []
    return bundle


def test_safe_finalize_receipt_side_effects_records_expected_local_failure() -> None:
    bundle = _receipt_bundle()

    bundle._safe_finalize_receipt_side_effects(
        _ReceiptServiceValueError(),
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

    assert bundle._errors == ["receipt_loop_error:bad receipt state"]


def test_safe_finalize_receipt_side_effects_does_not_swallow_unexpected_bug() -> None:
    bundle = _receipt_bundle()

    with pytest.raises(KeyError, match="unexpected receipt bug"):
        bundle._safe_finalize_receipt_side_effects(
            _ReceiptServiceKeyError(),
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


def test_safe_finalize_receipt_side_effects_passes_through_valid_path() -> None:
    bundle = _receipt_bundle()
    service = _ReceiptServiceOk()

    bundle._safe_finalize_receipt_side_effects(
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

    assert bundle._errors == []
    assert service.calls == [
        "finalize_replay",
        "synchronize_settlement_accounting",
        "persist_execution_outcome",
        "update_execution_learning",
        "observe_settlement_memory",
        "update_agent_performance",
        "observe_blockspace",
        "notify_governance",
        "notify_narrative",
    ]


def test_record_tick_failure_updates_metrics_and_error_log() -> None:
    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._errors = []
    bundle.metrics = SimpleNamespace(last_error="", failed_ticks=0)

    bundle._record_tick_failure(RuntimeError("tick failed"))

    assert bundle.metrics.last_error == "tick failed"
    assert bundle.metrics.failed_ticks == 1
    assert bundle._errors == ["tick failed"]


def test_record_tick_failure_tolerates_metric_counter_write_failure() -> None:
    class _Metrics:
        def __init__(self):
            self.last_error = ""
            self._failed_ticks = 0

        @property
        def failed_ticks(self):
            return self._failed_ticks

        @failed_ticks.setter
        def failed_ticks(self, value):
            raise ValueError("metrics write failed")

    bundle = RuntimeBundle.__new__(RuntimeBundle)
    bundle._errors = []
    bundle.metrics = _Metrics()

    bundle._record_tick_failure(RuntimeError("tick failed"))

    assert bundle.metrics.last_error == "tick failed"
    assert bundle._errors == ["tick failed"]
