from __future__ import annotations

import sqlite3
from typing import Any, Dict

from ..jsonsafe import to_json_safe
from ..capital_family_policy import FAMILY_CAPITAL_PLAN_VERSION, resolve_family_target
from ..persistence.repositories.capital_recovery_repository import CapitalRecoveryRepository
from ..treasury.reconciliation import reconcile_internal_prime_journal
from .capital_truth_dependency_reads import (
    has_bankroll_history as kernel_has_bankroll_history,
    has_capital_event_bus as kernel_has_capital_event_bus,
    has_internal_prime_state_history as kernel_has_internal_prime_state_history,
    has_treasury_state_history as kernel_has_treasury_state_history,
    read_all_ledger_transactions as kernel_read_all_ledger_transactions,
    read_bankroll_history_event as kernel_read_bankroll_history_event,
    read_capital_event as kernel_read_capital_event,
    read_internal_prime_state_history_snapshot as kernel_read_internal_prime_state_history_snapshot,
    read_ledger_account_balances as kernel_read_ledger_account_balances,
    read_ledger_accounting as kernel_read_ledger_accounting,
    read_ledger_balances as kernel_read_ledger_balances,
    read_ledger_tail as kernel_read_ledger_tail,
    read_treasury_history_snapshot as kernel_read_treasury_history_snapshot,
    safe_call as kernel_safe_call,
)
from .capital_truth_service_shell import summarize_capital_truth
from .capital_truth_source_snapshot import (
    bankroll_ts_ms as kernel_bankroll_ts_ms,
    build_capital_truth_source_snapshots,
    capital_commit_id_from_payload as kernel_capital_commit_id_from_payload,
    capital_engine_ts_ms as kernel_capital_engine_ts_ms,
    freshness_class as kernel_freshness_class,
    internal_prime_ts_ms as kernel_internal_prime_ts_ms,
    max_ts_ms as kernel_max_ts_ms,
    normalize_ts_ms as kernel_normalize_ts_ms,
    state_field_mismatches as kernel_state_field_mismatches,
)


class CapitalTruthService:
    """Canonical read path for platform capital truth.

    The service intentionally stays off the hot path. It reconciles the platform's
    operator-facing capital state from the existing institutional sources:
    treasury/capital engine, bankroll realized profit, ledger, internal prime,
    and launch family allocations.
    """

    @staticmethod
    def _int_like(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float_like(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_call(obj: Any, method: str, default: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return kernel_safe_call(obj, method, default)

    def _ledger_tail(self, runtime: Any) -> list[Dict[str, Any]]:
        return kernel_read_ledger_tail(runtime)

    def _ledger_balances(self, runtime: Any) -> Dict[str, Any]:
        return kernel_read_ledger_balances(runtime)

    def _ledger_account_balances(self, runtime: Any) -> Dict[str, Dict[str, Any]]:
        return kernel_read_ledger_account_balances(runtime)

    def _ledger_accounting(self, runtime: Any) -> Dict[str, Any]:
        return kernel_read_ledger_accounting(runtime)

    def _open_loan_asset_exposure(self, internal_prime_state: Dict[str, Any]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for loan in list(internal_prime_state.get("openLoans") or []) + list(
            internal_prime_state.get("disputedLoans") or []
        ):
            if not isinstance(loan, dict):
                continue
            asset = str(loan.get("asset") or "")
            if not asset:
                continue
            exposure = self._float_like(loan.get("collateral_reserved_usd"))
            if exposure <= 0.0:
                exposure = self._float_like(loan.get("notional_usd"))
            out[asset] = round(out.get(asset, 0.0) + exposure, 8)
        return out

    def _account_balance_asset(
        self, account_balances: Dict[str, Dict[str, Any]], account: str, asset: str
    ) -> float:
        return self._float_like(dict(account_balances.get(str(account)) or {}).get(str(asset)))

    def _mapping_floats(self, payload: Any) -> Dict[str, float]:
        return {str(k): round(self._float_like(v), 8) for k, v in dict(payload or {}).items()}

    def _append_reason(self, reasons: list[str], reason: str) -> None:
        reason_text = str(reason or "")
        if reason_text and reason_text not in reasons:
            reasons.append(reason_text)

    @staticmethod
    def _capital_recovery_repo(runtime: Any) -> CapitalRecoveryRepository | None:
        repo = getattr(runtime, "_capital_recovery_repo", None)
        if repo is not None:
            return repo
        db = getattr(runtime, "_db", None)
        if db is None:
            return None
        try:
            chain_cfg = getattr(getattr(runtime, "cfg", None), "chain", None)
            chain = str(getattr(chain_cfg, "name", None) or "default")
            repo = CapitalRecoveryRepository(db, chain=chain)
            runtime._capital_recovery_repo = repo
            return repo
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            return None

    def _capital_recovery_state(self, runtime: Any, *, component: str) -> Dict[str, Any]:
        repo = self._capital_recovery_repo(runtime)
        if repo is None:
            return {}
        try:
            payload = repo.load(component=str(component))
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            return {}
        return dict(payload or {}) if isinstance(payload, dict) else {}

    def _internal_prime_ledger_reconciliation(
        self,
        *,
        internal_prime_state: Dict[str, Any],
        account_balances: Dict[str, Dict[str, Any]],
        accounting: Dict[str, Any],
    ) -> Dict[str, Any]:
        ledger_borrowed_usd = round(
            self._account_balance_asset(account_balances, "internal_prime:borrowed_usd", "USD"), 8
        )
        encumbered_assets = self._mapping_floats(accounting.get("encumberedAssets") or {})
        open_loan_asset_exposure = self._open_loan_asset_exposure(internal_prime_state)
        prime_state_borrowed_usd = round(
            self._float_like(internal_prime_state.get("borrowedUsd")), 8
        )
        reasons: list[str] = []
        if abs(ledger_borrowed_usd - prime_state_borrowed_usd) > 1e-6:
            self._append_reason(reasons, "internal_prime_ledger_borrowed_mismatch")
        all_assets = sorted(set(encumbered_assets) | set(open_loan_asset_exposure))
        asset_deltas = {
            asset: round(
                float(encumbered_assets.get(asset, 0.0))
                - float(open_loan_asset_exposure.get(asset, 0.0)),
                8,
            )
            for asset in all_assets
        }
        if any(abs(delta) > 1e-6 for delta in asset_deltas.values()):
            self._append_reason(reasons, "internal_prime_ledger_encumbrance_mismatch")
        return {
            "ok": not reasons,
            "reasons": reasons,
            "ledger_borrowed_usd": ledger_borrowed_usd,
            "state_borrowed_usd": prime_state_borrowed_usd,
            "encumbered_assets": encumbered_assets,
            "open_loan_asset_exposure": open_loan_asset_exposure,
            "asset_deltas": asset_deltas,
        }

    def _all_ledger_transactions(self, runtime: Any) -> list[Dict[str, Any]]:
        return kernel_read_all_ledger_transactions(runtime)

    def _ledger_transactions(self, runtime: Any) -> list[Dict[str, Any]]:
        return [
            dict(row)
            for row in self._all_ledger_transactions(runtime)
            if isinstance(row, dict) and str(row.get("tx_type") or "").startswith("prime_loan_")
        ]

    def _pnl_receipt_rows(self, runtime: Any) -> list[Dict[str, Any]]:
        store = getattr(runtime, "_pnl", None)
        path = str(getattr(store, "path", "") or "")
        if not path:
            return []
        try:
            con = sqlite3.connect(path)
            con.row_factory = sqlite3.Row
            try:
                rows = con.execute(
                    "SELECT tx_hash, receipt_status, realized_profit_after_gas_wei, realized_profit_token, realized_profit_token_wei, realized_profit_after_gas_usd_micro, ts FROM trades WHERE tx_hash IS NOT NULL AND tx_hash <> '' AND receipt_status IS NOT NULL ORDER BY ts ASC, id ASC"
                ).fetchall()
            finally:
                con.close()
        except (sqlite3.Error, OSError, RuntimeError, TypeError, ValueError):
            return []
        return [dict(row) for row in rows]

    def _withdraw_history(self, runtime: Any) -> Dict[str, Any]:
        def _normalize_outcome(raw: Any) -> str:
            outcome = str(raw or "").strip()
            if outcome in {"pending", "sent", "receipt_unavailable"}:
                return "submitted"
            if outcome == "mined_success":
                return "success"
            if outcome == "mined_reverted":
                return "receipt_reverted"
            return outcome

        merged: Dict[str, Dict[str, Any]] = {}
        source_counts: Dict[str, int] = {"ledger": 0, "audit": 0}

        def _append_item(item: Dict[str, Any], *, source: str) -> None:
            tx_hash = str(item.get("tx_hash") or "")
            if tx_hash:
                key = f"{tx_hash}|{str(item.get('kind') or '')}"
            else:
                key = "|".join(
                    [
                        str(item.get("kind") or ""),
                        str(item.get("outcome") or ""),
                        str(item.get("token") or ""),
                        str(item.get("amount_wei") or ""),
                        str(item.get("ts_ms") or 0),
                    ]
                )
            item["source"] = str(source)
            if source == "ledger":
                merged[key] = item
                source_counts["ledger"] = int(source_counts.get("ledger", 0)) + 1
                return
            if key not in merged:
                merged[key] = item
            source_counts["audit"] = int(source_counts.get("audit", 0)) + 1

        for row in self._all_ledger_transactions(runtime):
            if not isinstance(row, dict):
                continue
            kind = str(row.get("tx_type") or "")
            if "withdraw" not in kind.lower():
                continue
            metadata = dict(row.get("metadata") or {})
            token = str(
                metadata.get("token")
                or metadata.get("token_out")
                or metadata.get("asset")
                or metadata.get("token_in")
                or ""
            )
            amount = self._int_like(
                metadata.get("amount_wei")
                or metadata.get("amount")
                or metadata.get("amountOut")
                or metadata.get("amount_in")
            )
            outcome = _normalize_outcome(
                metadata.get("outcome") or metadata.get("tx_status") or metadata.get("status")
            )
            _append_item(
                {
                    "ts_ms": self._int_like(row.get("ts_ms")),
                    "kind": kind,
                    "reason": str(metadata.get("reason") or metadata.get("action_reason") or ""),
                    "reason_code": str(metadata.get("reason_code") or outcome or ""),
                    "outcome": outcome,
                    "token": token,
                    "amount_wei": str(amount),
                    "tx_hash": str(row.get("receipt_id") or metadata.get("tx_hash") or ""),
                },
                source="ledger",
            )

        audit = getattr(getattr(runtime, "_cc", None), "audit", None)
        if audit is not None and hasattr(audit, "tail"):
            try:
                rows = list(audit.tail(limit=2000) or [])
            except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError):
                rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                kind = str(row.get("kind") or "")
                if "withdraw" not in kind.lower():
                    continue
                payload = dict(row.get("payload") or {})
                token = str(
                    payload.get("token")
                    or payload.get("token_out")
                    or payload.get("asset")
                    or payload.get("token_in")
                    or ""
                )
                amount = self._int_like(
                    payload.get("amount_wei")
                    or payload.get("amount")
                    or payload.get("amountOut")
                    or payload.get("amount_in")
                )
                outcome = _normalize_outcome(
                    payload.get("outcome") or payload.get("status") or payload.get("tx_status")
                )
                _append_item(
                    {
                        "ts_ms": self._int_like(row.get("ts_ms")),
                        "kind": kind,
                        "reason": str(row.get("reason") or payload.get("action_reason") or ""),
                        "reason_code": str(payload.get("reason_code") or outcome or ""),
                        "outcome": outcome,
                        "token": token,
                        "amount_wei": str(amount),
                        "tx_hash": str(payload.get("tx_hash") or payload.get("hash") or ""),
                    },
                    source="audit",
                )

        items = sorted(merged.values(), key=lambda item: self._int_like(item.get("ts_ms")))
        by_token: Dict[str, int] = {}
        successful = 0
        for item in items:
            token = str(item.get("token") or "")
            amount = self._int_like(item.get("amount_wei"))
            outcome = str(item.get("outcome") or "")
            if outcome in {"ok", "success", "submitted", "completed", "receipt_reverted"}:
                successful += 1
            if token and amount:
                by_token[token] = int(by_token.get(token, 0)) + int(amount)
        return {
            "available": bool(items)
            or bool(source_counts["audit"])
            or bool(source_counts["ledger"]),
            "count": int(len(items)),
            "successful_count": int(successful),
            "items": items[-10:],
            "by_token": {str(k): str(v) for k, v in by_token.items()},
            "source_counts": {str(k): int(v) for k, v in source_counts.items() if int(v) > 0},
        }

    def _executor_balance_snapshot(
        self,
        runtime: Any,
        *,
        ledger_balances: Dict[str, Any],
        ledger_accounting: Dict[str, Any],
    ) -> Dict[str, Any]:
        asset_accounts = dict(ledger_accounting.get("assetAccounts") or {})
        balances: Dict[str, float] = {}
        for account, asset_amounts in asset_accounts.items():
            if not str(account).startswith("asset:"):
                continue
            for asset, amount in dict(asset_amounts or {}).items():
                balances[str(asset)] = round(
                    float(balances.get(str(asset), 0.0)) + self._float_like(amount), 8
                )
        if not balances:
            balances = {
                str(k): round(self._float_like(v), 8)
                for k, v in dict(ledger_balances or {}).items()
            }
        return {
            "available": bool(balances),
            "executor_address": str(
                getattr(
                    getattr(getattr(runtime, "cfg", None), "execution", None),
                    "executor_address",
                    "",
                )
                or ""
            ),
            "balance_source": (
                "asset_accounts" if asset_accounts else ("balances" if balances else "unavailable")
            ),
            "balances": balances,
        }

    def _receipt_settlement_reconciliation(
        self,
        runtime: Any,
        *,
        ledger_balances: Dict[str, Any],
        ledger_accounting: Dict[str, Any],
    ) -> Dict[str, Any]:
        pnl_rows = [
            row
            for row in self._pnl_receipt_rows(runtime)
            if self._int_like(row.get("receipt_status")) == 1
        ]
        ledger_rows = [
            dict(row)
            for row in self._all_ledger_transactions(runtime)
            if isinstance(row, dict) and str(row.get("tx_type") or "") == "receipt_settlement"
        ]
        pnl_map = {
            str(row.get("tx_hash") or ""): dict(row)
            for row in pnl_rows
            if str(row.get("tx_hash") or "")
        }
        ledger_map: Dict[str, Dict[str, Any]] = {}
        for row in ledger_rows:
            metadata = dict(row.get("metadata") or {})
            key = str(row.get("receipt_id") or metadata.get("tx_hash") or "")
            if key:
                ledger_map[key] = row
        missing_ledger = sorted(key for key in pnl_map if key not in ledger_map)
        orphan_ledger = sorted(key for key in ledger_map if key not in pnl_map)
        mismatches: list[Dict[str, Any]] = []
        pnl_total = 0
        ledger_total = 0
        for key, row in pnl_map.items():
            pnl_total += self._int_like(row.get("realized_profit_after_gas_wei"))
            if key not in ledger_map:
                continue
            metadata = dict(ledger_map[key].get("metadata") or {})
            ledger_total += self._int_like(metadata.get("realized_profit_after_gas_wei"))
            fields = []
            for field in (
                "realized_profit_after_gas_wei",
                "realized_profit_token",
                "realized_profit_token_wei",
                "realized_profit_after_gas_usd_micro",
            ):
                left = str(row.get(field) or "")
                right = str(metadata.get(field) or "")
                if left != right:
                    fields.append(field)
            if fields:
                mismatches.append({"receipt_id": key, "fields": fields})
        for key, row in ledger_map.items():
            if key not in pnl_map:
                ledger_total += self._int_like(
                    dict(row.get("metadata") or {}).get("realized_profit_after_gas_wei")
                )
        executor_snapshot = self._executor_balance_snapshot(
            runtime, ledger_balances=ledger_balances, ledger_accounting=ledger_accounting
        )
        withdraw_history = self._withdraw_history(runtime)
        pnl_last_ts_ms = self._max_ts_ms(row.get("ts") for row in pnl_rows)
        ledger_last_ts_ms = self._max_ts_ms(row.get("ts_ms") for row in ledger_rows)
        withdraw_last_ts_ms = self._max_ts_ms(
            item.get("ts_ms") for item in list(withdraw_history.get("items") or [])
        )
        reasons: list[str] = []
        if missing_ledger:
            self._append_reason(reasons, "receipt_settlement_journal_missing")
        if orphan_ledger:
            self._append_reason(reasons, "receipt_settlement_journal_orphaned")
        if mismatches:
            self._append_reason(reasons, "receipt_settlement_journal_mismatch")
        if pnl_total != ledger_total:
            self._append_reason(reasons, "receipt_settlement_realized_total_mismatch")
        if (pnl_rows or withdraw_history.get("count")) and not bool(
            executor_snapshot.get("available")
        ):
            self._append_reason(reasons, "receipt_settlement_executor_balance_snapshot_unavailable")
        return {
            "ok": not reasons,
            "reason_codes": reasons,
            "pnl_receipts": {
                "successful_count": int(len(pnl_map)),
                "realized_profit_after_gas_wei_total": str(pnl_total),
                "receipts": sorted(pnl_map.keys())[-10:],
                "last_ts_ms": int(pnl_last_ts_ms or 0),
            },
            "ledger_receipts": {
                "count": int(len(ledger_map)),
                "realized_profit_after_gas_wei_total": str(ledger_total),
                "receipts": sorted(ledger_map.keys())[-10:],
                "last_ts_ms": int(ledger_last_ts_ms or 0),
            },
            "missing_ledger_receipts": missing_ledger[:20],
            "orphan_ledger_receipts": orphan_ledger[:20],
            "field_mismatches": mismatches[:20],
            "executor_balance_snapshot": executor_snapshot,
            "withdraw_history": {
                **dict(withdraw_history),
                "last_ts_ms": int(withdraw_last_ts_ms or 0),
            },
            "last_observed_ts_ms": int(max(pnl_last_ts_ms, ledger_last_ts_ms, withdraw_last_ts_ms)),
        }

    @staticmethod
    def _normalize_ts_ms(value: Any) -> int:
        try:
            raw = int(value or 0)
        except (TypeError, ValueError):
            return 0
        if raw <= 0:
            return 0
        if raw < 1_000_000_000_000:
            raw *= 1000
        return int(raw)

    @classmethod
    def _max_ts_ms(cls, values: Any) -> int:
        best = 0
        for value in values:
            normalized = cls._normalize_ts_ms(value)
            if normalized > best:
                best = normalized
        return int(best)

    @staticmethod
    def _freshness_class(*, age_ms: int | None, available: bool, material: bool) -> str:
        if not material:
            return "idle"
        if not available:
            return "unavailable"
        if age_ms is None:
            return "unknown"
        if age_ms <= 15 * 60 * 1000:
            return "current"
        if age_ms <= 6 * 60 * 60 * 1000:
            return "recent"
        if age_ms <= 24 * 60 * 60 * 1000:
            return "aging"
        return "stale"

    def _source_snapshot(
        self,
        *,
        name: str,
        now_ms: int,
        ts_ms: int,
        material: bool,
        available: bool,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        normalized_ts_ms = self._normalize_ts_ms(ts_ms)
        age_ms = max(0, int(now_ms) - normalized_ts_ms) if normalized_ts_ms > 0 else None
        freshness_class = self._freshness_class(
            age_ms=age_ms,
            available=bool(available),
            material=bool(material),
        )
        reason_codes: list[str] = []
        if material and not available:
            self._append_reason(reason_codes, f"{name}_unavailable")
        if material and freshness_class in {"unknown", "stale", "unavailable"}:
            self._append_reason(reason_codes, f"{name}_freshness_{freshness_class}")
        return {
            "name": str(name),
            "material": bool(material),
            "available": bool(available),
            "ts_ms": int(normalized_ts_ms or 0),
            "age_ms": int(age_ms or 0) if age_ms is not None else None,
            "freshness_class": freshness_class,
            "reason_codes": reason_codes,
            "details": dict(details or {}),
        }

    def _internal_prime_ts_ms(self, internal_prime_state: Dict[str, Any]) -> int:
        return kernel_internal_prime_ts_ms(internal_prime_state)

    def _capital_engine_ts_ms(
        self,
        capital_state: Dict[str, Any],
        capital_engine: Dict[str, Any],
        efficiency: Dict[str, Any],
        reinvestment: Dict[str, Any] | None = None,
    ) -> int:
        return kernel_capital_engine_ts_ms(capital_state, capital_engine, efficiency, reinvestment)

    def _bankroll_ts_ms(self, bankroll_state: Any) -> int:
        if bankroll_state is None:
            return 0
        return kernel_bankroll_ts_ms(
            {
                "updated_ts_ms": getattr(bankroll_state, "updated_ts_ms", 0),
                "profit_updated_ts_ms": getattr(bankroll_state, "profit_updated_ts_ms", 0),
                "sizing_updated_ts_ms": getattr(bankroll_state, "sizing_updated_ts_ms", 0),
            }
        )

    def _has_bankroll_history(self, runtime: Any) -> bool:
        return kernel_has_bankroll_history(runtime)

    def _bankroll_history_event(self, runtime: Any) -> Dict[str, Any]:
        return kernel_read_bankroll_history_event(runtime)

    def _has_treasury_state_history(self, runtime: Any) -> bool:
        return kernel_has_treasury_state_history(runtime)

    def _treasury_history_snapshot(self, runtime: Any) -> Dict[str, Any]:
        return kernel_read_treasury_history_snapshot(runtime)

    def _has_internal_prime_state_history(self, runtime: Any) -> bool:
        return kernel_has_internal_prime_state_history(runtime)

    def _internal_prime_state_history_snapshot(self, runtime: Any) -> Dict[str, Any]:
        return kernel_read_internal_prime_state_history_snapshot(runtime)

    @classmethod
    def _capital_commit_id_from_payload(cls, payload: Any) -> str:
        return kernel_capital_commit_id_from_payload(payload)

    def _has_capital_event_bus(self, runtime: Any) -> bool:
        return kernel_has_capital_event_bus(runtime)

    def _capital_event(self, runtime: Any, *, domain: str) -> Dict[str, Any]:
        return kernel_read_capital_event(runtime, domain=domain)

    @staticmethod
    def _state_field_mismatches(
        current: Dict[str, Any], recorded: Dict[str, Any], fields: list[str]
    ) -> list[str]:
        return kernel_state_field_mismatches(current, recorded, fields)

    def _capital_convergence(
        self,
        *,
        now_ms: int,
        capital_state: Dict[str, Any],
        capital_engine: Dict[str, Any],
        efficiency: Dict[str, Any],
        reinvestment: Dict[str, Any],
        bankroll_state: Any,
        realized_profit_wei: int,
        deployed_capital_wei: int,
        ledger_ts_ms: int,
        receipt_settlement: Dict[str, Any],
        receipt_outcome_truth: Dict[str, Any],
        borrowed_usd: float,
        prime_open_loan_count: int,
        internal_prime_state: Dict[str, Any],
        bankroll_history_event: Dict[str, Any],
        treasury_history_snapshot: Dict[str, Any],
        internal_prime_state_history_snapshot: Dict[str, Any],
        bankroll_history_enabled: bool,
        treasury_history_enabled: bool,
        internal_prime_history_enabled: bool,
        capital_event_enabled: bool,
        capital_event_bankroll: Dict[str, Any],
        capital_event_treasury: Dict[str, Any],
        capital_event_ledger: Dict[str, Any],
        capital_event_receipt: Dict[str, Any],
        capital_event_internal_prime: Dict[str, Any],
    ) -> Dict[str, Any]:
        current_bankroll_state = {
            "realized_profit_wei": int(realized_profit_wei or 0),
            "last_amount_in_wei": int(getattr(bankroll_state, "last_amount_in_wei", 0) or 0),
            "success_streak": int(getattr(bankroll_state, "success_streak", 0) or 0),
            "fail_streak": int(getattr(bankroll_state, "fail_streak", 0) or 0),
            "updated_ts_ms": int(getattr(bankroll_state, "updated_ts_ms", 0) or 0),
            "profit_updated_ts_ms": int(getattr(bankroll_state, "profit_updated_ts_ms", 0) or 0),
            "sizing_updated_ts_ms": int(getattr(bankroll_state, "sizing_updated_ts_ms", 0) or 0),
        }
        source_bundle = build_capital_truth_source_snapshots(
            now_ms=now_ms,
            ledger_ts_ms=ledger_ts_ms,
            realized_profit_wei=realized_profit_wei,
            deployed_capital_wei=deployed_capital_wei,
            borrowed_usd=borrowed_usd,
            prime_open_loan_count=prime_open_loan_count,
            capital_state=capital_state,
            capital_engine=capital_engine,
            efficiency=efficiency,
            reinvestment=reinvestment,
            receipt_settlement=receipt_settlement,
            receipt_outcome_truth=receipt_outcome_truth,
            internal_prime_state=internal_prime_state,
            current_bankroll_state=current_bankroll_state,
            bankroll_history_event=bankroll_history_event,
            treasury_history_snapshot=treasury_history_snapshot,
            internal_prime_state_history_snapshot=internal_prime_state_history_snapshot,
            bankroll_history_enabled=bankroll_history_enabled,
            treasury_history_enabled=treasury_history_enabled,
            internal_prime_history_enabled=internal_prime_history_enabled,
            capital_event_enabled=capital_event_enabled,
            capital_event_bankroll=capital_event_bankroll,
            capital_event_treasury=capital_event_treasury,
            capital_event_ledger=capital_event_ledger,
            capital_event_receipt=capital_event_receipt,
            capital_event_internal_prime=capital_event_internal_prime,
            append_reason=self._append_reason,
        )
        sources: Dict[str, Dict[str, Any]] = {
            str(name): dict(payload) for name, payload in source_bundle.sources.items()
        }
        family_targets = dict(source_bundle.family_targets)
        family_allocations_wei = dict(source_bundle.family_allocations_wei)
        receipt_last_ts_ms = int(source_bundle.receipt_last_ts_ms or 0)
        receipt_outcome_ts_ms = int(source_bundle.receipt_outcome_ts_ms or 0)
        ledger_event_ts_ms = int(source_bundle.ledger_event_ts_ms or 0)
        receipt_event_ts_ms = int(source_bundle.receipt_event_ts_ms or 0)
        bankroll_history_payload = dict(source_bundle.bankroll_history_payload)
        treasury_history_payload = dict(source_bundle.treasury_history_payload)
        internal_prime_history_payload = dict(source_bundle.internal_prime_history_payload)
        bankroll_event_payload = dict(source_bundle.bankroll_event_payload)
        bankroll_event_state = dict(source_bundle.bankroll_event_state)
        treasury_event_payload = dict(source_bundle.treasury_event_payload)
        treasury_event_capital_engine = dict(source_bundle.treasury_event_capital_engine)
        ledger_event_payload = dict(source_bundle.ledger_event_payload)
        receipt_event_payload = dict(source_bundle.receipt_event_payload)
        prime_event_payload = dict(source_bundle.prime_event_payload)
        ledger_material = bool(dict(sources.get("ledger") or {}).get("material"))
        capital_engine_material = bool(dict(sources.get("capital_engine") or {}).get("material"))
        receipt_material = bool(dict(sources.get("receipt_settlement") or {}).get("material"))
        bankroll_material = bool(dict(sources.get("bankroll") or {}).get("material"))
        capital_engine_ts_ms = self._capital_engine_ts_ms(
            capital_state, capital_engine, efficiency, reinvestment
        )
        bankroll_history_ts_ms = self._max_ts_ms(
            [
                bankroll_history_event.get("ts_ms"),
                bankroll_history_payload.get("updated_ts_ms"),
                bankroll_history_payload.get("profit_updated_ts_ms"),
                bankroll_history_payload.get("sizing_updated_ts_ms"),
            ]
        )
        treasury_history_ts_ms = self._max_ts_ms(
            [treasury_history_snapshot.get("ts_ms"), treasury_history_payload.get("updated_ts_ms")]
        )

        reasons: list[str] = []
        freshness_reason_codes: list[str] = []
        for source in sources.values():
            for reason in list(source.get("reason_codes") or []):
                self._append_reason(freshness_reason_codes, str(reason))
                if str(reason).endswith(
                    ("_freshness_unknown", "_freshness_stale", "_freshness_unavailable")
                ):
                    self._append_reason(reasons, str(reason))

        receipt_pnl_total = self._int_like(
            dict(receipt_settlement.get("pnl_receipts") or {}).get(
                "realized_profit_after_gas_wei_total"
            )
        )
        if receipt_pnl_total > 0 and abs(receipt_pnl_total - int(realized_profit_wei or 0)) > 0:
            self._append_reason(reasons, "bankroll_receipt_realized_profit_mismatch")

        bankroll_history_mismatches = self._state_field_mismatches(
            current_bankroll_state,
            bankroll_history_payload,
            [
                "realized_profit_wei",
                "last_amount_in_wei",
                "success_streak",
                "fail_streak",
                "updated_ts_ms",
                "profit_updated_ts_ms",
                "sizing_updated_ts_ms",
            ],
        )
        if bankroll_material and bankroll_history_event and bankroll_history_mismatches:
            self._append_reason(reasons, "bankroll_state_history_mismatch")
            sources["bankroll_history"]["details"]["mismatch_fields"] = bankroll_history_mismatches

        bankroll_event_mismatches = self._state_field_mismatches(
            current_bankroll_state,
            bankroll_event_state,
            [
                "realized_profit_wei",
                "last_amount_in_wei",
                "success_streak",
                "fail_streak",
                "updated_ts_ms",
                "profit_updated_ts_ms",
                "sizing_updated_ts_ms",
            ],
        )
        if (
            bankroll_material
            and capital_event_enabled
            and capital_event_bankroll
            and bankroll_event_mismatches
        ):
            self._append_reason(reasons, "bankroll_capital_event_mismatch")
            sources["capital_event_bankroll"]["details"][
                "mismatch_fields"
            ] = bankroll_event_mismatches

        runtime_capital_signature = {
            "updated_ts_ms": int(capital_engine_ts_ms or 0),
            "deployable_bankroll_wei": str(
                max(0, int(self._int_like(capital_engine.get("deployable_bankroll_wei"))))
            ),
            "estimated_capital_wei": str(
                max(0, int(self._int_like(capital_engine.get("estimated_capital_wei"))))
            ),
            "drawdown_buffer_wei": str(
                max(0, int(self._int_like(capital_engine.get("drawdown_buffer_wei"))))
            ),
            "family_allocations_wei": {
                str(k): str(max(0, int(self._int_like(v))))
                for k, v in dict(capital_engine.get("family_allocations_wei") or {}).items()
            },
        }
        history_capital_engine = dict(treasury_history_payload.get("capital_engine") or {})
        history_signature = {
            "updated_ts_ms": int(
                self._max_ts_ms(
                    [
                        treasury_history_payload.get("updated_ts_ms"),
                        history_capital_engine.get("updated_ts_ms"),
                    ]
                )
                or 0
            ),
            "deployable_bankroll_wei": str(
                max(0, int(self._int_like(history_capital_engine.get("deployable_bankroll_wei"))))
            ),
            "estimated_capital_wei": str(
                max(0, int(self._int_like(history_capital_engine.get("estimated_capital_wei"))))
            ),
            "drawdown_buffer_wei": str(
                max(0, int(self._int_like(history_capital_engine.get("drawdown_buffer_wei"))))
            ),
            "family_allocations_wei": {
                str(k): str(max(0, int(self._int_like(v))))
                for k, v in dict(history_capital_engine.get("family_allocations_wei") or {}).items()
            },
        }
        treasury_history_mismatches = self._state_field_mismatches(
            runtime_capital_signature,
            history_signature,
            [
                "updated_ts_ms",
                "deployable_bankroll_wei",
                "estimated_capital_wei",
                "drawdown_buffer_wei",
                "family_allocations_wei",
            ],
        )
        if capital_engine_material and treasury_history_snapshot and treasury_history_mismatches:
            self._append_reason(reasons, "capital_engine_history_runtime_mismatch")
            sources["treasury_state_history"]["details"][
                "mismatch_fields"
            ] = treasury_history_mismatches

        treasury_event_signature = {
            "updated_ts_ms": int(
                self._max_ts_ms(
                    [
                        treasury_event_payload.get("updated_ts_ms"),
                        treasury_event_capital_engine.get("updated_ts_ms"),
                    ]
                )
                or 0
            ),
            "deployable_bankroll_wei": str(
                max(
                    0,
                    int(
                        self._int_like(treasury_event_capital_engine.get("deployable_bankroll_wei"))
                    ),
                )
            ),
            "estimated_capital_wei": str(
                max(
                    0,
                    int(self._int_like(treasury_event_capital_engine.get("estimated_capital_wei"))),
                )
            ),
            "drawdown_buffer_wei": str(
                max(
                    0, int(self._int_like(treasury_event_capital_engine.get("drawdown_buffer_wei")))
                )
            ),
            "family_allocations_wei": {
                str(k): str(max(0, int(self._int_like(v))))
                for k, v in dict(
                    treasury_event_capital_engine.get("family_allocations_wei") or {}
                ).items()
            },
        }
        treasury_event_mismatches = self._state_field_mismatches(
            runtime_capital_signature,
            treasury_event_signature,
            [
                "updated_ts_ms",
                "deployable_bankroll_wei",
                "estimated_capital_wei",
                "drawdown_buffer_wei",
                "family_allocations_wei",
            ],
        )
        if (
            capital_engine_material
            and capital_event_enabled
            and capital_event_treasury
            and treasury_event_mismatches
        ):
            self._append_reason(reasons, "capital_engine_capital_event_mismatch")
            sources["capital_event_treasury"]["details"][
                "mismatch_fields"
            ] = treasury_event_mismatches

        total_target_pct = round(sum(float(v) for v in family_targets.values()), 8)
        if family_targets and total_target_pct - 1.0 > 1e-6:
            self._append_reason(reasons, "family_targets_overallocated")

        allocated_total_wei = sum(int(v) for v in family_allocations_wei.values())
        if deployed_capital_wei > 0 and allocated_total_wei - int(deployed_capital_wei) > 1:
            self._append_reason(reasons, "family_allocations_exceed_deployable_capital")

        unknown_allocated_families = sorted(
            family
            for family, value in family_allocations_wei.items()
            if int(value) > 0
            and not resolve_family_target(family_targets=family_targets, family=family)[2]
        )
        if unknown_allocated_families:
            self._append_reason(reasons, "family_allocation_target_mismatch")

        if (
            receipt_outcome_ts_ms > 0
            and receipt_last_ts_ms > 0
            and receipt_outcome_ts_ms + (15 * 60 * 1000) < receipt_last_ts_ms
        ):
            self._append_reason(reasons, "receipt_outcome_truth_lags_receipt_settlement")
        if (
            ledger_material
            and capital_event_enabled
            and ledger_ts_ms > 0
            and ledger_event_ts_ms > 0
            and ledger_event_ts_ms + 1000 < ledger_ts_ms
        ):
            self._append_reason(reasons, "ledger_capital_event_lag")
        if (
            receipt_material
            and capital_event_enabled
            and receipt_last_ts_ms > 0
            and receipt_event_ts_ms > 0
            and receipt_event_ts_ms + 1000 < receipt_last_ts_ms
        ):
            self._append_reason(reasons, "receipt_settlement_capital_event_lag")

        lineage_anchor_commit_id = str(source_bundle.lineage_anchor_commit_id or "")
        if lineage_anchor_commit_id:
            lineage_sources = {
                "capital_event_receipt": self._capital_commit_id_from_payload(
                    receipt_event_payload
                ),
                "capital_event_ledger": self._capital_commit_id_from_payload(ledger_event_payload),
                "capital_event_bankroll": self._capital_commit_id_from_payload(
                    bankroll_event_payload
                ),
                "bankroll_history": self._capital_commit_id_from_payload(bankroll_history_event),
                "capital_event_treasury": self._capital_commit_id_from_payload(
                    treasury_event_payload
                ),
                "treasury_state_history": self._capital_commit_id_from_payload(
                    treasury_history_payload
                ),
                "capital_event_internal_prime": self._capital_commit_id_from_payload(
                    prime_event_payload
                ),
                "internal_prime_state_history": self._capital_commit_id_from_payload(
                    internal_prime_history_payload
                ),
            }
            required_lineage = [
                name
                for name, snapshot in sources.items()
                if name in lineage_sources
                and bool(snapshot.get("material"))
                and bool(snapshot.get("available"))
            ]
            missing_lineage = [
                name for name in required_lineage if not str(lineage_sources.get(name) or "")
            ]
            mismatched_lineage = [
                name
                for name in required_lineage
                if str(lineage_sources.get(name) or "")
                and str(lineage_sources.get(name) or "") != str(lineage_anchor_commit_id)
            ]
            if missing_lineage:
                self._append_reason(reasons, "capital_commit_lineage_incomplete")
            if mismatched_lineage:
                self._append_reason(reasons, "capital_commit_lineage_mismatch")
            lineage_details = {
                "anchor_commit_id": str(lineage_anchor_commit_id),
                "required_sources": list(required_lineage),
                "missing_sources": list(missing_lineage),
                "mismatched_sources": list(mismatched_lineage),
                "commit_ids": {
                    name: str(lineage_sources.get(name) or "") for name in required_lineage
                },
            }
            sources["capital_event_receipt"]["details"]["commit_lineage"] = dict(lineage_details)
            sources["capital_event_ledger"]["details"]["commit_lineage"] = dict(lineage_details)
            sources["capital_event_internal_prime"]["details"]["commit_lineage"] = dict(
                lineage_details
            )

        convergence_ts_values = [
            int(snapshot.get("ts_ms") or 0)
            for snapshot in sources.values()
            if bool(snapshot.get("material")) and int(snapshot.get("ts_ms") or 0) > 0
        ]
        min_ts_ms = int(min(convergence_ts_values)) if convergence_ts_values else 0
        max_ts_ms = int(max(convergence_ts_values)) if convergence_ts_values else 0
        spread_ms = max(0, max_ts_ms - min_ts_ms) if min_ts_ms and max_ts_ms else 0
        freshness_class = self._freshness_class(
            age_ms=(max(0, now_ms - min_ts_ms) if min_ts_ms > 0 else None),
            available=bool(convergence_ts_values),
            material=bool(any(bool(source.get("material")) for source in sources.values())),
        )
        return {
            "ok": not reasons,
            "reason_codes": reasons,
            "freshness_reason_codes": freshness_reason_codes,
            "freshness_class": freshness_class,
            "observed_ts_ms": int(now_ms),
            "reference_ts_ms": int(min_ts_ms or 0),
            "newest_source_ts_ms": int(max_ts_ms or 0),
            "source_spread_ms": int(spread_ms or 0),
            "sources": sources,
            "derived": {
                "bankroll_realized_profit_wei": str(max(0, int(realized_profit_wei))),
                "receipt_realized_profit_after_gas_wei_total": str(max(0, int(receipt_pnl_total))),
                "family_targets_total_pct": float(round(total_target_pct * 100.0, 6)),
                "family_allocations_total_wei": str(max(0, int(allocated_total_wei))),
                "deployable_capital_wei": str(max(0, int(deployed_capital_wei))),
                "unknown_allocated_families": unknown_allocated_families,
                "bankroll_history_ts_ms": int(bankroll_history_ts_ms or 0),
                "treasury_history_ts_ms": int(treasury_history_ts_ms or 0),
            },
        }

    def summary(self, runtime: Any) -> Dict[str, Any]:
        return summarize_capital_truth(service=self, runtime=runtime)
