from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List

from ..domain_errors import LedgerConsistencyError


@dataclass(frozen=True)
class LedgerEntry:
    ts_ms: int
    entry_type: str
    asset: str
    amount: float
    venue: str
    chain: str
    family: str
    note: str
    transaction_id: str = ""
    receipt_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LedgerLine:
    account: str
    asset: str
    amount: float
    family: str = ""
    venue: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LedgerTransaction:
    transaction_id: str
    ts_ms: int
    tx_type: str
    chain: str
    receipt_id: str
    lines: List[LedgerLine] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        total = round(sum(float(x.amount) for x in self.lines), 8)
        if abs(total) > 1e-6:
            raise LedgerConsistencyError(
                "unbalanced transaction", reason_code="unbalanced_transaction"
            )
        if not self.lines:
            raise LedgerConsistencyError(
                "missing transaction lines", reason_code="missing_transaction_lines"
            )

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["lines"] = [line.to_dict() for line in self.lines]
        return payload


class TreasuryLedger:
    _PROJECTED_ENTRY_TYPES = {"realized_pnl", "borrow_cost", "settlement_loss"}

    def __init__(self, *, data_dir: str, chain: str):
        self.path = os.path.join(data_dir, "treasury", f"ledger_{chain}.jsonl")
        self.tx_path = os.path.join(data_dir, "treasury", f"ledger_transactions_{chain}.jsonl")
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    @staticmethod
    def _normalize_account_class(account: str) -> str:
        acc = str(account or "")
        if acc.startswith("asset:"):
            return "asset"
        if acc.startswith("liability:"):
            return "liability"
        if acc.startswith("equity:"):
            return "equity"
        if acc == "internal_prime:borrowed_usd":
            return "liability"
        if acc.startswith("internal_prime:inventory_reserved:"):
            return "encumbrance"
        return "memo"

    @staticmethod
    def _add_nested_amount(
        target: Dict[str, Dict[str, float]], *, key: str, asset: str, amount: float
    ) -> None:
        bucket = target.setdefault(str(key), {})
        bucket[str(asset)] = round(float(bucket.get(str(asset), 0.0)) + float(amount), 8)

    @classmethod
    def _aggregate_account_balances(
        cls, rows: Iterable[Dict[str, Any]]
    ) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for row in rows:
            for line in list((row or {}).get("lines") or []):
                if not isinstance(line, dict):
                    continue
                account = str(line.get("account") or "")
                asset = str(line.get("asset") or "")
                if not account:
                    continue
                cls._add_nested_amount(
                    out, key=account, asset=asset or "", amount=float(line.get("amount") or 0.0)
                )
        return {
            account: {asset: round(float(amount), 8) for asset, amount in assets.items()}
            for account, assets in out.items()
        }

    @classmethod
    def _aggregate_accounting_semantics(cls, rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        account_balances = cls._aggregate_account_balances(rows)
        assets: Dict[str, float] = {}
        liabilities: Dict[str, float] = {}
        equity: Dict[str, float] = {}
        encumbrances: Dict[str, float] = {}
        memo_accounts: Dict[str, Dict[str, float]] = {}
        liability_accounts: Dict[str, Dict[str, float]] = {}
        encumbrance_accounts: Dict[str, Dict[str, float]] = {}
        asset_accounts: Dict[str, Dict[str, float]] = {}
        equity_accounts: Dict[str, Dict[str, float]] = {}
        for account, asset_amounts in account_balances.items():
            account_class = cls._normalize_account_class(account)
            target = {
                "asset": assets,
                "liability": liabilities,
                "equity": equity,
                "encumbrance": encumbrances,
            }.get(account_class)
            account_target = {
                "asset": asset_accounts,
                "liability": liability_accounts,
                "equity": equity_accounts,
                "encumbrance": encumbrance_accounts,
            }.get(account_class)
            if target is None or account_target is None:
                memo_accounts[account] = dict(asset_amounts)
                continue
            account_target[account] = dict(asset_amounts)
            for asset, amount in asset_amounts.items():
                if not asset:
                    continue
                if account_class == "encumbrance":
                    target[asset] = round(float(target.get(asset, 0.0)) + abs(float(amount)), 8)
                else:
                    target[asset] = round(float(target.get(asset, 0.0)) + float(amount), 8)
        free_assets = {
            asset: round(float(assets.get(asset, 0.0)) - float(encumbrances.get(asset, 0.0)), 8)
            for asset in sorted(set(assets) | set(encumbrances))
        }
        net_assets = {
            asset: round(float(free_assets.get(asset, 0.0)) - float(liabilities.get(asset, 0.0)), 8)
            for asset in sorted(set(free_assets) | set(liabilities))
        }
        return {
            "accountBalances": account_balances,
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "encumberedAssets": encumbrances,
            "freeAssets": free_assets,
            "netAssets": net_assets,
            "assetAccounts": asset_accounts,
            "liabilityAccounts": liability_accounts,
            "equityAccounts": equity_accounts,
            "encumbranceAccounts": encumbrance_accounts,
            "memoAccounts": memo_accounts,
        }

    @staticmethod
    def _aggregate_legacy_balances(rows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for row in rows:
            asset = str((row or {}).get("asset") or "")
            if not asset:
                continue
            out[asset] = float(out.get(asset, 0.0)) + float((row or {}).get("amount") or 0.0)
        return {k: round(v, 8) for k, v in out.items()}

    @staticmethod
    def _aggregate_transaction_balances(rows: Iterable[Dict[str, Any]]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for row in rows:
            for line in list((row or {}).get("lines") or []):
                if not isinstance(line, dict):
                    continue
                account = str(line.get("account") or "")
                asset = str(line.get("asset") or "")
                if not asset or account.startswith("equity:"):
                    continue
                out[asset] = float(out.get(asset, 0.0)) + float(line.get("amount") or 0.0)
        return {k: round(v, 8) for k, v in out.items()}

    @staticmethod
    def _entry_lines(
        *,
        asset: str,
        amount: float,
        family: str = "",
        venue: str = "",
        note: str = "",
    ) -> List[LedgerLine]:
        asset_s = str(asset or "")
        amount_f = float(amount)
        note_s = str(note or "")
        return [
            LedgerLine(
                account=f"asset:{asset_s}",
                asset=asset_s,
                amount=amount_f,
                family=str(family),
                venue=str(venue),
                note=note_s,
            ),
            LedgerLine(
                account="equity:offset",
                asset="USD",
                amount=float(-amount_f),
                family=str(family),
                venue=str(venue),
                note=f"offset:{note_s or asset_s}",
            ),
        ]

    @classmethod
    def _simple_entry_from_transaction(cls, row: Dict[str, Any]) -> Dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        tx_type = str(row.get("tx_type") or "")
        metadata = dict(row.get("metadata") or {})
        entry_type = str(metadata.get("entry_type") or tx_type)
        if entry_type not in cls._PROJECTED_ENTRY_TYPES:
            return None
        line = None
        for candidate in list(row.get("lines") or []):
            if not isinstance(candidate, dict):
                continue
            account = str(candidate.get("account") or "")
            asset = str(candidate.get("asset") or "")
            if account.startswith("equity:") or not asset:
                continue
            line = dict(candidate)
            break
        if line is None:
            return None
        family = str(metadata.get("family") or line.get("family") or "")
        venue = str(metadata.get("venue") or line.get("venue") or "")
        note = str(metadata.get("note") or line.get("note") or entry_type)
        payload = LedgerEntry(
            ts_ms=int(row.get("ts_ms") or 0),
            entry_type=entry_type,
            asset=str(metadata.get("asset") or line.get("asset") or ""),
            amount=float(line.get("amount") or 0.0),
            venue=venue,
            chain=str(row.get("chain") or ""),
            family=family,
            note=note,
            transaction_id=str(row.get("transaction_id") or ""),
            receipt_id=str(row.get("receipt_id") or ""),
            metadata=dict(metadata),
        )
        return payload.to_dict()

    @classmethod
    def _receipt_component_entries(cls, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(row, dict) or str(row.get("tx_type") or "") != "receipt_settlement":
            return []
        metadata = dict(row.get("metadata") or {})
        route_key = str(
            metadata.get("route_id")
            or metadata.get("tx_hash")
            or row.get("receipt_id")
            or row.get("transaction_id")
            or ""
        )
        note_prefix = f"receipt_settlement:{route_key}" if route_key else "receipt_settlement"
        family = str(metadata.get("strategy_family") or metadata.get("family") or "")
        venue = str(metadata.get("capture_lane") or metadata.get("venue") or "")
        chain = str(row.get("chain") or "")
        base_metadata = dict(metadata)
        entries: List[Dict[str, Any]] = []

        def _append(entry_type: str, amount: float, note_suffix: str, role: str) -> None:
            if abs(float(amount)) <= 1e-12:
                return
            entry = LedgerEntry(
                ts_ms=int(row.get("ts_ms") or 0),
                entry_type=entry_type,
                asset="USD",
                amount=float(amount),
                venue=venue,
                chain=chain,
                family=family,
                note=f"{note_prefix}:{note_suffix}",
                transaction_id=str(row.get("transaction_id") or ""),
                receipt_id=str(row.get("receipt_id") or ""),
                metadata={**base_metadata, "settlementRole": role},
            )
            entries.append(entry.to_dict())

        status = int(metadata.get("status") or 0)
        realized_after_gas_usd = float(metadata.get("realized_after_gas_usd") or 0.0)
        borrow_cost_usd = float(metadata.get("borrow_cost_usd") or 0.0)
        gas_cost_usd = float(metadata.get("gas_cost_usd") or 0.0)
        if status == 1 and realized_after_gas_usd > 0.0:
            _append(
                "realized_pnl", realized_after_gas_usd, "realized_after_gas_usd", "realized_pnl"
            )
        if status != 1 and gas_cost_usd > 0.0:
            _append("settlement_loss", -abs(gas_cost_usd), "gas_loss_usd", "settlement_loss")
        if borrow_cost_usd > 0.0:
            _append("borrow_cost", -abs(borrow_cost_usd), "borrow_cost_usd", "borrow_cost")
        return entries

    @classmethod
    def projected_entry_rows(cls, rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        projected: List[Dict[str, Any]] = []
        for row in list(rows or []):
            simple = cls._simple_entry_from_transaction(dict(row))
            if simple is not None:
                projected.append(simple)
                continue
            projected.extend(cls._receipt_component_entries(dict(row)))
        return projected

    def _read_all_rows(self, path: str) -> List[Dict[str, Any]]:
        if not os.path.exists(path):
            return []
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
        return rows

    def balance_report(self) -> Dict[str, Any]:
        legacy_rows = self._read_all_rows(self.path)
        legacy_balances = self._aggregate_legacy_balances(legacy_rows)
        tx_rows = self._read_all_rows(self.tx_path)
        tx_balances = self._aggregate_transaction_balances(tx_rows)
        accounting = self._aggregate_accounting_semantics(tx_rows)
        if tx_rows:
            return {
                "balances": tx_balances,
                "balanceSource": "transaction_journal",
                "transactionCount": int(len(tx_rows)),
                "legacyEntryCount": int(len(legacy_rows)),
                "accountBalances": accounting.get("accountBalances") or {},
                "accounting": {k: v for k, v in accounting.items() if k != "accountBalances"},
            }
        return {
            "balances": legacy_balances,
            "balanceSource": "legacy_entries",
            "transactionCount": 0,
            "legacyEntryCount": int(len(legacy_rows)),
            "accountBalances": {},
            "accounting": {
                "assets": {},
                "liabilities": {},
                "equity": {},
                "encumberedAssets": {},
                "freeAssets": {},
                "netAssets": {},
                "assetAccounts": {},
                "liabilityAccounts": {},
                "equityAccounts": {},
                "encumbranceAccounts": {},
                "memoAccounts": {},
            },
        }

    def transaction_balances(self) -> Dict[str, float]:
        return dict(self.balance_report().get("balances") or {})

    @staticmethod
    def _filter_prime_transactions(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            dict(row)
            for row in list(rows or [])
            if isinstance(row, dict) and str(row.get("tx_type") or "").startswith("prime_loan_")
        ]

    def transactions_all(self) -> List[Dict[str, Any]]:
        return self._read_all_rows(self.tx_path)

    def prime_transactions(self) -> List[Dict[str, Any]]:
        return self._filter_prime_transactions(self.transactions_all())

    def build_transaction(
        self,
        *,
        tx_type: str,
        chain: str,
        lines: List[LedgerLine],
        receipt_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> LedgerTransaction:
        tx = LedgerTransaction(
            transaction_id=f"tx_{uuid.uuid4().hex[:16]}",
            ts_ms=int(time.time() * 1000),
            tx_type=str(tx_type),
            chain=str(chain),
            receipt_id=str(receipt_id or ""),
            lines=list(lines or []),
            metadata=dict(metadata or {}),
        )
        tx.validate()
        return tx

    def write_transaction(self, tx: LedgerTransaction) -> LedgerTransaction:
        tx.validate()
        with open(self.tx_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(tx.to_dict(), sort_keys=True) + "\n")
        return tx

    def append_transaction(
        self,
        *,
        tx_type: str,
        chain: str,
        lines: List[LedgerLine],
        receipt_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> LedgerTransaction:
        tx = self.build_transaction(
            tx_type=tx_type,
            chain=chain,
            lines=lines,
            receipt_id=receipt_id,
            metadata=metadata,
        )
        return self.write_transaction(tx)

    def append(
        self,
        *,
        entry_type: str,
        asset: str,
        amount: float,
        venue: str = "",
        chain: str = "",
        family: str = "",
        note: str = "",
        receipt_id: str = "",
        metadata: Dict[str, Any] | None = None,
    ) -> LedgerEntry:
        metadata_dict = dict(metadata or {})
        tx = self.append_transaction(
            tx_type=str(entry_type),
            chain=str(chain),
            receipt_id=str(receipt_id),
            lines=self._entry_lines(
                asset=str(asset),
                amount=float(amount),
                family=str(family),
                venue=str(venue),
                note=str(note),
            ),
            metadata={
                "entry_type": str(entry_type),
                "asset": str(asset),
                "venue": str(venue),
                "family": str(family),
                "note": str(note),
                **metadata_dict,
            },
        )
        return LedgerEntry(
            ts_ms=tx.ts_ms,
            entry_type=str(entry_type),
            asset=str(asset),
            amount=float(amount),
            venue=str(venue),
            chain=str(chain),
            family=str(family),
            note=str(note),
            transaction_id=tx.transaction_id,
            receipt_id=str(receipt_id),
            metadata=dict(tx.metadata or {}),
        )

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        tx_rows = self.transactions_all()
        projected = self.projected_entry_rows(tx_rows)
        if projected:
            return projected[-max(1, int(limit)) :]
        if not os.path.exists(self.path):
            return []
        rows = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
        return rows[-max(1, int(limit)) :]

    def transactions_tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not os.path.exists(self.tx_path):
            return []
        rows = []
        with open(self.tx_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
        return rows[-max(1, int(limit)) :]

    def balances(self) -> Dict[str, float]:
        return self.transaction_balances()
