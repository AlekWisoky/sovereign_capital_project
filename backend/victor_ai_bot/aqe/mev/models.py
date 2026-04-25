from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PendingTxSummary:
    tx_hash: str
    to: str = ""
    frm: str = ""
    nonce: int | None = None
    value_wei: int = 0
    max_fee_per_gas: int | None = None
    max_priority_fee_per_gas: int | None = None
    gas_price: int | None = None
    gas: int | None = None
    input_0x: str = "0x"
    first_seen_ts: float = 0.0
    last_seen_ts: float = 0.0

    # Heuristic tags
    tags: List[str] = field(default_factory=list)
    dex_hint: str = ""  # e.g., univ2/univ3/curve/agg


@dataclass
class MEVConfig:
    """Execution-time MEV module config.

    Safe defaults:
    - disabled
    - defensive mode
    - refuse public send if high risk
    """

    enabled: bool = False
    mode: str = "defensive"  # defensive|research

    # Mempool
    ws: List[str] = field(default_factory=list)  # optional override; falls back to chain.ws
    max_pending: int = 2000
    sample_rate: float = 1.0  # 0..1
    reconnect_backoff_s: float = 2.0

    # Router allowlist for analysis (optional; empty => heuristic only)
    watched_to: List[str] = field(default_factory=list)

    # Safety rail
    refuse_public_send_on_high_risk: bool = True
    high_risk_threshold: float = 0.75

    # Evaluation knobs
    large_value_wei: int = 2 * 10**18
    priority_fee_gwei_alert: int = 10

    # Private routing suggestions
    suggest_private_when_risky: bool = True


@dataclass
class MEVState:
    ok: bool = True
    enabled: bool = False
    mode: str = "defensive"
    connected: bool = False
    ws_url: str = ""

    pending_count: int = 0
    last_error: str = ""

    # Summary metrics
    sandwich_risk_p50: float = 0.0
    sandwich_risk_p90: float = 0.0
    high_risk_ratio: float = 0.0

    last_update_ts: float = 0.0

    # Bounded samples
    sample_pending: List[Dict[str, Any]] = field(default_factory=list)
