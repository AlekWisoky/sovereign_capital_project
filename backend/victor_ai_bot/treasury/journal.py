from __future__ import annotations

from typing import Any, Dict

from .ledger import TreasuryLedger


def record_realized_pnl(
    ledger: TreasuryLedger,
    *,
    asset: str,
    amount: float,
    family: str,
    venue: str = "",
    chain: str = "",
    note: str = "realized_pnl",
    receipt_id: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return ledger.append(
        entry_type="realized_pnl",
        asset=asset,
        amount=amount,
        family=family,
        venue=venue,
        chain=chain,
        note=note,
        receipt_id=receipt_id,
        metadata=dict(metadata or {}),
    ).to_dict()


def record_borrow_cost(
    ledger: TreasuryLedger,
    *,
    asset: str,
    amount: float,
    family: str,
    venue: str = "",
    chain: str = "",
    note: str = "borrow_cost",
    receipt_id: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return ledger.append(
        entry_type="borrow_cost",
        asset=asset,
        amount=-abs(amount),
        family=family,
        venue=venue,
        chain=chain,
        note=note,
        receipt_id=receipt_id,
        metadata=dict(metadata or {}),
    ).to_dict()


def record_settlement_loss(
    ledger: TreasuryLedger,
    *,
    asset: str,
    amount: float,
    family: str,
    venue: str = "",
    chain: str = "",
    note: str = "settlement_loss",
    receipt_id: str = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return ledger.append(
        entry_type="settlement_loss",
        asset=asset,
        amount=-abs(amount),
        family=family,
        venue=venue,
        chain=chain,
        note=note,
        receipt_id=receipt_id,
        metadata=dict(metadata or {}),
    ).to_dict()
