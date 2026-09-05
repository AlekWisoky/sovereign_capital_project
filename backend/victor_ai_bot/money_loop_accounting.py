from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

_SAFE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError)


@dataclass(frozen=True)
class SettledReceiptEconomics:
    """Canonical economic facts derived from a settled receipt transaction."""

    receipt_id: str
    transaction_id: str
    status: int
    amount_in_wei: int
    realized_after_gas_wei: int
    realized_after_gas_usd: float
    gas_cost_usd: float
    borrow_cost_usd: float
    signed_pnl_usd: float
    success: bool
    source: str = "canonical_receipt_settlement"

    @property
    def loss_usd(self) -> float:
        return max(0.0, -float(self.signed_pnl_usd))

    @property
    def reinvestable_profit_usd(self) -> float:
        return max(0.0, float(self.signed_pnl_usd))

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["loss_usd"] = round(self.loss_usd, 8)
        out["reinvestable_profit_usd"] = round(self.reinvestable_profit_usd, 8)
        return out


class MoneyLoopAccounting:
    """Translate a canonical settled receipt transaction into signed economics."""

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except _SAFE_EXCEPTIONS:
            return float(default)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value))
        except _SAFE_EXCEPTIONS:
            return int(default)

    @classmethod
    def from_settlement_payload(
        cls, payload: Mapping[str, Any], *, receipt_id: str = ""
    ) -> SettledReceiptEconomics:
        raw = dict(payload or {})
        metadata = raw.get("metadata")
        meta = dict(metadata or {}) if isinstance(metadata, Mapping) else raw
        resolved_receipt_id = str(raw.get("receipt_id") or receipt_id or "")
        transaction_id = str(raw.get("transaction_id") or "")
        status = cls._safe_int(meta.get("status"), cls._safe_int(raw.get("status"), 0))
        amount_in_wei = cls._safe_int(meta.get("amount_in_wei"), 0)
        realized_after_gas_wei = cls._safe_int(
            meta.get("realized_after_gas_wei") or meta.get("realized_profit_after_gas_wei"), 0
        )
        realized_after_gas_usd = cls._safe_float(meta.get("realized_after_gas_usd"), 0.0)
        gas_cost_usd = cls._safe_float(meta.get("gas_cost_usd"), 0.0)
        borrow_cost_usd = cls._safe_float(meta.get("borrow_cost_usd"), 0.0)
        net_value = meta.get("net_realized_usd")
        if net_value is None:
            signed_pnl_usd = realized_after_gas_usd - borrow_cost_usd
            if status != 1:
                signed_pnl_usd -= gas_cost_usd
        else:
            signed_pnl_usd = cls._safe_float(net_value, 0.0)
        return SettledReceiptEconomics(
            receipt_id=resolved_receipt_id,
            transaction_id=transaction_id,
            status=status,
            amount_in_wei=amount_in_wei,
            realized_after_gas_wei=realized_after_gas_wei,
            realized_after_gas_usd=round(realized_after_gas_usd, 8),
            gas_cost_usd=round(gas_cost_usd, 8),
            borrow_cost_usd=round(borrow_cost_usd, 8),
            signed_pnl_usd=round(signed_pnl_usd, 8),
            success=bool(status == 1),
        )

    @classmethod
    def from_ledger_transaction(cls, tx: Mapping[str, Any]) -> SettledReceiptEconomics:
        return cls.from_settlement_payload(tx, receipt_id=str(tx.get("receipt_id") or ""))
