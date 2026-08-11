from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from victor_ai_bot import arb_engine, execution
from victor_ai_bot.abi_utils import enc_uint
from victor_ai_bot.bankroll import BankrollConfig, BankrollManager
from victor_ai_bot.command_center_overlay import AuditStore
from victor_ai_bot.executor_events import ARB_EXECUTED_TOPIC0, decode_arb_executed
from victor_ai_bot.execution import try_execute_opportunity
from victor_ai_bot.execution_capture.route_execution_plan import build_execution_route_plan
from victor_ai_bot.latency_profiler import LatencyProfiler
from victor_ai_bot.models import Metrics
from victor_ai_bot.pnl import PnLStore
from victor_ai_bot.persistence.db import PersistenceDB
from victor_ai_bot.persistence.repositories.bankroll_repository import BankrollEventRepository
from victor_ai_bot.persistence.repositories.capital_event_repository import CapitalEventRepository
from victor_ai_bot.persistence.repositories.ledger_repository import LedgerRepository
from victor_ai_bot.runtime_services.execution_service import ExecutionGateResult, ExecutionService
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.receipt_service import ReceiptService
from victor_ai_bot.runtime_services.replay_service import ReplayService
from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade
from victor_ai_bot.treasury.config import TreasuryConfig
from victor_ai_bot.treasury.ledger import TreasuryLedger
from victor_ai_bot.treasury.runtime import TreasuryRuntime
from victor_ai_bot.route_encoding import route_id_hex
from victor_ai_bot.models import Opportunity


class _QuoteRpc:
    pass


class _NoSendRpc:
    async def estimate_gas(self, tx):
        return 21_000

    async def get_nonce(self, addr):
        raise AssertionError("dry-run fixture must not request a signing nonce")

    async def send_raw_tx(self, raw):
        raise AssertionError("dry-run fixture must not broadcast a transaction")

    async def send_private_tx(self, raw, max_block_number=None):
        raise AssertionError("dry-run fixture must not submit privately")


class _AdmissionProbe(ExecutionService):
    def __init__(self):
        self.calls: list[str] = []

    def _ok(self, name: str):
        self.calls.append(name)
        return ExecutionGateResult(True, "ok", {"stage": name, "blocked": False})

    def auto_trade_hold_gate(self, runtime):
        return self._ok("hold")

    def auto_trade_family_gate(self, runtime, opp):
        return self._ok("family")

    def auto_trade_execution_realism_gate(self, opp, decision, runtime=None):
        self.calls.append("route")
        return opp, self._ok("route")

    def auto_trade_flashloan_gate(self, runtime, opp, decision):
        return self._ok("flashloan")

    def auto_trade_treasury_gate(self, runtime):
        return self._ok("treasury")


class _Runtime:
    def __init__(self, tmp_path):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(
                name="ethereum",
                chain_id=1,
                v3_pairs=[],
                curve_pools=[],
                balancer_pools=[],
                univ3_quoter_v2="0x0000000000000000000000000000000000000001",
                univ3_swap_router="0x0000000000000000000000000000000000000002",
                balancer_vault="",
            ),
            flags=SimpleNamespace(
                enable_two_leg_loops=True,
                enable_three_leg_loops=False,
                enable_v3_triangular=False,
            ),
            safety=SimpleNamespace(
                slippage_bps=50,
                minProfitAbs=1,
                minProfitBps=0,
                flashloan_fee_bps=9,
                max_borrow_amount="0",
                require_estimate_gas=False,
                require_simulation=False,
                mev_adversarial_eval_enabled=False,
                max_daily_loss_pct=3.0,
            ),
            execution=SimpleNamespace(
                dry_run=True,
                brain_mode="auto",
                gas_mode="standard",
                send_mode="public",
                gas_presets={},
                gas_limit=21_000,
                max_submit_per_block=1,
                flashloan_fee_bps=9,
                flash_provider="aave",
                deadline_seconds=30,
                executor_address="",
                profit_to="",
                private_key_env="UNUSED",
                rft=SimpleNamespace(enabled=True, episode_export_enabled=True, snapshot_top_k=3),
            ),
        )
        self.cache = SimpleNamespace(get=lambda key: None, set=lambda key, value: None)
        self._opps = []
        self._auto_trading = False
        self.metrics = Metrics()
        self._cc = SimpleNamespace(controls=SimpleNamespace(defensive_mode=False), audit=AuditStore(str(tmp_path / "audit.jsonl")))
        self._pnl = PnLStore(str(tmp_path / "pnl.sqlite3"))
        self._db = PersistenceDB(str(tmp_path / "state.sqlite3"))
        self._capital_event_repo = CapitalEventRepository(self._db, chain="ethereum")
        self._ledger_repo = LedgerRepository(self._db, capital_event_repo=self._capital_event_repo, chain="ethereum")
        self._bankroll_history_repo = BankrollEventRepository(self._db, chain="ethereum")
        self._ledger = TreasuryLedger(data_dir=str(tmp_path), chain="ethereum")
        self._bankroll = BankrollManager(
            BankrollConfig(auto_reinvest_enabled=True, base_borrow_amount_wei=1_000),
            history_repo=self._bankroll_history_repo,
            capital_event_repo=self._capital_event_repo,
        )
        self._treasury = TreasuryRuntime(
            cfg=TreasuryConfig(enabled=True),
            data_dir=str(tmp_path),
            db=self._db,
            chain="ethereum",
            capital_event_repo=self._capital_event_repo,
        )
        self._market_regime = {"regime": "balanced"}
        self._replay = __import__("victor_ai_bot.runtime_subsystems.replay_store", fromlist=["ReplayBundleStore"]).ReplayBundleStore(data_dir=str(tmp_path), chain="ethereum", chain_id=1)
        self._wealth_goal_service = None
        self._telemetry_service = None
        self._lat = LatencyProfiler()

    def fund_summary_state(self):
        return {"ok": True, "health": {"recoveryReady": True, "recoveryStatus": "ready"}}

    def capital_engine_state(self):
        return {"capital_engine": {"family_targets": {"flashloan_atomic": 1.0}}}

    def capital_truth(self):
        return SimpleNamespace(capital_summary={"deployableUsd": 100.0, "navUsd": 100.0, "utilizationPct": 0.0})

    def fund_summary_state(self):
        return {"ok": True, "health": {"recoveryReady": True, "recoveryStatus": "ready"}}

    def snapshot(self):
        return asyncio.sleep(0, result={"chain": "ethereum", "metrics": self.metrics.model_dump(), "rpc": {"error_rate": 0.0}, "opportunities": []})

    def execution_live_state(self):
        return {"items": []}

    def ledger_state(self):
        return {"ok": True, "balances": self._ledger.balance_report().get("balances", {})}

    def treasury_state(self):
        return {"ok": True}

    def internal_prime_state(self):
        return {"ok": True}

    def launch_state(self):
        return {"ok": True}

    def wealth_goal_state(self):
        return {"ok": False}


@pytest.mark.asyncio
async def test_current_golden_path_closed_loop(tmp_path, monkeypatch):
    runtime = _Runtime(tmp_path)
    amount_in = 1_000
    token_a = "0x00000000000000000000000000000000000000a1"
    token_b = "0x00000000000000000000000000000000000000b2"
    venue = "0x00000000000000000000000000000000000000c3"
    runtime.cfg.chain.v3_pairs = [{"token_in": token_a, "token_out": token_b, "fee": 3_000}]

    async def fixed_quotes(rpc, cfg, cache, edges, amount):
        out = {}
        for edge in edges:
            value = 1_100 if edge.token_in == token_a and amount == amount_in else 1_050
            out[arb_engine.edge_key(edge)] = (value, {"fee": 3_000})
        return out

    monkeypatch.setattr(arb_engine, "quote_edges_batch", fixed_quotes)
    opportunities = await RuntimePrimaryScanFacade._scan_primary_opportunities(
        runtime, _QuoteRpc(), current_block=19_000_000, amount_in=amount_in
    )
    assert opportunities, "scan must discover a fixed profitable loop"
    opp = opportunities[0]
    runtime._opps = [opp]
    assert isinstance(opp, Opportunity)
    assert len(opp.route.legs) == 2
    assert opp.route_id
    assert opp.min_outs == ["1094", "1044"]
    assert int(opp.expected_profit_raw) == 50

    # Test-local enrichment required by the current decision/admission contracts.
    opp.can_execute = True
    opp.meta.update(
        {
            "strategy_family": "flashloan_atomic",
            "route_family": "flashloan_atomic",
            "profitability": {"authoritative": True, "valid": True, "stale": False, "reason": "ok", "profit_after_costs_wei": "25"},
            "safety": {"exec_ready": True, "profit_after_costs_wei": "25"},
            "execution_route_plan": {"executable": True, "selected_venues": [venue, venue]},
            "capture": {"action": "trade", "lane": "public", "metadata": {"envelope": {"route_family": "flashloan_atomic"}, "flashloan_resilience": {"sizing": {"allowed": True, "selected_provider": "aave"}}}},
            "out1": "1100",
            "out2": "1050",
        }
    )

    from victor_ai_bot.decision_engine import DecisionEngine
    decision_engine = DecisionEngine(chain_name="ethereum", data_dir=str(tmp_path), brain_mode="auto")
    decision = decision_engine.annotate_and_decide(
        [opp], current_block=19_000_000, pending_txs=0, auto_enabled=True,
        cfg=runtime.cfg, gas_budget_remaining_wei=10**12, capital_budget_remaining_wei=10**12,
        family_capital_remaining_wei={"flashloan_atomic": 10**12},
    )
    assert decision.action == "trade"
    assert decision.opp_id == opp.id
    assert decision.route_id == opp.route_id

    admission = _AdmissionProbe().auto_trade_admission_gate(runtime, opp, decision)
    assert admission.allowed is True
    assert admission.plan.keys() == {"hold", "family", "route", "flashloan", "treasury"}

    async def fixed_gas(rpc, mode=None, presets=None):
        return 1, 1

    monkeypatch.setattr(execution, "suggest_gas", fixed_gas)
    dry_result = await try_execute_opportunity(
        _NoSendRpc(), _NoSendRpc(), runtime.cfg, opp, 19_000_000, 18_999_999,
        cache=None, decision=decision, force_dry_run=True, profiler=None,
    )
    assert dry_result.ok is True
    assert dry_result.dry_run is True
    assert dry_result.plan["amount_in"] == str(amount_in)
    assert dry_result.plan["amount_out"] == "1044"
    assert dry_result.plan["flashloan_fee"] == "0"
    assert dry_result.plan["gas_cost"] == "21000"
    assert dry_result.plan["route_id"] == opp.route_id

    # SYNTHETIC_HANDOFF: dry-run has no tx hash and cannot mine. The fixed hash,
    # expected PnL row, and receipt below model a hypothetical submitted execution.
    tx_hash = "0x" + "ab" * 32
    await runtime._pnl.add_trade({
        "ts": 1, "chain": "ethereum", "opportunity_id": opp.id, "route_id": opp.route_id,
        "tx_hash": tx_hash, "mode": "auto", "dry_run": False, "ok": True, "reason": "submitted",
        "expected_gross_profit_wei": "50", "expected_profit_after_costs_wei": "25",
        "estimated_gas_cost_wei": "21000", "flashloan_fee_wei": "0", "gas_limit": 21000,
        "max_fee_wei": "1", "priority_fee_wei": "1", "strategy_type": "flashloan_atomic",
        "income_stream": "arb", "venue_path": "fixed",
    })
    route_topic = "0x" + opp.route_id[2:].rjust(64, "0") if opp.route_id.startswith("0x") else "0x" + opp.route_id.rjust(64, "0")
    token_topic = "0x" + token_a[2:].rjust(64, "0")
    log = {"address": venue, "topics": [ARB_EXECUTED_TOPIC0, route_topic, token_topic], "data": "0x" + (enc_uint(1_000) + enc_uint(50) + enc_uint(1)).hex()}
    receipt = {"status": "0x1", "gasUsed": "0x5208", "effectiveGasPrice": "0x1", "blockNumber": "0x122", "logs": [log]}
    decoded = decode_arb_executed(log)
    assert decoded is not None
    assert decoded.profit == 50
    assert decoded.provider == 1

    pnl = await runtime._pnl.update_receipt(tx_hash, receipt, executor_address=venue, chain_weth=token_a)
    assert pnl["status"] == 1
    assert pnl["realized_profit_token_wei"] == "50"
    assert pnl["realized_gas_cost_wei"] == str(21_000)

    settled = ReceiptService().synchronize_settlement_accounting(
        runtime, tx_hash=tx_hash, pending={"strategy_family": "flashloan_atomic", "route_family": "flashloan_atomic", "flashloan_fee_wei": "0"},
        decoded={"realized_profit_after_gas_wei": "50", "realized_profit_token": token_a, "realized_profit_token_wei": "50", "realized_profit_after_gas_usd_micro": "50", "realized_gas_cost_wei": "21000", "realized_gas_cost_usd_micro": "0"},
        status=1, amount_in=amount_in, expected_after=25, realized_after=50, submit_to_receipt_ms=10,
        route_id=opp.route_id, route_family="flashloan_atomic", strategy_family="flashloan_atomic", capture_lane_pending="PUBLIC",
    )
    assert settled["ok"] is True
    assert runtime._ledger_repo.has_receipt_transaction(chain="ethereum", receipt_id=tx_hash, tx_type="receipt_settlement")
    assert runtime._bankroll.state.realized_profit_wei == 50
    assert runtime._treasury.cfg.meta["last_settlement_receipt_id"] == tx_hash
    capital_events = runtime._capital_event_repo.latest_events(limit=10)
    commit_ids = {str((event.get("payload") or {}).get("capitalCommitId")) for event in capital_events if (event.get("payload") or {}).get("capitalCommitId")}
    assert len(commit_ids) == 1

    replay = ReplayService()
    event_id = replay.create_bundle(runtime, opportunity_id=opp.id, route_id=opp.route_id, mode="auto", rl_state=decision.rl_state, rl_action=decision.rl_action_index, latency_ms=10, plan=dry_result.plan, dry_run=True, ok=True, attempted=False, submitted=False, reason="dry_run_ok_no_executor", tx_hash=tx_hash, block_number=19_000_000, status="submitted")
    assert event_id
    bundle = runtime._replay.load_by_tx_hash(tx_hash)
    assert bundle["tx_hash"] == tx_hash
    assert bundle["opportunity_id"] == opp.id

    operator = await OperatorSummaryService().build_snapshot(runtime)
    assert operator["dataSource"] == "backend"
    assert operator["receiptSummary"]["lastTxHash"] == tx_hash
    assert operator["flashloanArbLifecycle"]["settlementRecorded"] is True
