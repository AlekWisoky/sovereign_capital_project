from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Mapping

from ..treasury.ledger import LedgerLine, LedgerTransaction, TreasuryLedger

_SAFE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class CapitalWriteService:
    handles_bankroll_outcome_mutation = True

    @staticmethod
    def _new_capital_commit_id(*, namespace: str) -> str:
        ns = str(namespace or "capital").strip().replace(" ", "_") or "capital"
        return f"{ns}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _annotate_capital_commit(
        payload: Dict[str, Any], *, capital_commit_id: str
    ) -> Dict[str, Any]:
        out = dict(payload or {})
        if capital_commit_id:
            out["capitalCommitId"] = str(capital_commit_id)
            out["capital_write_boundary"] = "universal_capital_write_v1"
        return out

    def commit_internal_prime_open(
        self,
        prime: Any,
        *,
        transition: Mapping[str, Any],
    ) -> Dict[str, Any]:
        db = getattr(prime, "_db", None)
        ledger_repo = getattr(prime, "_ledger_repo", None)
        state_repo = getattr(prime, "_state_repo", None)
        capital_event_repo = getattr(prime, "_capital_event_repo", None)
        ledger = getattr(prime, "_ledger", None)
        if db is None or ledger_repo is None or state_repo is None or ledger is None:
            raise RuntimeError("internal_prime_open_dependencies_unavailable")

        transition_dict = dict(transition or {})
        capital_commit_id = self._new_capital_commit_id(namespace="prime-open")
        if not bool(transition_dict.get("ok", False)):
            return transition_dict
        loan = self._safe_dict(transition_dict.get("loan"))
        state_snapshot = self._annotate_capital_commit(
            self._safe_dict(transition_dict.get("state_snapshot")),
            capital_commit_id=capital_commit_id,
        )
        journal_tx = self._safe_dict(transition_dict.get("journal_tx"))
        journal_tx["metadata"] = self._annotate_capital_commit(
            self._safe_dict(journal_tx.get("metadata")),
            capital_commit_id=capital_commit_id,
        )
        event_type = str(transition_dict.get("event_type") or "prime_state")
        tx_ts_ms = int(
            journal_tx.get("ts_ms")
            or state_snapshot.get("updatedTsMs")
            or state_snapshot.get("updated_ts_ms")
            or int(time.time() * 1000)
        )

        with db.connect() as conn:
            ledger_repo.append_transaction(
                chain=str(getattr(prime, "chain", "") or ""),
                payload=dict(journal_tx),
                conn=conn,
                publish_capital_event=True,
            )
            state_repo.append_snapshot(
                ts_ms=int(
                    state_snapshot.get("updatedTsMs")
                    or state_snapshot.get("updated_ts_ms")
                    or tx_ts_ms
                ),
                state_type=str(event_type or "prime_state"),
                payload=dict(state_snapshot),
                conn=conn,
            )
            if capital_event_repo is not None and hasattr(capital_event_repo, "append_event"):
                capital_event_repo.append_event(
                    ts_ms=int(
                        state_snapshot.get("updatedTsMs")
                        or state_snapshot.get("updated_ts_ms")
                        or tx_ts_ms
                    ),
                    domain="internal_prime",
                    event_type=str(event_type or "prime_state"),
                    source="capital_write_service",
                    transaction_id=str(journal_tx.get("transaction_id") or ""),
                    receipt_id=str(journal_tx.get("receipt_id") or ""),
                    entity_id=str(loan.get("loan_id") or "internal_prime_state"),
                    payload=dict(state_snapshot),
                    conn=conn,
                )

        try:
            ledger.write_transaction(self._ledger_tx_from_payload(journal_tx))
        except _SAFE_EXCEPTIONS:
            pass
        if hasattr(prime, "adopt_state_payload"):
            try:
                prime.adopt_state_payload(dict(state_snapshot), persist_mirror=True)
            except _SAFE_EXCEPTIONS:
                pass
        return {
            "ok": True,
            "reason_code": "ok",
            "loan": dict(loan),
            "ledgerTransaction": dict(journal_tx),
            "state_snapshot": dict(state_snapshot),
            "event_type": str(event_type or "prime_state"),
            "utilization": float(transition_dict.get("utilization") or 0.0),
            "capital_commit_id": str(capital_commit_id),
        }

    @staticmethod
    def _chain(runtime: Any) -> str:
        return str(getattr(getattr(getattr(runtime, "cfg", None), "chain", None), "name", "") or "")

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return dict(value or {}) if isinstance(value, Mapping) else {}

    @staticmethod
    def _ledger_tx_from_payload(payload: Mapping[str, Any]) -> LedgerTransaction:
        tx_payload = dict(payload or {})
        return LedgerTransaction(
            transaction_id=str(tx_payload.get("transaction_id") or ""),
            ts_ms=int(tx_payload.get("ts_ms") or 0),
            tx_type=str(tx_payload.get("tx_type") or ""),
            chain=str(tx_payload.get("chain") or ""),
            receipt_id=str(tx_payload.get("receipt_id") or ""),
            lines=[LedgerLine(**dict(line)) for line in list(tx_payload.get("lines") or [])],
            metadata=dict(tx_payload.get("metadata") or {}),
        )

    def commit_receipt_settlement(
        self,
        runtime: Any,
        *,
        tx_payload: Mapping[str, Any],
        tx_lines: list[dict[str, Any]] | None,
        receipt_id: str,
        status: int,
        amount_in: int,
        submit_to_receipt_ms: int,
        route_id: str,
        route_family: str,
        strategy_family: str,
        capture_lane_pending: str,
        realized_after_usd: float,
        borrow_cost_usd: float,
        net_realized_usd: float,
        gas_cost_wei: int,
        profitability_chain: Mapping[str, Any],
        borrowing: Mapping[str, Any],
        loan_result: Mapping[str, Any],
        outcome_truth_verified: bool,
        prime_transition: Mapping[str, Any] | None = None,
    ) -> Dict[str, Any]:
        db = getattr(runtime, "_db", None)
        ledger_repo = getattr(runtime, "_ledger_repo", None)
        capital_event_repo = getattr(runtime, "_capital_event_repo", None)
        bankroll = getattr(runtime, "_bankroll", None)
        bankroll_history_repo = getattr(runtime, "_bankroll_history_repo", None)
        treasury = getattr(runtime, "_treasury", None)
        treasury_state_repo = (
            getattr(treasury, "_state_repo", None) if treasury is not None else None
        )
        prime = getattr(runtime, "_internal_prime", None)
        internal_prime_state_repo = (
            getattr(prime, "_state_repo", None) if prime is not None else None
        )
        ledger = getattr(runtime, "_ledger", None)
        if db is None or ledger_repo is None or capital_event_repo is None or ledger is None:
            raise RuntimeError("capital_write_dependencies_unavailable")

        tx_payload_dict = dict(tx_payload or {})
        capital_commit_id = self._new_capital_commit_id(namespace="receipt-settlement")
        tx_payload_dict["metadata"] = self._annotate_capital_commit(
            self._safe_dict(tx_payload_dict.get("metadata")),
            capital_commit_id=capital_commit_id,
        )
        tx_ts_ms = int(tx_payload_dict.get("ts_ms") or int(time.time() * 1000))
        tx_transaction_id = str(tx_payload_dict.get("transaction_id") or "")
        chain = self._chain(runtime)
        success = bool(int(status) == 1)
        prime_transition_dict = dict(prime_transition or {})
        prime_state_snapshot = self._annotate_capital_commit(
            self._safe_dict(prime_transition_dict.get("state_snapshot")),
            capital_commit_id=capital_commit_id,
        )
        prime_journal_tx = self._safe_dict(prime_transition_dict.get("journal_tx"))
        if prime_journal_tx:
            prime_journal_tx["metadata"] = self._annotate_capital_commit(
                self._safe_dict(prime_journal_tx.get("metadata")),
                capital_commit_id=capital_commit_id,
            )
        prime_event_type = str(prime_transition_dict.get("event_type") or "prime_state")

        bankroll_state_payload: Dict[str, Any] | None = None
        if (
            outcome_truth_verified
            and bankroll is not None
            and hasattr(bankroll, "project_trade_state")
        ):
            bankroll_state_payload = dict(
                bankroll.project_trade_state(
                    success=success,
                    realized_profit_after_gas_wei=(
                        int(tx_payload_dict.get("metadata", {}).get("realized_after_gas_wei") or 0)
                        if success
                        else 0
                    ),
                    amount_in_wei=int(amount_in),
                )
                or {}
            )

        treasury_meta: Dict[str, Any] = {}
        treasury_snapshot: Dict[str, Any] = {}
        if treasury is not None and hasattr(treasury, "cfg"):
            treasury_meta = dict(getattr(getattr(treasury, "cfg", None), "meta", {}) or {})
            treasury_meta["rolling_gas_cost_wei"] = int(
                treasury_meta.get("rolling_gas_cost_wei") or 0
            ) + int(gas_cost_wei)
            treasury_meta["rolling_failures"] = int(treasury_meta.get("rolling_failures") or 0) + (
                0 if success else 1
            )
            treasury_meta["turnover_count"] = int(treasury_meta.get("turnover_count") or 0) + 1
            treasury_meta["last_settlement_receipt_id"] = str(receipt_id)
            treasury_meta["last_settlement_status"] = "settled" if success else "failed"
            treasury_meta["last_settlement_route_id"] = str(route_id)
            treasury_meta["last_settlement_route_family"] = str(route_family)
            treasury_meta["last_settlement_strategy_family"] = str(strategy_family)
            treasury_meta["last_settlement_submit_to_receipt_ms"] = int(submit_to_receipt_ms)
            treasury_meta["last_settlement_realized_after_gas_usd"] = round(
                float(realized_after_usd), 6
            )
            treasury_meta["last_settlement_borrow_cost_usd"] = round(float(borrow_cost_usd), 6)
            treasury_meta["last_settlement_net_usd"] = round(float(net_realized_usd), 6)
            treasury_meta["last_settlement_borrowing_source"] = str(borrowing.get("source") or "")
            treasury_meta["last_settlement_flashloan_provider"] = str(
                borrowing.get("provider") or ""
            )
            treasury_meta["last_settlement_flashloan_fee_wei"] = int(
                borrowing.get("flashloanFeeWei") or 0
            )
            terminal_authority = self._safe_dict(
                (profitability_chain or {}).get("terminalProfitabilityAuthority")
            )
            terminal_profitability = self._safe_dict(
                (profitability_chain or {}).get("terminalProfitability")
            )
            treasury_meta["last_settlement_terminal_profitability_stage"] = str(
                terminal_authority.get("stage") or ""
            )
            treasury_meta["last_settlement_terminal_profitability_reason"] = str(
                terminal_authority.get("reason") or ""
            )
            treasury_meta["last_settlement_terminal_profitability_authoritative"] = bool(
                terminal_authority.get("authoritative", False)
            )
            treasury_meta["last_settlement_terminal_profitability_live_gas_derived"] = bool(
                terminal_authority.get("live_gas_derived", False)
            )
            treasury_meta["last_settlement_terminal_profitability_after_costs_wei"] = int(
                terminal_profitability.get("profit_after_costs_wei") or 0
            )
            treasury_meta["last_settlement_terminal_profitability_authority"] = dict(
                terminal_authority
            )
            treasury_meta["last_settlement_terminal_profitability"] = dict(terminal_profitability)
            treasury_meta["last_settlement_capital_admission"] = self._safe_dict(
                (profitability_chain or {}).get("capitalAdmission")
            )
            treasury_meta["last_settlement_profitability_chain"] = dict(profitability_chain or {})
            if bankroll is not None and hasattr(bankroll, "cfg"):
                treasury_meta["auto_reinvest_enabled"] = bool(
                    getattr(bankroll.cfg, "auto_reinvest_enabled", False)
                )
            post_bankroll = bankroll_state_payload or {
                "realized_profit_wei": int(
                    getattr(getattr(bankroll, "state", None), "realized_profit_wei", 0) or 0
                ),
                "last_amount_in_wei": int(amount_in or 0),
                "success_streak": int(
                    getattr(getattr(bankroll, "state", None), "success_streak", 0) or 0
                ),
                "fail_streak": int(
                    getattr(getattr(bankroll, "state", None), "fail_streak", 0) or 0
                ),
                "updated_ts_ms": int(
                    getattr(getattr(bankroll, "state", None), "updated_ts_ms", 0) or 0
                ),
                "profit_updated_ts_ms": int(
                    getattr(getattr(bankroll, "state", None), "profit_updated_ts_ms", 0) or 0
                ),
                "sizing_updated_ts_ms": int(
                    getattr(getattr(bankroll, "state", None), "sizing_updated_ts_ms", 0) or 0
                ),
            }
            base_borrow = int(
                getattr(getattr(bankroll, "cfg", None), "base_borrow_amount_wei", 0) or 0
            )
            next_amount = int(post_bankroll.get("last_amount_in_wei") or 0)
            estimated_capital = max(
                int(treasury_meta.get("estimated_capital_wei") or 0),
                int(post_bankroll.get("realized_profit_wei") or 0) + max(base_borrow, next_amount),
            )
            if estimated_capital > 0:
                treasury_meta["estimated_capital_wei"] = int(estimated_capital)
                if int(amount_in) > 0:
                    treasury_meta["utilization_rate"] = round(
                        max(0.0, min(1.0, float(int(amount_in)) / float(int(estimated_capital)))), 6
                    )
            treasury_meta["capitalCommitId"] = str(capital_commit_id)
            treasury_meta["last_realized_profit_wei"] = int(
                post_bankroll.get("realized_profit_wei") or 0
            )
            treasury.cfg.meta = dict(treasury_meta)
            if hasattr(treasury, "pre_select_strategy"):
                treasury_snapshot = dict(
                    treasury.pre_select_strategy(
                        bankroll_state=dict(post_bankroll),
                        volatility_regime=str(
                            (getattr(runtime, "_market_regime", {}) or {}).get("regime")
                            or "balanced"
                        ),
                        persist=False,
                    )
                    or {}
                )
            if treasury_snapshot:
                treasury_snapshot["terminalProfitabilityAuthority"] = self._safe_dict(
                    (profitability_chain or {}).get("terminalProfitabilityAuthority")
                )
                treasury_snapshot["terminalProfitability"] = self._safe_dict(
                    (profitability_chain or {}).get("terminalProfitability")
                )
                treasury_snapshot["capitalAdmission"] = self._safe_dict(
                    (profitability_chain or {}).get("capitalAdmission")
                )
                treasury_snapshot["profitabilityChain"] = dict(profitability_chain or {})

        if bankroll_state_payload:
            bankroll_state_payload = self._annotate_capital_commit(
                bankroll_state_payload, capital_commit_id=capital_commit_id
            )
        if treasury_snapshot:
            treasury_snapshot = self._annotate_capital_commit(
                treasury_snapshot, capital_commit_id=capital_commit_id
            )

        with db.connect() as conn:
            ledger_repo.append_transaction(
                chain=chain, payload=tx_payload_dict, conn=conn, publish_capital_event=True
            )
            if bankroll_state_payload and bankroll_history_repo is not None:
                bankroll_history_repo.append_event(
                    ts_ms=int(bankroll_state_payload.get("updated_ts_ms") or tx_ts_ms),
                    event_type="trade_recorded",
                    state=dict(bankroll_state_payload),
                    payload={
                        "success": bool(success),
                        "receipt_id": str(receipt_id),
                        "transaction_id": str(tx_transaction_id),
                        "source": "capital_write_service",
                        "capitalCommitId": str(capital_commit_id),
                    },
                    conn=conn,
                )
                capital_event_repo.append_event(
                    ts_ms=int(bankroll_state_payload.get("updated_ts_ms") or tx_ts_ms),
                    domain="bankroll",
                    event_type="trade_recorded",
                    source="capital_write_service",
                    transaction_id=str(tx_transaction_id),
                    receipt_id=str(receipt_id),
                    entity_id="bankroll_state",
                    payload={
                        "state": dict(bankroll_state_payload),
                        "source": "receipt_settlement",
                        "capitalCommitId": str(capital_commit_id),
                    },
                    conn=conn,
                )
            if treasury_snapshot and treasury_state_repo is not None:
                treasury_state_repo.append_snapshot(
                    ts_ms=int(treasury_snapshot.get("updated_ts_ms") or tx_ts_ms),
                    state_type="capital_snapshot",
                    payload=dict(treasury_snapshot),
                    conn=conn,
                )
                capital_event_repo.append_event(
                    ts_ms=int(treasury_snapshot.get("updated_ts_ms") or tx_ts_ms),
                    domain="treasury",
                    event_type="capital_snapshot",
                    source="capital_write_service",
                    transaction_id=str(tx_transaction_id),
                    receipt_id=str(receipt_id),
                    entity_id="treasury_runtime",
                    payload=dict(treasury_snapshot),
                    conn=conn,
                )
            if prime_journal_tx:
                ledger_repo.append_transaction(
                    chain=chain,
                    payload=dict(prime_journal_tx),
                    conn=conn,
                    publish_capital_event=True,
                )
            if prime_state_snapshot and internal_prime_state_repo is not None:
                internal_prime_state_repo.append_snapshot(
                    ts_ms=int(
                        prime_state_snapshot.get("updatedTsMs")
                        or prime_state_snapshot.get("updated_ts_ms")
                        or tx_ts_ms
                    ),
                    state_type=str(prime_event_type or "prime_state"),
                    payload=dict(prime_state_snapshot),
                    conn=conn,
                )
                capital_event_repo.append_event(
                    ts_ms=int(
                        prime_state_snapshot.get("updatedTsMs")
                        or prime_state_snapshot.get("updated_ts_ms")
                        or tx_ts_ms
                    ),
                    domain="internal_prime",
                    event_type=str(prime_event_type or "prime_state"),
                    source="capital_write_service",
                    transaction_id=str(tx_transaction_id),
                    receipt_id=str(receipt_id),
                    entity_id=str(
                        dict(prime_journal_tx.get("metadata") or {}).get("loanId")
                        or "internal_prime_state"
                    ),
                    payload=dict(prime_state_snapshot),
                    conn=conn,
                )
            elif prime_journal_tx:
                capital_event_repo.append_event(
                    ts_ms=int(prime_journal_tx.get("ts_ms") or tx_ts_ms),
                    domain="internal_prime",
                    event_type=str(prime_journal_tx.get("tx_type") or "prime_state"),
                    source="capital_write_service",
                    transaction_id=str(tx_transaction_id),
                    receipt_id=str(receipt_id),
                    entity_id=str(
                        dict(prime_journal_tx.get("metadata") or {}).get("loanId")
                        or "internal_prime_state"
                    ),
                    payload={"journal_tx": dict(prime_journal_tx)},
                    conn=conn,
                )
            capital_event_repo.append_event(
                ts_ms=int(tx_ts_ms),
                domain="receipt",
                event_type="settlement_recorded" if success else "settlement_failed",
                source="capital_write_service",
                transaction_id=str(tx_transaction_id),
                receipt_id=str(receipt_id),
                entity_id=str(route_id or receipt_id),
                payload={
                    "capitalCommitId": str(capital_commit_id),
                    "ts_ms": int(tx_ts_ms),
                    "status": "settled" if success else "failed",
                    "route_id": str(route_id),
                    "route_family": str(route_family),
                    "strategy_family": str(strategy_family),
                    "capture_lane": str(capture_lane_pending or ""),
                    "realized_after_gas_usd": round(float(realized_after_usd), 6),
                    "borrow_cost_usd": round(float(borrow_cost_usd), 6),
                    "net_realized_usd": round(float(net_realized_usd), 6),
                    "loan_settlement": dict(loan_result or {}),
                },
                conn=conn,
            )

        try:
            ledger.write_transaction(self._ledger_tx_from_payload(tx_payload_dict))
        except _SAFE_EXCEPTIONS:
            pass
        if prime_journal_tx and prime is not None and hasattr(prime, "_ledger"):
            try:
                prime._ledger.write_transaction(self._ledger_tx_from_payload(prime_journal_tx))
            except _SAFE_EXCEPTIONS:
                pass
        if (
            bankroll_state_payload
            and bankroll is not None
            and hasattr(bankroll, "apply_state_payload")
        ):
            try:
                bankroll.apply_state_payload(dict(bankroll_state_payload))
            except _SAFE_EXCEPTIONS:
                pass
        if treasury is not None and hasattr(treasury, "cfg"):
            try:
                treasury.cfg.meta = dict(treasury_meta)
                if treasury_snapshot and hasattr(treasury, "adopt_snapshot"):
                    treasury.adopt_snapshot(dict(treasury_snapshot), persist_mirror=True)
            except _SAFE_EXCEPTIONS:
                pass
        if prime_state_snapshot and prime is not None and hasattr(prime, "adopt_state_payload"):
            try:
                prime.adopt_state_payload(dict(prime_state_snapshot), persist_mirror=True)
            except _SAFE_EXCEPTIONS:
                pass
        return {
            "transaction_id": str(tx_transaction_id),
            "ledger_entries": TreasuryLedger.projected_entry_rows([dict(tx_payload_dict)]),
            "treasury_snapshot": dict(treasury_snapshot or {}),
            "bankroll_state": dict(bankroll_state_payload or {}),
            "prime_result": dict(prime_transition_dict or {}),
            "capital_commit_id": str(capital_commit_id),
        }
