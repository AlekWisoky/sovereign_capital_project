from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


_SAFE_LEDGER_EXCEPTIONS = (OSError, sqlite3.Error, TypeError, ValueError)


@dataclass(frozen=True)
class LearningOutcome:
    """Canonical settled-trade learning record.

    The PnL SQLite store remains the source of truth for execution outcomes.
    This object is a normalized read model for learning consumers such as OMAR;
    it deliberately does not create a second financial ledger.
    """

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
            "context": dict(self.context),
        }


class CanonicalOutcomeLedger:
    """Read-only canonical outcome ledger backed by PnLStore's SQLite journal.

    OMAR consumes this interface instead of reading execution logs directly.
    The ledger joins finalized PnL rows with the existing RL training record by
    transaction hash, so decision context and realized outcome stay linked.
    """

    def __init__(self, *, data_dir: str, chain: str, bootstrap_history: int = 500):
        self.data_dir = str(data_dir or "")
        self.chain = str(chain or "")
        self.pnl_path = os.path.join(self.data_dir, f"pnl_{self.chain}.sqlite")
        self.training_path = os.path.join(
            self.data_dir, "training", f"rl_training_{self.chain}.jsonl"
        )
        self.cursor_path = os.path.join(
            self.data_dir, "omar", f"outcome_cursor_{self.chain}.json"
        )
        self.bootstrap_history = max(1, int(bootstrap_history))
        self._seen: set[str] = set()
        self._loaded = False
        self.last_error = ""
        self._load_cursor()

    @staticmethod
    def _int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value or default))
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return float(default)

    def _load_cursor(self) -> None:
        if self._loaded:
            return
        self._loaded = True
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

    def _normalize(self, row: Dict[str, Any], training: Dict[str, Any]) -> LearningOutcome:
        tx_hash = str(row.get("tx_hash") or "")
        receipt_status = self._int(row.get("receipt_status"), 0)
        amount_in = self._int(row.get("expected_gross_profit_wei"), 0)
        expected_after = self._int(row.get("expected_profit_after_costs_wei"), 0)
        realized_after = self._int(row.get("realized_profit_after_gas_wei"), 0)
        ok = receipt_status == 1 and realized_after >= 0

        extra = training.get("extra") if isinstance(training.get("extra"), dict) else {}
        brain = extra.get("brain") if isinstance(extra.get("brain"), dict) else {}
        context = {
            "trainingTs": self._int(training.get("ts"), 0),
            "strategy": str(extra.get("strategy") or ""),
            "opportunityId": str(extra.get("opportunity_id") or row.get("opportunity_id") or ""),
            "mode": str(extra.get("mode") or row.get("mode") or ""),
            "brain": dict(brain),
            "aqeDebug": dict(extra.get("aqe_debug") or {})
            if isinstance(extra.get("aqe_debug"), dict)
            else {},
            "wealthGoal": dict(extra.get("wealth_goal") or {})
            if isinstance(extra.get("wealth_goal"), dict)
            else {},
            "treasury": dict(extra.get("treasury") or {})
            if isinstance(extra.get("treasury"), dict)
            else {},
            "governance": dict(extra.get("governance") or {})
            if isinstance(extra.get("governance"), dict)
            else {},
            "capture": dict(extra.get("capture") or {})
            if isinstance(extra.get("capture"), dict)
            else {},
        }

        denom = max(1, amount_in)
        realized_for_reward = realized_after if receipt_status == 1 else 0
        penalty = 0 if receipt_status == 1 else abs(expected_after)
        reward_num = realized_for_reward - penalty
        reward_scaled_ppm = reward_num * 1_000_000 // denom
        reward_scaled_float = reward_num / float(denom) * 1_000_000.0

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
            rl_action_index=self._int(
                training.get("rl_action_index"),
            ),
            aqe_action=str(training.get("extra", {}).get("aqe_action") or "")
            if isinstance(training.get("extra"), dict)
            else "",
            reward_scaled_ppm=reward_scaled_ppm,
            reward_scaled_float=reward_scaled_float,
            latency_ms=self._int(training.get("extra", {}).get("latency_ms"), 0)
            if isinstance(training.get("extra"), dict)
            else 0,
            submit_to_receipt_ms=self._int(training.get("extra", {}).get("submit_to_receipt_ms"), 0)
            if isinstance(training.get("extra"), dict)
            else 0,
            context=context,
        )

    def poll(self, *, limit: int = 50) -> List[LearningOutcome]:
        """Return newly settled outcomes, newest first, without duplicates."""
        try:
            rows = self._query_rows(max(1, int(limit)))
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
        }
