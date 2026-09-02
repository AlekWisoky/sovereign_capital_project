from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class MoneyLoopSettlement:
    """Canonical economic classification of one settled trade.

    The signed net P&L is the only quantity allowed to affect owned-capital
    economics and learning. Flash-loan principal is a liability/throughput
    quantity and is never treated as profit or owned bankroll.
    """

    signed_net_pnl_wei: int
    bankroll_loss_wei: int
    positive_profit_wei: int
    flashloan_principal_wei: int
    flashloan_fee_wei: int
    owned_capital_delta_wei: int
    reinvestable_profit_wei: int

    @property
    def profitable(self) -> bool:
        return self.signed_net_pnl_wei > 0

    @property
    def loss(self) -> bool:
        return self.signed_net_pnl_wei < 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["profitable"] = self.profitable
        payload["loss"] = self.loss
        return payload


def classify_settlement(
    *,
    signed_net_pnl_wei: int,
    flashloan_principal_wei: int = 0,
    flashloan_fee_wei: int = 0,
) -> MoneyLoopSettlement:
    """Classify a settled result without allowing borrowed principal to leak into P&L."""

    pnl = int(signed_net_pnl_wei)
    principal = max(0, int(flashloan_principal_wei))
    fee = max(0, int(flashloan_fee_wei))
    positive = max(0, pnl)
    loss = max(0, -pnl)
    return MoneyLoopSettlement(
        signed_net_pnl_wei=pnl,
        bankroll_loss_wei=loss,
        positive_profit_wei=positive,
        flashloan_principal_wei=principal,
        flashloan_fee_wei=fee,
        owned_capital_delta_wei=pnl,
        reinvestable_profit_wei=positive,
    )


def signed_net_pnl_from_metadata(metadata: Mapping[str, Any]) -> int | None:
    """Resolve an explicitly signed settlement P&L from canonical metadata.

    No success boolean is used as a substitute. A missing signed value remains
    unknown so callers can fail closed instead of converting an unpriced loss
    into zero P&L.
    """

    for key in (
        "signed_net_pnl_wei",
        "signedNetPnlWei",
        "net_realized_pnl_wei",
        "netRealizedPnlWei",
    ):
        value = metadata.get(key)
        if value is None or value == "":
            continue
        try:
            return int(str(value))
        except (TypeError, ValueError):
            continue
    return None
