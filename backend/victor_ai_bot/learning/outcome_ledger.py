from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .borrowing_truth import BorrowingTruth, resolve_borrowing_truth

_SAFE_LEDGER_EXCEPTIONS = (OSError, sqlite3.Error, TypeError, ValueError)


@dataclass(frozen=True)
class LearningOutcome:
    """Canonical settled-trade learning record."""

    ledger_id: int
    ts: int
    chain: str
    opportunity_id: str
    route_id: str
    tx_hash: str
    mode: str
    ok: bool
    receipt_status: int
    amount_in_wei: int
    expected_profit_after_costs_wei: int
    estimated_gas_cost_wei: int
    flashloan_fee_wei: int
    realized_gas_cost_wei: int
    realized_profit_after_gas_wei: int
    realized_profit_token: str
    realized_profit_token_wei: int
    realized_gas_cost_in_profit_token_wei: int
    realized_profit_usd_micro: int
    realized_gas_cost_usd_micro: int
    realized_profit_after_gas_usd_micro: int
    strategy_type: str
    income_stream: str
    venue_path: str
    rl_state: str = ""
    rl_action_index: int = -1
    aqe_action: str = ""
    reward_scaled_ppm: int = 0
    reward_scaled_float: float = 0.0
    latency_ms: int = 0
    submit_to_receipt_ms: int = 0
    borrowing: BorrowingTruth = field(default_factory=BorrowingTruth)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledgerId": self.ledger_id,
            "ts": self.ts,
            "chain": self.chain,
            "opportunityId": self.opportunity_id,
            "routeId": self.route_id,
            "txHash": self.tx_hash,
            "mode": self.mode,
            "ok": self.ok,
            "receiptStatus": self.receipt_status,
            "amountInWei": str(self.amount_in_wei),
            "expectedProfitAfterCostsWei": str(self.expected_profit_after_costs_wei),
            "estimatedGasCostWei": str(self.estimated_gas_cost_wei),
            "flashloanFeeWei": str(self.flashloan_fee_wei),
            "realizedGasCostWei": str(self.realized_gas_cost_wei),
            "realizedProfitAfterGasWei": str(self.realized_profit_after_gas_wei),
            "realizedProfitToken": self.realized_profit_token,
            "realizedProfitTokenWei": str(self.realized_profit_token_wei),
            "realizedGasCostInProfitTokenWei": str(self.realized_gas_cost_in_profit_token_wei),
            "realizedProfitUsdMicro": str(self.realized_profit_usd_micro),
            "realizedGasCostUsdMicro": str(self.realized_gas_cost_usd_micro),
            "realizedProfitAfterGasUsdMicro": str(self.realized_profit_after_gas_usd_micro),
            "strategyType": self.strategy_type,
            "incomeStream": self.income_stream,
            "venuePath": self.venue_path,
            "rlState": self.rl_state,
            "rlActionIndex": self.rl_action_index,
            "aqeAction": self.aqe_action,
            "rewardScaledPpm": self.reward_scaled_ppm,
            "rewardScaledFloat": self.reward_scaled_float,
            "latencyMs": self.latency_ms,
            "submitToReceiptMs": self.submit_to_receipt_ms,
            "borrowing": self.borrowing.to_dict(),
            "context": dict(self.context),
        }


class CanonicalOutcomeLedger:
    """Read-only canonical outcome view backed by PnLStore's SQLite journal.

    Financial truth stays in the existing PnL store. OMAR reads this normalized
    view and joins the transaction-linked learning record by transaction hash.
    The live runtime is optional but, when bound, is used to resolve the exact
    internal-prime loan and its current lifecycle state.
    """

    def __init__(
        self,
        *,
        data_dir: str,
        chain: str,
        bootstrap_history: int = 500,
        runtime: Any | None = None,
    ):
        self.data_dir = str(data_dir or "")
        self.chain = str(chain or "")
        self.runtime = runtime
        self.pnl_path = os.path.join(self.data_dir, f"pnl_{self.chain}.sqlite")
        self.training_path = os.path.join(
            self.data_dir,
            "training",
            f"rl_training_{self.chain}.jsonl",
        )
        self.cursor_path = os.path.join(
            self.data_dir,
            "omar",
            f"outcome_cursor_{self.chain}.json",
        )
        self.bootstrap_history = max(1, int(bootstrap_history))
        self._seen: set[str] = set()
        self.last_error = ""
        self._load_cursor()

    def bind_runtime(self, runtime: Any | None) -> None:
        """Bind the live runtime without changing ledger ownership."""
        self.runtime = runtime

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value or default))
        except (TypeError, ValueError):
            return int(default)

    def _load_cursor(self) -> None:
        try:
            with open(self.cursor_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            seen = payload.get("seenTxHashes") if isinstance(payload, dict) else []
            if isinstance(seen, list):
                self._seen = {str(x) for x in seen if str(x)}
        except (OSError, ValueError, TypeError):
            self._seen = set()

    def _save_cursor(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.cursor_path), exist_ok=True)
            payload = {
                "schemaVersion": 1,
                "chain": self.chain,
                "updatedTs": int(time.time()),
                "seenTxHashes": sorted(self._seen)[-10000:],
            }
            tmp = f"{self.cursor_path}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.cursor_path)
        except (OSError, TypeError, ValueError):
            return

    def _training_context(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        try:
            with open(self.training_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(row, dict):
                        continue
                    tx_hash = str(row.get("tx_hash") or "")
                    if tx_hash:
                        out[tx_hash] = row
        except OSError:
            return out
        return out

    def _query_rows(self, limit: int) -> List[Dict[str, Any]]:
        if not os.path.exists(self.pnl_path):
            return []
        con = sqlite3.connect(self.pnl_path)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT * FROM trades WHERE receipt_status IS NOT NULL "
                "AND tx_hash IS NOT NULL AND tx_hash != '' "
                "ORDER BY id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            con.close()

    def _normalize(
        self,
        row: Dict[str, Any],
        training: Dict[str, Any],
    ) -> LearningOutcome:
        tx_hash = str(row.get("tx_hash") or "")
        receipt_status = self._int(row.get("receipt_status"), 0)
        training_extra = training.get("extra") if isinstance(training.get("extra"), dict) else {}
        brain = training_extra.get("brain") if isinstance(training_extra.get("brain"), dict) else {}
        amount_in = self._int(training.get("amount_in_wei"), 0)
        expected_after = self._int(row.get("expected_profit_after_costs_wei"), 0)
        realized_after = self._int(row.get("realized_profit_after_gas_wei"), 0)
        ok = receipt_status == 1
        denom = max(1, amount_in)
        realized_for_reward = realized_after if ok else 0
        penalty = 0 if ok else abs(expected_after)
        reward_num = realized_for_reward - penalty

        internal_prime_context = training_extra.get("internal_prime")
        if not isinstance(internal_prime_context, dict):
            internal_prime_context = training_extra.get("internalPrime")
        context = {
            "trainingTs": self._int(training.get("ts"), 0),
            "strategy": str(training_extra.get("strategy") or ""),
            "opportunityId": str(
                training_extra.get("opportunity_id") or row.get("opportunity_id") or ""
            ),
            "mode": str(training_extra.get("mode") or row.get("mode") or ""),
            "brain": dict(brain),
            "aqeDebug": (
                dict(training_extra.get("aqe_debug") or {})
                if isinstance(training_extra.get("aqe_debug"), dict)
                else {}
            ),
            "wealthGoal": (
                dict(training_extra.get("wealth_goal") or {})
                if isinstance(training_extra.get("wealth_goal"), dict)
                else {}
            ),
            "treasury": (
                dict(training_extra.get("treasury") or {})
                if isinstance(training_extra.get("treasury"), dict)
                else {}
            ),
            "governance": (
                dict(training_extra.get("governance") or {})
                if isinstance(training_extra.get("governance"), dict)
                else {}
            ),
            "capture": (
                dict(training_extra.get("capture") or {})
                if isinstance(training_extra.get("capture"), dict)
                else {}
            ),
            "capital": (
                dict(training_extra.get("capital") or {})
                if isinstance(training_extra.get("capital"), dict)
                else {}
            ),
            "internalPrime": (
                dict(internal_prime_context or {})
                if isinstance(internal_prime_context, dict)
                else {}
            ),
        }

        borrowing = resolve_borrowing_truth(
            runtime=self.runtime,
            pending={
                "pending_context": training_extra,
                "capital_admission": training_extra.get("capital_admission")
                or training_extra.get("capitalAdmission")
                or {},
                "loan_id": training_extra.get("loan_id") or training_extra.get("loanId") or "",
                "borrowing_truth": training_extra.get("borrowing_truth")
                or training_extra.get("borrowingTruth")
                or {},
            },
            outcome={
                "borrow_settled_usd": row.get("borrow_settled_usd"),
                "realized_borrow_cost_usd": row.get("realized_borrow_cost_usd"),
            },
        )
        context["borrowing"] = borrowing.to_dict()

        return LearningOutcome(
            ledger_id=self._int(row.get("id"), 0),
            ts=self._int(row.get("ts"), 0),
            chain=str(row.get("chain") or self.chain),
            opportunity_id=str(row.get("opportunity_id") or ""),
            route_id=str(row.get("route_id") or ""),
            tx_hash=tx_hash,
            mode=str(row.get("mode") or ""),
            ok=bool(ok),
            receipt_status=receipt_status,
            amount_in_wei=amount_in,
            expected_profit_after_costs_wei=expected_after,
            estimated_gas_cost_wei=self._int(row.get("estimated_gas_cost_wei"), 0),
            flashloan_fee_wei=self._int(row.get("flashloan_fee_wei"), 0),
            realized_gas_cost_wei=self._int(row.get("realized_gas_cost_wei"), 0),
            realized_profit_after_gas_wei=realized_after,
            realized_profit_token=str(row.get("realized_profit_token") or ""),
            realized_profit_token_wei=self._int(row.get("realized_profit_token_wei"), 0),
            realized_gas_cost_in_profit_token_wei=self._int(
                row.get("realized_gas_cost_in_profit_token_wei"), 0
            ),
            realized_profit_usd_micro=self._int(row.get("realized_profit_usd_micro"), 0),
            realized_gas_cost_usd_micro=self._int(row.get("realized_gas_cost_usd_micro"), 0),
            realized_profit_after_gas_usd_micro=self._int(
                row.get("realized_profit_after_gas_usd_micro"), 0
            ),
            strategy_type=str(row.get("strategy_type") or ""),
            income_stream=str(row.get("income_stream") or ""),
            venue_path=str(row.get("venue_path") or ""),
            rl_state=str(training.get("rl_state") or brain.get("state") or ""),
            rl_action_index=self._int(training.get("rl_action_index"), -1),
            aqe_action=str(training_extra.get("aqe_action") or ""),
            reward_scaled_ppm=reward_num * 1_000_000 // denom,
            reward_scaled_float=reward_num / float(denom) * 1_000_000.0,
            latency_ms=self._int(training_extra.get("latency_ms"), 0),
            submit_to_receipt_ms=self._int(training_extra.get("submit_to_receipt_ms"), 0),
            borrowing=borrowing,
            context=context,
        )

    def poll(self, *, limit: int = 50) -> List[LearningOutcome]:
        """Return newly settled outcomes, oldest first, without duplicates."""
        try:
            query_limit = max(1, int(limit))
            if not self._seen:
                query_limit = max(query_limit, self.bootstrap_history)
            rows = self._query_rows(query_limit)
            training = self._training_context()
            outcomes: List[LearningOutcome] = []
            for row in reversed(rows):
                tx_hash = str(row.get("tx_hash") or "")
                if not tx_hash or tx_hash in self._seen:
                    continue
                outcomes.append(self._normalize(row, training.get(tx_hash, {})))
                self._seen.add(tx_hash)
            if outcomes:
                self._save_cursor()
            self.last_error = ""
            return outcomes
        except _SAFE_LEDGER_EXCEPTIONS as exc:
            self.last_error = str(exc)
            return []

    def state(self) -> Dict[str, Any]:
        return {
            "ok": not bool(self.last_error),
            "chain": self.chain,
            "pnlPath": self.pnl_path,
            "trainingPath": self.training_path,
            "seenOutcomeCount": len(self._seen),
            "lastError": self.last_error,
            "capitalAuthorityBound": bool(self.runtime is not None),
        }
