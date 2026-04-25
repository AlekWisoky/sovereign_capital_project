from __future__ import annotations

import sqlite3
from typing import Any, Dict, Mapping

from ..domain_errors import LedgerConsistencyError
from ..treasury.ledger import TreasuryLedger


class RuntimeCapitalFacade:
    """Capital/ledger compatibility facade.

    This isolates non-hot-path wealth-goal, ledger journaling, and operator-facing
    stress evaluation helpers away from RuntimeBundle's orchestration loop while
    preserving the existing compatibility surface.
    """

    cfg: Any
    _ledger: Any
    _ledger_repo: Any
    _auxiliary_state_service: Any
    _pnl: Any
    _fioa: Any

    def _ledger_event_key(
        self,
        *,
        entry_type: str,
        asset: str,
        amount: float,
        venue: str = "",
        family: str = "",
        note: str = "",
    ) -> str:
        parts = [
            str(entry_type or ""),
            str(asset or ""),
            f"{float(amount):.8f}",
            str(venue or ""),
            str(family or ""),
            str(note or ""),
        ]
        return "|".join(parts)

    def _tx_to_entry_payload(self, tx: Mapping[str, Any], *, chain: str) -> Dict[str, Any]:
        metadata = dict(tx.get("metadata") or {})
        lines = list(tx.get("lines") or [])
        first_line = dict(lines[0]) if lines and isinstance(lines[0], Mapping) else {}
        return {
            "ts_ms": int(tx.get("ts_ms") or 0),
            "entry_type": str(metadata.get("entry_type") or tx.get("tx_type") or ""),
            "asset": str(metadata.get("asset") or first_line.get("asset") or ""),
            "amount": float(first_line.get("amount") or 0.0),
            "venue": str(metadata.get("venue") or first_line.get("venue") or ""),
            "chain": str(tx.get("chain") or chain),
            "family": str(metadata.get("family") or first_line.get("family") or ""),
            "note": str(metadata.get("note") or first_line.get("note") or ""),
            "transaction_id": str(tx.get("transaction_id") or ""),
            "receipt_id": str(tx.get("receipt_id") or ""),
            "metadata": metadata,
        }

    def _existing_ledger_entry(self, *, event_key: str) -> Dict[str, Any]:
        chain = str(self.cfg.chain.name)
        repo = getattr(self, "_ledger_repo", None)
        if repo is not None and hasattr(repo, "all_transactions"):
            try:
                rows = [
                    dict(row)
                    for row in list(repo.all_transactions(chain=chain) or [])
                    if isinstance(row, Mapping)
                    and str((row.get("metadata") or {}).get("event_key") or "")
                    == str(event_key or "")
                ]
                if rows:
                    projected = TreasuryLedger.projected_entry_rows(rows)
                    if projected:
                        return dict(projected[-1])
                    return self._tx_to_entry_payload(rows[-1], chain=chain)
            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
                OSError,
                sqlite3.Error,
            ):
                pass
        ledger = getattr(self, "_ledger", None)
        if ledger is not None and hasattr(ledger, "transactions_all"):
            try:
                rows = [
                    dict(row)
                    for row in list(ledger.transactions_all() or [])
                    if isinstance(row, Mapping)
                    and str((row.get("metadata") or {}).get("event_key") or "")
                    == str(event_key or "")
                ]
                if rows:
                    projected = TreasuryLedger.projected_entry_rows(rows)
                    if projected:
                        return dict(projected[-1])
                    return self._tx_to_entry_payload(rows[-1], chain=chain)
            except (
                AttributeError,
                KeyError,
                TypeError,
                ValueError,
                RuntimeError,
                OSError,
                sqlite3.Error,
            ):
                pass
        return {}

    def wealth_goal_state(self) -> Dict[str, Any]:
        return self._auxiliary_state_service.wealth_goal_state(self)

    def record_ledger_entry(
        self,
        *,
        entry_type: str,
        asset: str,
        amount: float,
        venue: str = "",
        family: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        event_key = self._ledger_event_key(
            entry_type=entry_type,
            asset=asset,
            amount=amount,
            venue=venue,
            family=family,
            note=note,
        )
        existing = self._existing_ledger_entry(event_key=event_key)
        if existing:
            return existing
        try:
            item = self._ledger.append(
                entry_type=entry_type,
                asset=asset,
                amount=amount,
                venue=venue,
                chain=str(self.cfg.chain.name),
                family=family,
                note=note,
                metadata={"event_key": str(event_key)},
            ).to_dict()
            if getattr(self, "_ledger_repo", None) is not None:
                self._ledger_repo.append(chain=str(self.cfg.chain.name), payload=item)
            return item
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            OSError,
            sqlite3.Error,
            LedgerConsistencyError,
        ):
            return {}

    async def stress_evaluate(self, *, scenario: str = "standard") -> Dict[str, Any]:
        nav_usd = 0.0
        try:
            nav = await self._pnl.summary(window=100) if hasattr(self._pnl, "summary") else {}
            nav_usd = float(nav.get("total_realized_profit_after_gas_usd") or 0.0)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            nav_usd = 0.0
        risk = 0.0
        try:
            risk = float(getattr(getattr(self, "_fioa", None), "last_stress", 0.0) or 0.0)
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            risk = 0.0
        mults: Dict[str, Dict[str, float | str]] = {
            "liquidity_drop_50": {"nav": -0.035, "exposure": -20.0, "breaker": "drawdownBreaker"},
            "gas_5x": {"nav": -0.018, "exposure": -10.0, "breaker": "gasAnomalyBreaker"},
            "slippage_3x": {"nav": -0.028, "exposure": -15.0, "breaker": "driftBreaker"},
            "noise_injection": {"nav": -0.012, "exposure": -6.0, "breaker": ""},
        }
        cfg = mults.get(str(scenario), mults["noise_injection"])
        projected_nav = max(0.0, nav_usd * (1.0 + float(cfg["nav"]) * max(0.5, 1.0 + risk)))
        return {
            "ok": True,
            "scenario": str(scenario),
            "currentNavUsd": round(nav_usd, 6),
            "projectedNavUsd": round(projected_nav, 6),
            "deltaNavUsd": round(projected_nav - nav_usd, 6),
            "exposureClampPct": round(max(0.0, 100.0 + float(cfg["exposure"])), 2),
            "triggeredBreaker": str(cfg["breaker"] or ""),
            "riskScore": round(risk * 100.0, 2),
        }
