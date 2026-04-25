from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any

DexType = Literal["univ3", "curve", "balancer"]


class RouteLeg(BaseModel):
    dex: DexType
    venue: str
    token_in: str
    token_out: str
    amount_in: str
    min_out: str
    data: str = ""


class Route(BaseModel):
    legs: List[RouteLeg]


class Opportunity(BaseModel):
    id: str
    chain: str
    strategy: str
    expected_profit_raw: str
    expected_profit_usd: str
    route: Route
    min_outs: List[str]
    # Additive: deterministic identifier of the canonical route encoding.
    # Safe default is empty string.
    route_id: str = ""
    can_execute: bool = False
    created_at_ms: int = 0
    meta: Dict[str, Any] = Field(default_factory=dict)


class Metrics(BaseModel):
    flashLoans: int = 0
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    last_block: int = 0
    scan_ms: int = 0
    last_error: str = ""
    last_submitted_block: int = 0
    gas_mode: str = "standard"
    send_mode: str = "public"
    realized_profit_raw: str = "0"
    efficiency_pct: float = 0.0
    success_rate_pct: float = 0.0

    # --- Health / observability counters (additive; safe defaults) ---
    failed_ticks: int = 0
    last_tick_ms: int = 0
    db_latency_ms: float = 0.0
    db_latency_ema_ms: float = 0.0
    db_errors: int = 0
    pnl_summary_cache_hits: int = 0
    pnl_summary_cache_misses: int = 0
    pnl_income_cache_hits: int = 0
    pnl_income_cache_misses: int = 0

    # --- Latency percentiles (observability-only; additive) ---
    exec_e2e_p50_ms: float = 0.0
    exec_e2e_p90_ms: float = 0.0
    exec_e2e_p99_ms: float = 0.0
    submit_to_receipt_p50_ms: float = 0.0
    submit_to_receipt_p90_ms: float = 0.0
    submit_to_receipt_p99_ms: float = 0.0
    loop_p50_ms: float = 0.0
    loop_p90_ms: float = 0.0
    loop_p99_ms: float = 0.0


class RuntimeState(BaseModel):
    chain: str
    opportunities: List[Opportunity]
    metrics: Metrics
    rpc: Dict[str, Any] = Field(default_factory=dict)
