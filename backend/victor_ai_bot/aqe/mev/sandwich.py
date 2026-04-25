from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import PendingTxSummary, MEVConfig


# Common swap selectors (first 4 bytes)
# NOTE: heuristics only; we do NOT decode full calldata (dependency-free).
SWAP_SELECTORS: Dict[str, str] = {
    # Uniswap V2 style
    "0x38ed1739": "swapExactTokensForTokens",
    "0x18cbafe5": "swapExactETHForTokens",
    "0x7ff36ab5": "swapExactETHForTokens",
    "0x4a25d94a": "swapTokensForExactETH",
    "0x8803dbee": "swapTokensForExactTokens",
    "0xfb3bdb41": "swapETHForExactTokens",
    "0x5c11d795": "swapExactTokensForETH",
    # Uniswap V3 router
    "0x414bf389": "exactInputSingle",
    "0xc04b8d59": "exactInput",
    "0xdb3e2198": "exactOutputSingle",
    "0xf28c0498": "exactOutput",
    # Curve router/pools often have different selectors; keep generic
}


@dataclass
class SandwichRisk:
    risk: float
    tags: List[str]
    reason: str


def _is_large_value(tx: PendingTxSummary, cfg: MEVConfig) -> bool:
    return int(tx.value_wei or 0) >= int(cfg.large_value_wei)


def _prio_fee_gwei(tx: PendingTxSummary) -> float:
    # returns gwei
    v = tx.max_priority_fee_per_gas
    if v is None:
        v = tx.gas_price
    if v is None:
        return 0.0
    return float(v) / 1e9


def score_sandwich_risk(tx: PendingTxSummary, cfg: MEVConfig) -> SandwichRisk:
    """Return a defensive risk proxy for being in a high-MEV block.

    This is intentionally conservative and only used as a *safety rail*.
    """

    tags: List[str] = []
    risk = 0.05

    to = (tx.to or "").lower()
    if to and cfg.watched_to:
        if to in [a.lower() for a in cfg.watched_to]:
            risk += 0.25
            tags.append("watched_to")

    sel = (tx.input_0x or "0x")[:10].lower()
    if sel in SWAP_SELECTORS:
        risk += 0.35
        tags.append("swap_selector")
        tags.append(SWAP_SELECTORS[sel])

    if _is_large_value(tx, cfg):
        risk += 0.20
        tags.append("large_value")

    pr = _prio_fee_gwei(tx)
    if pr >= float(cfg.priority_fee_gwei_alert):
        risk += 0.25
        tags.append("high_priority_fee")

    # If tx has no to (contract creation) or unknown input, keep small risk.

    risk = max(0.0, min(1.0, risk))
    reason = "ok"
    if risk >= cfg.high_risk_threshold:
        reason = "high_risk_block_proxy"

    return SandwichRisk(risk=risk, tags=tags, reason=reason)


def summarize_risk(risks: List[float]) -> Tuple[float, float, float]:
    if not risks:
        return 0.0, 0.0, 0.0
    s = sorted(risks)
    p50 = s[int(0.50 * (len(s) - 1))]
    p90 = s[int(0.90 * (len(s) - 1))]
    high = sum(1 for r in s if r >= 0.75) / float(len(s))
    return float(p50), float(p90), float(high)
