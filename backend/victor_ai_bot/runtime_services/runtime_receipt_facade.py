from __future__ import annotations

import asyncio
import time
from typing import Any

from victor_ai_bot.executor_events import decode_arb_executed
from victor_ai_bot.rpc import JsonRpcClient
from victor_ai_bot.runtime_subsystems import build_reward_trace
from victor_ai_bot.usd_pricing import (
    gas_wei_to_token_wei,
    gas_wei_to_usd_micro,
    token_to_usd_micro,
)

_SAFE_RECEIPT_EXCEPTIONS = (AttributeError, RuntimeError, TypeError, ValueError)
_RECEIPT_RETRY_LIMIT = 3


class RuntimeReceiptFacade:
    def _update_settlement_followthrough(
        self,
        *,
        learning_ok: bool | None = None,
        memory_ok: bool | None = None,
    ) -> None:
        sync = dict(getattr(self, "_last_settlement_sync", {}) or {})
        if not sync:
            return
        learning_state = dict(sync.get("learningSync") or {})
        memory_state = dict(sync.get("memorySync") or {})
        if learning_ok is not None:
            learning_state = {
                "executed": True,
                "ok": bool(learning_ok),
                "reasonCode": ("ok" if learning_ok else "receipt_finalize_update_execution_learning_failed"),
            }
        if memory_ok is not None:
            memory_state = {
                "executed": True,
                "ok": bool(memory_ok),
                "reasonCode": ("ok" if memory_ok else "receipt_finalize_observe_settlement_memory_failed"),
            }
        sync["learningSync"] = learning_state
        sync["memorySync"] = memory_state
        learning_done = bool(learning_state.get("executed")) and bool(learning_state.get("ok"))
        memory_done = bool(memory_state.get("executed")) and bool(memory_state.get("ok"))
        reason_codes = []
        if not learning_done:
            reason_codes.append(str(learning_state.get("reasonCode") or "pending_receipt_followthrough"))
        if not memory_done:
            reason_codes.append(str(memory_state.get("reasonCode") or "pending_receipt_followthrough"))
        sync["closedLoop"] = {
            "settlementAccounting": bool(sync.get("ok", False)),
            "learningRecorded": learning_done,
            "memoryRecorded": memory_done,
            "completed": bool(sync.get("ok", False) and learning_done and memory_done),
            "reasonCodes": reason_codes,
            "nextAction": ("none" if not reason_codes else "finalize_receipt_followthrough"),
        }
        self._last_settlement_sync = sync

    def _record_receipt_finalize_failure(
        self,
        *,
        tx_hash: str,
        step: str,
        error: Exception,
        critical: bool,
    ) -> None:
        error_text = str(error or step or "receipt_finalize_failed")
        try:
            self._errors.append(f"receipt_loop_error:{error_text}")
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        try:
            failures = getattr(self, "_receipt_finalize_failures", None)
            if not isinstance(failures, list):
                failures = []
                setattr(self, "_receipt_finalize_failures", failures)
            failures.append(
                {
                    "tx_hash": str(tx_hash),
                    "step": str(step or "unknown"),
                    "error": error_text,
                    "critical": bool(critical),
                    "ts_ms": int(time.time() * 1000),
                }
            )
            if len(failures) > 128:
                del failures[:-128]
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

    def _run_receipt_finalize_step(
        self,
        fn: Any,
        *args: Any,
        receipt_tx_hash: str,
        step: str,
        critical: bool,
        **kwargs: Any,
    ) -> tuple[bool, Any]:
        try:
            return True, fn(*args, **kwargs)
        except _SAFE_RECEIPT_EXCEPTIONS as e:
            self._record_receipt_finalize_failure(
                tx_hash=str(receipt_tx_hash),
                step=str(step),
                error=e,
                critical=bool(critical),
            )
            return False, None

    def _observe_receipt_finalize_critical_failure(
        self,
        service: Any,
        *,
        tx_hash: str,
        step: str,
    ) -> None:
        if not hasattr(service, "observe_outcome_truth_health"):
            return
        reason_code = f"receipt_finalize_{str(step or 'unknown')}_failed"
        try:
            service.observe_outcome_truth_health(
                runtime=self,
                verified=False,
                reason_code=reason_code,
            )
        except _SAFE_RECEIPT_EXCEPTIONS as e:
            self._record_receipt_finalize_failure(
                tx_hash=str(tx_hash),
                step="observe_outcome_truth_health",
                error=e,
                critical=False,
            )

    async def _receipt_loop(self) -> None:
        # Single-worker receipt processing to avoid runaway RPC usage.
        service = getattr(self, "_receipt_service", None)
        while True:
            tx_hash = await self._receipt_q.get()
            receipt = None
            pending_popped = False
            try:
                read_url = self.rpc_manager.best_read()
                if not read_url:
                    continue
                async with JsonRpcClient(
                    read_url, timeout_s=10.0, max_concurrency=5, max_batch=10
                ) as rpc:
                    receipt = await rpc.wait_for_receipt(
                        tx_hash, timeout_s=180.0, poll_interval_s=2.0
                    )
                    if not receipt:
                        self._handle_receipt_loop_failure(
                            tx_hash=str(tx_hash),
                            error="receipt_unavailable",
                            receipt_seen=False,
                            pending_popped=False,
                        )
                        continue

                    gas_used = (
                        int(receipt.get("gasUsed") or "0x0", 16)
                        if isinstance(receipt.get("gasUsed"), str)
                        else 0
                    )
                    gas_price_hex = (
                        receipt.get("effectiveGasPrice") or receipt.get("gasPrice") or "0x0"
                    )
                    gas_price = int(gas_price_hex, 16) if isinstance(gas_price_hex, str) else 0
                    gas_cost_wei = int(gas_used) * int(gas_price)
                    block_hex = receipt.get("blockNumber") or "0x0"
                    block_number = int(block_hex, 16) if isinstance(block_hex, str) else 0

                    profit_token = None
                    profit_amt = None
                    try:
                        for log in receipt.get("logs") or []:
                            decoded_event = decode_arb_executed(log)
                            if decoded_event is None:
                                continue
                            profit_token = str(decoded_event.token)
                            profit_amt = int(decoded_event.profit)
                            break
                    except _SAFE_RECEIPT_EXCEPTIONS:
                        profit_token = None
                        profit_amt = None

                    gas_in_profit = None
                    if profit_token and block_number > 0:
                        try:
                            gas_in_profit = await gas_wei_to_token_wei(
                                rpc,
                                chain=self.cfg.chain,
                                gas_cost_wei=int(gas_cost_wei),
                                token_out=str(profit_token),
                                block_number=int(block_number),
                                cache=self.cache,
                            )
                        except _SAFE_RECEIPT_EXCEPTIONS:
                            gas_in_profit = None

                    usd_profit = None
                    usd_gas = None
                    usd_net = None
                    if (
                        bool(getattr(self.cfg.execution, "usd_accounting_enabled", False))
                        and profit_token
                        and profit_amt is not None
                        and block_number > 0
                    ):
                        usd_pref = str(
                            getattr(self.cfg.execution, "usd_stable_preference", "usdc") or "usdc"
                        )
                        try:
                            usd_profit = await token_to_usd_micro(
                                rpc,
                                chain=self.cfg.chain,
                                token=str(profit_token),
                                amount_wei=int(profit_amt),
                                block_number=int(block_number),
                                cache=self.cache,
                                preference=usd_pref,
                            )
                            usd_gas = await gas_wei_to_usd_micro(
                                rpc,
                                chain=self.cfg.chain,
                                gas_cost_wei=int(gas_cost_wei),
                                block_number=int(block_number),
                                cache=self.cache,
                                preference=usd_pref,
                            )
                            if usd_profit is not None and usd_gas is not None:
                                usd_net = int(max(0, int(usd_profit) - int(usd_gas)))
                        except _SAFE_RECEIPT_EXCEPTIONS:
                            usd_profit = None
                            usd_gas = None
                            usd_net = None

                    decoded = await self._pnl.update_receipt(
                        tx_hash,
                        receipt,
                        executor_address=str(self.cfg.execution.executor_address or ""),
                        chain_weth=str(self.cfg.chain.weth or ""),
                        realized_gas_cost_in_profit_token_wei=(
                            int(gas_in_profit) if gas_in_profit is not None else None
                        ),
                        realized_profit_usd_micro=(
                            int(usd_profit) if usd_profit is not None else None
                        ),
                        realized_gas_cost_usd_micro=int(usd_gas) if usd_gas is not None else None,
                        realized_profit_after_gas_usd_micro=(
                            int(usd_net) if usd_net is not None else None
                        ),
                    )

                status_hex = receipt.get("status")
                status = int(status_hex, 16) if isinstance(status_hex, str) else 0
                pending = self._pending.pop(tx_hash, None) or {}
                pending_popped = True
                if not isinstance(pending, dict):
                    pending = {}
                submit_to_receipt_ms = (
                    service.submit_to_receipt_ms(self, pending)
                    if service is not None and hasattr(service, "submit_to_receipt_ms")
                    else 0
                )

                try:
                    expected_after = int(pending.get("expected_after") or 0)
                except (AttributeError, TypeError, ValueError):
                    expected_after = 0
                try:
                    amount_in = int(pending.get("amount_in") or 0)
                except (AttributeError, TypeError, ValueError):
                    amount_in = 0
                try:
                    latency_ms = int(pending.get("latency_ms") or 0)
                except (AttributeError, TypeError, ValueError):
                    latency_ms = 0
                mode = str(pending.get("mode") or "auto")
                route_id = str(pending.get("route_id") or "")
                rl_state = str(pending.get("rl_state") or "")
                try:
                    rl_action = int(pending.get("rl_action") or -1)
                except (AttributeError, TypeError, ValueError):
                    rl_action = -1
                aqe_action = str(pending.get("aqe_action") or "")
                try:
                    gas_est_wei = int(pending.get("gas_est_wei") or 0)
                except (AttributeError, TypeError, ValueError):
                    gas_est_wei = 0
                capture_lane_pending = str(pending.get("capture_lane") or "")
                capture_relay_pending = str(pending.get("capture_relay") or "")

                if service is not None and hasattr(service, "update_realized_gas_budget"):
                    service.update_realized_gas_budget(
                        self, gas_est_wei=gas_est_wei, decoded=decoded or {}
                    )
                realized_after = (
                    service.realized_after_wei(decoded or {})
                    if service is not None and hasattr(service, "realized_after_wei")
                    else 0
                )

                outcome_truth = (
                    service.settled_outcome_truth(status=status, decoded=decoded or {})
                    if service is not None and hasattr(service, "settled_outcome_truth")
                    else {"ok": True, "reason_code": "ok", "reason_codes": [], "verified": True}
                )

                if service is not None and hasattr(service, "record_trade_outcome"):
                    service.record_trade_outcome(
                        self,
                        status=status,
                        realized_after=realized_after,
                        expected_after=expected_after,
                        amount_in=amount_in,
                        latency_ms=latency_ms,
                        mode=mode,
                        outcome_truth_ok=bool(outcome_truth.get("ok", True)),
                        outcome_truth_reason_code=str(outcome_truth.get("reason_code") or "ok"),
                    )

                reward_trace = build_reward_trace(
                    amount_in_wei=amount_in,
                    expected_after_costs_wei=expected_after,
                    realized_after_gas_wei=int(max(0, realized_after)) if status == 1 else 0,
                    ok=(status == 1),
                    submit_to_receipt_ms=int(submit_to_receipt_ms),
                )

                if service is not None and hasattr(service, "record_capture_outcome"):
                    service.record_capture_outcome(
                        self,
                        route_id=route_id,
                        pending=pending,
                        status=status,
                        capture_lane_pending=capture_lane_pending,
                        capture_relay_pending=capture_relay_pending,
                        expected_after=expected_after,
                        realized_after=realized_after,
                        submit_to_receipt_ms=submit_to_receipt_ms,
                    )
                    service.update_decision_learning(
                        self,
                        route_id=route_id,
                        rl_state=rl_state,
                        rl_action=rl_action,
                        amount_in=amount_in,
                        expected_after=expected_after,
                        realized_after=realized_after,
                        status=status,
                        tx_hash=str(tx_hash),
                        mode=mode,
                        latency_ms=latency_ms,
                        submit_to_receipt_ms=submit_to_receipt_ms,
                        aqe_action=aqe_action,
                        pending=pending,
                        reward_trace=reward_trace,
                    )
                    service.audit_reward_trace(
                        self,
                        tx_hash=str(tx_hash),
                        mode=mode,
                        route_id=route_id,
                        status=status,
                        submit_to_receipt_ms=submit_to_receipt_ms,
                        realized_after=realized_after,
                        expected_after=expected_after,
                        reward_trace=reward_trace,
                    )
                    self._safe_finalize_receipt_side_effects(
                        service,
                        tx_hash=str(tx_hash),
                        receipt=receipt,
                        decoded=decoded,
                        pending=pending,
                        status=status,
                        submit_to_receipt_ms=submit_to_receipt_ms,
                        expected_after=expected_after,
                        realized_after=realized_after,
                        amount_in=amount_in,
                        gas_est_wei=gas_est_wei,
                        route_id=route_id,
                        reward_trace=reward_trace,
                        capture_lane_pending=capture_lane_pending,
                        capture_relay_pending=capture_relay_pending,
                        outcome_truth=dict(outcome_truth or {}),
                    )
            except _SAFE_RECEIPT_EXCEPTIONS as e:
                self._handle_receipt_loop_failure(
                    tx_hash=str(tx_hash),
                    error=e,
                    receipt_seen=bool(receipt),
                    pending_popped=bool(pending_popped),
                )
            finally:
                try:
                    self._receipt_q.task_done()
                except ValueError:
                    pass

    @staticmethod
    def _receipt_retry_count_from_pending(pending: dict) -> int:
        try:
            return max(0, int(pending.get("_receipt_retry_count") or 0))
        except (AttributeError, TypeError, ValueError):
            return 0

    def _handle_receipt_loop_failure(
        self,
        *,
        tx_hash: str,
        error: Any,
        receipt_seen: bool,
        pending_popped: bool,
    ) -> None:
        error_text = str(error or "receipt_processing_failed")
        try:
            self._errors.append(f"receipt_loop_error:{error_text}")
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        if pending_popped:
            return
        pending_map = getattr(self, "_pending", None)
        if pending_map is None or not hasattr(pending_map, "get"):
            return
        pending = pending_map.get(tx_hash)
        if not isinstance(pending, dict):
            return

        retry_count = self._receipt_retry_count_from_pending(pending) + 1
        now_ms = int(time.time() * 1000)
        pending["_receipt_retry_count"] = int(retry_count)
        pending["_receipt_retry_last_error"] = error_text
        pending["_receipt_retry_last_error_ts_ms"] = int(now_ms)
        pending["_receipt_retry_receipt_seen"] = bool(receipt_seen)
        pending["_receipt_retry_exhausted"] = False
        pending["_receipt_retry_state"] = "retrying"

        should_retry = (not bool(receipt_seen)) and retry_count < int(_RECEIPT_RETRY_LIMIT)
        if should_retry:
            try:
                self._receipt_q.put_nowait(str(tx_hash))
                return
            except asyncio.QueueFull:
                error_text = "receipt_retry_queue_full"
                try:
                    self._errors.append(f"receipt_loop_error:{error_text}")
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
                pending["_receipt_retry_last_error"] = error_text

        pending["_receipt_retry_exhausted"] = True
        pending["_receipt_retry_state"] = (
            "awaiting_manual_recovery" if bool(receipt_seen) else "retry_exhausted"
        )

    def _safe_finalize_receipt_side_effects(
        self,
        service: Any,
        *,
        tx_hash: str,
        receipt: Any,
        decoded: Any,
        pending: dict,
        status: int,
        submit_to_receipt_ms: int,
        expected_after: int,
        realized_after: int,
        amount_in: int,
        gas_est_wei: int,
        route_id: str,
        reward_trace: dict,
        capture_lane_pending: str,
        capture_relay_pending: str,
        outcome_truth: dict,
    ) -> None:
        self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="finalize_replay",
            critical=False,
            fn=service.finalize_replay,
            runtime=self,
            tx_hash=str(tx_hash),
            status=status,
            receipt=receipt if isinstance(receipt, dict) else {},
            decoded=dict(decoded or {}) if isinstance(decoded, dict) else {},
            reward_trace=dict(reward_trace or {}),
        )

        if hasattr(service, "observe_outcome_truth_health"):
            self._run_receipt_finalize_step(
                receipt_tx_hash=str(tx_hash),
                step="observe_outcome_truth_health",
                critical=False,
                fn=service.observe_outcome_truth_health,
                runtime=self,
                verified=bool((outcome_truth or {}).get("ok", True)),
                reason_code=str(
                    (outcome_truth or {}).get("reason_code") or "settled_profit_truth_unavailable"
                ),
            )

        if not bool((outcome_truth or {}).get("ok", True)):
            if hasattr(service, "record_outcome_truth_gap"):
                self._run_receipt_finalize_step(
                    receipt_tx_hash=str(tx_hash),
                    step="record_outcome_truth_gap",
                    critical=True,
                    fn=service.record_outcome_truth_gap,
                    runtime=self,
                    tx_hash=str(tx_hash),
                    route_id=route_id,
                    status=status,
                    reason_code=str(
                        (outcome_truth or {}).get("reason_code")
                        or "settled_profit_truth_unavailable"
                    ),
                    pending=pending,
                )
            elif hasattr(service, "synchronize_settlement_accounting"):
                self._run_receipt_finalize_step(
                    receipt_tx_hash=str(tx_hash),
                    step="synchronize_settlement_accounting",
                    critical=True,
                    fn=service.synchronize_settlement_accounting,
                    runtime=self,
                    tx_hash=str(tx_hash),
                    pending=pending,
                    decoded=decoded or {},
                    status=status,
                    amount_in=amount_in,
                    expected_after=expected_after,
                    realized_after=realized_after,
                    submit_to_receipt_ms=submit_to_receipt_ms,
                    route_id=route_id,
                    route_family=str(pending.get("route_family") or ""),
                    strategy_family=str(
                        pending.get("strategy_family") or pending.get("route_family") or ""
                    ),
                    capture_lane_pending=capture_lane_pending,
                    outcome_truth_verified=False,
                    outcome_truth_reason_code=str(
                        (outcome_truth or {}).get("reason_code")
                        or "settled_profit_truth_unavailable"
                    ),
                )
            self._run_receipt_finalize_step(
                receipt_tx_hash=str(tx_hash),
                step="observe_blockspace",
                critical=False,
                fn=service.observe_blockspace,
                runtime=self,
                status=status,
                realized_after=realized_after,
                decoded=decoded or {},
            )
            self._run_receipt_finalize_step(
                receipt_tx_hash=str(tx_hash),
                step="notify_narrative",
                critical=False,
                fn=service.notify_narrative,
                runtime=self,
                tx_hash=str(tx_hash),
                status=status,
                decoded=decoded or {},
                pending=pending,
            )
            return

        if hasattr(service, "synchronize_settlement_accounting"):
            settlement_ok, settlement_sync = self._run_receipt_finalize_step(
                receipt_tx_hash=str(tx_hash),
                step="synchronize_settlement_accounting",
                critical=True,
                fn=service.synchronize_settlement_accounting,
                runtime=self,
                tx_hash=str(tx_hash),
                pending=pending,
                decoded=decoded or {},
                status=status,
                amount_in=amount_in,
                expected_after=expected_after,
                realized_after=realized_after,
                submit_to_receipt_ms=submit_to_receipt_ms,
                route_id=route_id,
                route_family=str(pending.get("route_family") or ""),
                strategy_family=str(
                    pending.get("strategy_family") or pending.get("route_family") or ""
                ),
                capture_lane_pending=capture_lane_pending,
                outcome_truth_verified=True,
                outcome_truth_reason_code="ok",
            )
            if not settlement_ok:
                self._observe_receipt_finalize_critical_failure(
                    service,
                    tx_hash=str(tx_hash),
                    step="synchronize_settlement_accounting",
                )
                return
            if not isinstance(settlement_sync, dict):
                self._observe_receipt_finalize_critical_failure(
                    service,
                    tx_hash=str(tx_hash),
                    step="synchronize_settlement_accounting_invalid_payload",
                )
                return
            if not bool(settlement_sync.get("ok", False)):
                return
        else:
            self._record_receipt_finalize_failure(
                tx_hash=str(tx_hash),
                step="synchronize_settlement_accounting",
                error=AttributeError("canonical settlement sync unavailable"),
                critical=True,
            )
            self._observe_receipt_finalize_critical_failure(
                service,
                tx_hash=str(tx_hash),
                step="synchronize_settlement_accounting",
            )
            return

        persisted_ok, persisted = self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="persist_execution_outcome",
            critical=True,
            fn=service.persist_execution_outcome,
            runtime=self,
            pending=pending,
            status=status,
            submit_to_receipt_ms=submit_to_receipt_ms,
            realized_usd=service._realized_usd_from_wei(
                int(max(0, realized_after)) if status == 1 else 0
            ),
            expected_usd=service._realized_usd_from_wei(int(expected_after)),
            reward_trace=dict(reward_trace or {}),
            capture_lane_pending=capture_lane_pending,
        )
        if not persisted_ok:
            self._observe_receipt_finalize_critical_failure(
                service,
                tx_hash=str(tx_hash),
                step="persist_execution_outcome",
            )
            return
        if not isinstance(persisted, dict):
            self._observe_receipt_finalize_critical_failure(
                service,
                tx_hash=str(tx_hash),
                step="persist_execution_outcome_invalid_payload",
            )
            return

        route_family_pending = str(persisted.get("route_family") or "")
        strategy_family_pending = str(persisted.get("strategy_family") or "flashloan_atomic")
        realized_usd = float(persisted.get("realized_usd") or 0.0)
        expected_usd = float(persisted.get("expected_usd") or 0.0)

        learning_ok, _ = self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="update_execution_learning",
            critical=False,
            fn=service.update_execution_learning,
            runtime=self,
            pending=pending,
            status=status,
            realized_usd=realized_usd,
            expected_usd=expected_usd,
            route_family=route_family_pending,
            strategy_family=strategy_family_pending,
            capture_lane_pending=capture_lane_pending,
        )
        self._update_settlement_followthrough(learning_ok=learning_ok)
        memory_ok, _ = self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="observe_settlement_memory",
            critical=False,
            fn=service.observe_settlement_memory,
            runtime=self,
            pending=pending,
            status=status,
            submit_to_receipt_ms=submit_to_receipt_ms,
            realized_usd=realized_usd,
            expected_usd=expected_usd,
            gas_est_wei=gas_est_wei,
            route_family=route_family_pending,
            strategy_family=strategy_family_pending,
            route_id=route_id,
            tx_hash=str(tx_hash),
            capture_lane_pending=capture_lane_pending,
            capture_relay_pending=capture_relay_pending,
        )
        self._update_settlement_followthrough(memory_ok=memory_ok)
        self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="update_agent_performance",
            critical=False,
            fn=service.update_agent_performance,
            runtime=self,
            pending=pending,
            status=status,
            amount_in=amount_in,
            realized_after=realized_after,
        )
        self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="observe_blockspace",
            critical=False,
            fn=service.observe_blockspace,
            runtime=self,
            status=status,
            realized_after=realized_after,
            decoded=decoded or {},
        )
        self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="notify_governance",
            critical=False,
            fn=service.notify_governance,
            runtime=self,
            pending=pending,
            route_id=route_id,
            amount_in=amount_in,
            status=status,
            expected_after=expected_after,
            realized_after=realized_after,
        )
        self._run_receipt_finalize_step(
            receipt_tx_hash=str(tx_hash),
            step="notify_narrative",
            critical=False,
            fn=service.notify_narrative,
            runtime=self,
            tx_hash=str(tx_hash),
            status=status,
            decoded=decoded or {},
            pending=pending,
        )
