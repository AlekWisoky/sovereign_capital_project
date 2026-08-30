from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

import victor_ai_bot.runtime_legacy as runtime_legacy_module
from victor_ai_bot.decision_identity import ensure_decision_identity, lineage_from_opportunity
from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.lifecycle_bridge import install_omar_lifecycle_hooks
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.canonical_settlement_interface import (
    install_canonical_settlement_bridge,
    install_canonical_settlement_interface,
)
from victor_ai_bot.runtime_services.execution_service import ExecutionService
from victor_ai_bot.runtime_services.runtime_execute_dispatch_facade import (
    AutoExecutionDispatchContext,
    RuntimeExecuteDispatchFacade,
)
from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade


class _Rpc:
    def __init__(self, url: str, **kwargs):
        self.url = url
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _Leg:
    def __init__(self, amount_in: str, min_out: str):
        self.amount_in = amount_in
        self.min_out = min_out
        self.venue = "venue-a"


class _Opportunity:
    def __init__(self):
        self.id = "opp-phase7"
        self.route_id = "route-phase7"
        self.can_execute = True
        self.route = SimpleNamespace(legs=[_Leg("1000", "990")])
        self.min_outs = ["990"]
        self.expected_profit_raw = "8"
        self.meta = {
            "safety": {"exec_ready": True, "profit_after_costs_wei": "8"},
            "profit_after_costs": "8",
            "brain": {},
        }

    def model_copy(self, deep: bool = False):
        return copy.deepcopy(self) if deep else copy.copy(self)


class _ExecutionService:
    async def handle_fioa_execution_wrapper(self, runtime, opp, decision, core):
        return await core()

    async def handle_post_execute_bookkeeping(
        self, runtime, opp, result, *, bn, latency_ms, mode
    ):
        return await ExecutionService.handle_post_execute_bookkeeping(
            self,
            runtime,
            opp,
            result,
            bn=bn,
            latency_ms=latency_ms,
            mode=mode,
        )

    def restore_operator_overrides(self, runtime, *, old_gas_mode, old_send_mode):
        runtime.cfg.execution.gas_mode = old_gas_mode
        runtime.cfg.execution.send_mode = old_send_mode


class _Runtime(RuntimeReceiptFacade):
    def __init__(self, *, omar, ledger_repo):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(
                dry_run=False,
                gas_mode="standard",
                send_mode="public",
            ),
        )
        self.metrics = SimpleNamespace(
            gas_mode="standard",
            send_mode="public",
            last_submitted_block=0,
        )
        self._last_submitted_block = 17
        self.cache = object()
        self._mev_guard = None
        self._execution_service = _ExecutionService()
        self._omar = omar
        self._ledger_repo = ledger_repo
        self.recorded = []

    async def _record_exec(self, result, opp, *, latency_ms, mode):
        self.recorded.append((result, opp, latency_ms, mode))


@pytest.mark.asyncio
# @codescene(disable:"Large Method") Production-shaped integration test intentionally keeps the complete lifecycle assertion in one scenario.
async def test_production_shaped_lineage_reaches_exact_omar_policy_update(
    monkeypatch, tmp_path
):
    install_canonical_settlement_interface()
    install_canonical_settlement_bridge()
    install_omar_lifecycle_hooks()

    omar = OmarRuntime(OmarConfig(enabled=True), chain_name="phase7")
    omar.learning_path = str(tmp_path / "real_policy.json")
    omar._real_learner.path = omar.learning_path

    opp = _Opportunity()
    decision = SimpleNamespace(
        action="trade",
        size_mult=0.75,
        borrow_mult=1.0,
        gas_mode="standard",
        metadata={},
    )
    identity = ensure_decision_identity(
        opp,
        decision,
        chain_name="ethereum",
        current_block=123,
    )
    omar.observe_decision(
        decision_id=identity.decision_id,
        opportunity_id=opp.id,
        route_id=opp.route_id,
        action="EXECUTE",
        state_key="phase7-state",
        context={"execution_realism": 0.9},
        metadata={"correlation_id": identity.correlation_id},
    )

    scaled = ExecutionService.scale_opportunity(ExecutionService, opp, 0.75)
    scaled.meta["canonical_lineage"] = {
        "decision_id": identity.decision_id,
        "correlation_id": identity.correlation_id,
    }
    scaled.meta["brain"]["canonical_decision_id"] = identity.decision_id
    scaled.meta["brain"]["correlation_id"] = identity.correlation_id

    events = []
    execution_result = SimpleNamespace(
        ok=True,
        dry_run=False,
        submitted=True,
        tx_hash="0xphase7",
        plan={},
    )

    class _Repo:
        def all_transactions(self, *, chain):
            sizing_id = scaled.meta["brain"]["sizing_id"]
            return [
                {
                    "transaction_id": "settlement-phase7",
                    "tx_type": "receipt_settlement",
                    "receipt_id": "0xphase7",
                    "ts_ms": 2000,
                    "metadata": {
                        "canonical_lineage": {
                            "decision_id": identity.decision_id,
                            "correlation_id": identity.correlation_id,
                            "sizing_id": sizing_id,
                        },
                        "canonical_decision_id": identity.decision_id,
                        "correlation_id": identity.correlation_id,
                        "sizing_id": sizing_id,
                        "opportunity_id": opp.id,
                        "route_id": opp.route_id,
                        "expected_net_usd": 5.0,
                        "realized_net_usd": 4.0,
                        "gas_cost_usd": 0.2,
                        "slippage_bps": 2.0,
                        "latency_ms": 11,
                        "truth_verified": True,
                    },
                }
            ]

    runtime = _Runtime(omar=omar, ledger_repo=_Repo())
    monkeypatch.setattr(runtime_legacy_module, "JsonRpcClient", _Rpc)

    async def fake_execute(
        rpc_r, rpc_s, cfg, candidate, bn, last_submitted_block, **kwargs
    ):
        events.append(("execute", candidate, kwargs["decision"]))
        assert candidate.meta["brain"]["sizing_id"]
        assert candidate.meta["brain"]["canonical_decision_id"] == identity.decision_id
        assert candidate.meta["brain"]["correlation_id"] == identity.correlation_id
        return execution_result

    monkeypatch.setattr(runtime_legacy_module, "try_execute_opportunity", fake_execute)

    async def fake_prepare(self, *, opp, bn, decision):
        return AutoExecutionDispatchContext(
            opportunity=opp,
            force_dry=False,
            old_gas_mode="standard",
            old_send_mode="public",
            read_url="read-rpc",
            send_url="send-rpc",
        )

    monkeypatch.setattr(
        RuntimeExecuteDispatchFacade,
        "_prepare_auto_execution_dispatch",
        fake_prepare,
    )

    await RuntimeBundle._execute_auto(runtime, scaled, 123, decision)

    assert events and events[0][0] == "execute"
    assert runtime.recorded
    recorded_result, recorded_opp, _latency_ms, mode = runtime.recorded[0]
    assert recorded_result is execution_result
    assert recorded_opp is scaled
    assert mode == "auto"

    lineage = lineage_from_opportunity(scaled)
    assert lineage["decision_id"] == identity.decision_id
    assert lineage["correlation_id"] == identity.correlation_id
    assert lineage["sizing_id"]

    assert omar.last_outcome["ok"] is True
    assert omar.last_outcome["decision_id"] == identity.decision_id
    assert omar.last_outcome["action"] == "EXECUTE"
    assert omar._real_learner.total_observations == 1

    with open(omar.learning_path + ".jsonl", "r", encoding="utf-8") as handle:
        update = json.loads(handle.readline())
    assert update["state_key"] == "phase7-state"
    assert update["action"] == "EXECUTE"
    assert update["outcome"]["realized_net_usd"] == 4.0
    assert update["outcome"]["gas_cost_usd"] == 0.2
    assert (
        update["outcome"]["metadata"]["canonical_lineage"]["sizing_id"]
        == lineage["sizing_id"]
    )
    assert update["outcome"]["metadata"]["size_mult_applied"] == 0.75
    assert update["reward"] == pytest.approx(3.7289)
