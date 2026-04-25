from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import importlib
import os, yaml
import pathlib

from .superstructure.config import SuperstructureConfig
from .fioa.config import FIOAConfig
from .llm_inl.config import LLMINLConfig
from .behaveagent.config import BehaveAgentConfig
from .analytics.quicksight import QuickSightAnalyticsConfig, RBACConfig, ReportAutomationConfig
from .treasury.config import TreasuryConfig, ProfitGoal
from .governance.config import GovernanceConfig

def _import_optional_symbol(module_name: str, symbol_name: str):
    try:
        module = importlib.import_module(module_name, __package__)
    except ModuleNotFoundError as exc:  # pragma: no cover
        if exc.name in {module_name, f"{__package__}.{module_name.lstrip('.')}"}:
            return None
        raise
    return getattr(module, symbol_name)


SpreadEngineConfig = _import_optional_symbol('.aqe.spread.engine', 'SpreadEngineConfig')  # type: ignore
ConsensusConfig = _import_optional_symbol('.aqe.coordination.consensus_engine', 'ConsensusConfig')  # type: ignore


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


@dataclass
class SafetyConfig:
    minProfitAbs: str = "0"  # wei (string)
    minProfitBps: int = 0  # bps of amount_in
    slippage_bps: int = 50
    max_borrow_amount: str = "0"  # wei (string)
    require_estimate_gas: bool = True
    require_simulation: bool = False

    # --- Enhanced preflight models (additive, gated) ---
    dynamic_slippage_enabled: bool = True
    # Probe size in bps for price-impact estimation during requote (preflight only).
    dynamic_slippage_probe_bps: int = 25
    # Multiplier applied to inferred impact bps when computing final slippage bps.
    dynamic_slippage_impact_mult: float = 1.0
    dynamic_slippage_min_bps: int = 20
    dynamic_slippage_max_bps: int = 250

    # Adversarial MEV / execution risk evaluation
    mev_adversarial_eval_enabled: bool = True
    # How strongly MEV risk reduces p_success (0..1). Higher => more conservative.
    mev_fail_prob_scale: float = 0.55
    # Additional gas premium multiplier under MEV stress.
    mev_gas_premium_mult: float = 0.35
    # Require risk-adjusted EV > 0 to proceed.
    require_adversarial_ev_positive: bool = True

    # Simulation enhancements
    simulation_try_pending: bool = False
    simulation_prev_blocks: int = 0
    simulation_soft_fail: bool = True


@dataclass
class StrategyFlags:
    enable_two_leg_loops: bool = True
    enable_curve_autogen: bool = True
    enable_balancer_autogen: bool = True
    # Alpha scanning (additive)
    enable_three_leg_loops: bool = False
    enable_v3_triangular: bool = False  # alias/compat; kept for older configs
    enable_discovery: bool = False


@dataclass
class GasPresets:
    # Values in gwei
    standard_max_fee_gwei: int = 25
    standard_priority_fee_gwei: int = 2
    fast_max_fee_gwei: int = 40
    fast_priority_fee_gwei: int = 3
    instant_max_fee_gwei: int = 60
    instant_priority_fee_gwei: int = 4


@dataclass
class ArbitrageConfig:
    """Phase 5: Cross-venue arbitrage engine config (CEX/CEX + optional DEX hooks).

    Safe defaults:
    - disabled
    - observe-only
    - 1x leverage
    - conservative thresholds

    Notes:
    - This engine is additive and does not change the core DeFi flash-loan arb loop.
    - Execution requires explicit enablement and credentials (not part of safe defaults).
    """

    enabled: bool = False
    mode: str = "observe"  # observe|suggest|auto (auto is off by default)
    poll_seconds: float = 2.0

    # Universe
    pairs: List[str] = field(default_factory=list)  # e.g., ["BTCUSDT", "ETHUSDT"]
    venues: List[Dict[str, Any]] = field(default_factory=list)
    # Each venue entry example:
    # {"name": "binance", "product": "spot"}
    # {"name": "binance", "product": "futures"}

    # Risk / sizing
    leverage: float = 1.0
    max_notional_usd: float = 2500.0
    min_spread_bps: int = 8
    min_net_profit_usd: float = 2.0

    # Fees (fallback). Adapters may override.
    taker_fee_bps: int = 10
    maker_fee_bps: int = 2

    # Transfer latency risk model (heuristic). Provide per-venue seconds.
    latency_seconds: Dict[str, float] = field(default_factory=dict)

    # Safety rails
    max_open_positions: int = 1
    circuit_breaker_vol_spike: float = 0.15  # 15% sudden move disables auto
    allow_execution: bool = False  # must be explicitly enabled for any live trading


@dataclass
class MEVConfig:
    """Phase 6: MEV module config (defensive-first).

    Safe defaults:
    - disabled
    - refuse public submission when mempool risk proxy is high
    - research features off
    """

    enabled: bool = False
    mode: str = "defensive"  # defensive|research

    ws: List[str] = field(default_factory=list)
    max_pending: int = 2000
    sample_rate: float = 1.0
    reconnect_backoff_s: float = 2.0

    watched_to: List[str] = field(default_factory=list)

    refuse_public_send_on_high_risk: bool = True
    high_risk_threshold: float = 0.75

    large_value_wei: int = 2 * 10**18
    priority_fee_gwei_alert: int = 10

    suggest_private_when_risky: bool = True


@dataclass
class MetaEvolutionConfig:
    """Phase 7: Meta-strategy generator + evolutionary mutation engine (safe, additive).

    Safe defaults:
    - disabled
    - observe mode
    - never enables auto_trading

    Modes:
      observe  : only expose telemetry and on-demand generation
      suggest  : periodically generate candidates for operator review
      auto     : may apply top candidates ONLY if allow_auto_apply is true (see env)
    """

    enabled: bool = False
    mode: str = "observe"
    tick_seconds: float = 10.0

    # Generation bounds (conservative)
    max_candidates: int = 5
    max_registry_items: int = 200
    max_slippage_bps: int = 120
    min_profit_abs_bump_wei: int = 2 * 10**15
    min_profit_bps_step: int = 10
    max_min_profit_bps: int = 80
    max_submit_per_block: int = 2
    min_trade_cooldown: int = 2

    # Allow private suggestion in high gas regimes
    allow_private: bool = True


@dataclass
class RFTConfig:
    enabled: bool = False
    episode_export_enabled: bool = False
    snapshot_top_k: int = 20
    enable_reward_trace_export: bool = True
    grader_weights: Dict[str, int] = field(
        default_factory=lambda: {
            "schema": 100,
            "policy": 100,
            "capital": 100,
            "profit": 100,
            "risk": 100,
            "latency": 100,
        }
    )


@dataclass
class ExecutionConfig:
    # bankroll / compounding
    auto_reinvest_enabled: bool = False
    reinvest_rate: int = 0  # 0-100
    base_borrow_amount: str = "0"  # wei string (optional override)
    # Phase B7: Kelly fraction bankroll sizing
    # Backwards compatible default: OFF.
    # Enable explicitly once enough history exists for stable sizing.
    kelly_enabled: bool = False
    kelly_window: int = 50
    # Backwards-compatibility / safety: only apply Kelly after sufficient
    # trade history has accumulated.
    kelly_min_history: int = 20
    # Higher cap enables up-sizing in strong regimes while remaining bounded
    # by global caps and governance.
    kelly_cap_fraction: float = 0.75
    # Small floor prevents the first few trades from being scaled down too
    # aggressively when history is sparse.
    kelly_min_fraction: float = 0.05
    volatility_downscale: float = 0.35
    dry_run: bool = True
    auto_trading: bool = False
    send_mode: str = "public"  # public/private/protected_rpc
    gas_mode: str = "standard"  # standard/fast/instant
    gas_limit: int = 550_000
    max_submit_per_block: int = 1
    deadline_seconds: int = 30
    redact_routes_when_private: bool = True
    # signing/executor (optional)
    private_key_env: str = "VICTOR_PRIVATE_KEY"
    # Optional sender override for simulation/estimateGas in dry-run environments.
    # If empty, the backend uses the private key address when available.
    from_address: str = ""
    executor_address: str = ""  # contract
    profit_to: str = ""  # address, optional
    # --- Profit withdrawal ---
    # Mobile app can request tx data to withdraw from the executor contract, or the backend can execute it
    # if it holds the executor owner key. Always restrict destinations via allowlists.
    withdraw_mode: str = "txdata"  # txdata|backend
    withdraw_allowlist: List[str] = field(default_factory=list)  # destination addresses
    withdraw_tokens: List[str] = field(default_factory=list)  # token addresses for UI convenience

    flash_provider: str = "aave"  # aave|balancer
    flashloan_fee_bps: int = 9  # ASSUMPTION: 9 bps default
    gas_presets: GasPresets = field(default_factory=GasPresets)

    # --- Decisioning / RL (additive) ---
    brain_mode: str = "off"  # off|shadow|suggest|auto
    min_p_success: float = 0.70
    trade_cooldown_blocks: int = 1
    max_pending_txs: int = 1
    daily_gas_budget_wei: str = "0"  # optional cap; 0 disables

    # --- Unit economics / USD accounting (additive, analytics-only) ---
    usd_accounting_enabled: bool = False
    # Preferred stable for USD conversions when both are available.
    usd_stable_preference: str = "usdc"  # usdc|usdt

    # v1 production scope lock.
    # Choose ONE and win deeply before enabling additional modules.
    v1_focus: str = (
        "flashloan_atomic"  # flashloan_atomic|cross_exchange|funding_capture|mev_defense
    )

    # --- Executor ABI drift protection (additive) ---
    enforce_executor_version: bool = False
    expected_executor_abi_version: int = 2

    # --- RFT export / grading (proposal-only, additive) ---
    rft: RFTConfig = field(default_factory=RFTConfig)

    # --- Phase B1: BehaveAgent (additive) ---
    behaveagent: BehaveAgentConfig = field(default_factory=BehaveAgentConfig)

    # --- Phase V9: QuickSight Analytics (additive) ---
    analytics: QuickSightAnalyticsConfig = field(default_factory=QuickSightAnalyticsConfig)

    # --- Phase B5/B8: Spread Engine + Unified overlays (additive) ---
    spread: Any = field(
        default_factory=lambda: SpreadEngineConfig() if SpreadEngineConfig else None
    )

    # --- Phase B3/B4: Consensus (additive) ---
    consensus: Any = field(default_factory=lambda: ConsensusConfig() if ConsensusConfig else None)

    # --- Treasury & capital optimization layer (additive) ---
    treasury: TreasuryConfig = field(default_factory=TreasuryConfig)

    # --- Blockchain Agent Standard governance layer (additive) ---
    governance: GovernanceConfig = field(default_factory=GovernanceConfig)

    # --- Phase 5: Arbitrage Engine (additive) ---
    arbitrage: ArbitrageConfig = field(default_factory=ArbitrageConfig)

    # --- Phase 6: MEV module (additive, defensive-first) ---
    mev: MEVConfig = field(default_factory=MEVConfig)

    # --- Phase 7: Meta strategy generator (additive) ---
    meta: MetaEvolutionConfig = field(default_factory=MetaEvolutionConfig)

    # --- Phase 14+: Organizational Superstructure (additive) ---
    superstructure: SuperstructureConfig = field(default_factory=SuperstructureConfig)

    # --- Phase 20: FIOA (FIU-inspired Operational Independence layer) ---
    fioa: FIOAConfig = field(default_factory=FIOAConfig)

    # --- Phase 21: LLM-INL (LLM-mediated Interactive Narrative Layer) ---
    llm_inl: LLMINLConfig = field(default_factory=LLMINLConfig)


@dataclass
class ChainConfig:
    name: str
    chain_id: int
    rpc_read: List[str] = field(default_factory=list)
    rpc_send: List[str] = field(default_factory=list)
    rpc_private: List[str] = field(default_factory=list)
    ws: List[str] = field(default_factory=list)
    univ3_quoter_v2: str = ""
    univ3_factory: str = ""  # optional; enables bounded discovery
    univ3_swap_router: str = ""  # executor uses SwapRouter; quoting uses QuoterV2
    balancer_vault: str = ""
    aave_v3_pool: str = ""
    weth: str = ""
    # Optional stablecoins for USD accounting / off-ramp UX.
    usdc: str = ""
    usdt: str = ""
    # Discovery token universe (addresses). Optional.
    token_universe: List[str] = field(default_factory=list)
    discovery_interval_blocks: int = 50
    discovery_max_calls: int = 24
    # candidate edges
    v3_pairs: List[dict] = field(default_factory=list)
    curve_pools: List[dict] = field(default_factory=list)
    balancer_pools: List[dict] = field(default_factory=list)


@dataclass
class AppConfig:
    chain: ChainConfig
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    flags: StrategyFlags = field(default_factory=StrategyFlags)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)


def load_configs_from_env(default_cfg_path: str) -> List[AppConfig]:
    """Load one or more configs from environment variables.

    - If VICTOR_MULTI_CONFIGS is set: comma-separated yaml paths are loaded.
    - Else: VICTOR_CONFIG is loaded.

    Safe default: if any config path is missing/unreadable, it is skipped and
    an empty list is never returned (we fall back to default_cfg_path).
    """
    multi = os.environ.get("VICTOR_MULTI_CONFIGS")
    if multi:
        out: List[AppConfig] = []
        for p in [x.strip() for x in multi.split(",") if x.strip()]:
            try:
                out.append(load_config(p))
            except (FileNotFoundError, OSError, TypeError, ValueError, yaml.YAMLError):
                # Safe default: skip invalid entries.
                continue
        if out:
            return out
    single = os.environ.get("VICTOR_CONFIG") or default_cfg_path
    return [load_config(single)]


def load_config(path: str) -> AppConfig:
    p = pathlib.Path(path)
    if not p.exists():
        # Common repo layout: configs live under `backend/config/` but callers/tests
        # may reference `config/...` from repo root.
        if path.startswith("config/") or path.startswith("config\\"):
            alt = pathlib.Path("backend") / p
            if alt.exists():
                p = alt
        else:
            # best-effort: if given `ethereum.yaml`, try `backend/config/ethereum.yaml`
            alt2 = pathlib.Path("backend") / "config" / p.name
            if alt2.exists():
                p = alt2

    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    chain_raw = raw.get("chain", raw)
    name = chain_raw.get("name", os.path.splitext(os.path.basename(str(p)))[0])
    chain_id = int(chain_raw.get("chain_id") or chain_raw.get("chainId") or 0)
    # Candidate lists may live under `chain:` or at top-level (legacy presets).
    v3_pairs = chain_raw.get("v3_pairs") or raw.get("v3_pairs") or []
    curve_pools = chain_raw.get("curve_pools") or raw.get("curve_pools") or []
    balancer_pools = chain_raw.get("balancer_pools") or raw.get("balancer_pools") or []

    chain = ChainConfig(
        name=name,
        chain_id=chain_id,
        rpc_read=_as_list(chain_raw.get("rpc_read") or chain_raw.get("rpc") or []),
        rpc_send=_as_list(chain_raw.get("rpc_send") or chain_raw.get("rpc") or []),
        rpc_private=_as_list(chain_raw.get("rpc_private") or []),
        ws=_as_list(chain_raw.get("ws") or []),
        univ3_quoter_v2=str(chain_raw.get("univ3_quoter_v2") or ""),
        univ3_factory=str(chain_raw.get("univ3_factory") or ""),
        univ3_swap_router=str(chain_raw.get("univ3_swap_router") or ""),
        balancer_vault=str(chain_raw.get("balancer_vault") or ""),
        aave_v3_pool=str(chain_raw.get("aave_v3_pool") or ""),
        weth=str(chain_raw.get("weth") or ""),
        usdc=str(chain_raw.get("usdc") or ""),
        usdt=str(chain_raw.get("usdt") or ""),
        token_universe=_as_list(chain_raw.get("token_universe") or []),
        discovery_interval_blocks=int(chain_raw.get("discovery_interval_blocks") or 50),
        discovery_max_calls=int(chain_raw.get("discovery_max_calls") or 24),
        v3_pairs=v3_pairs,
        curve_pools=curve_pools,
        balancer_pools=balancer_pools,
    )
    sraw = raw.get("safety") or {}
    safety = SafetyConfig(
        minProfitAbs=str(sraw.get("minProfitAbs", "0")),
        minProfitBps=int(sraw.get("minProfitBps", 0)),
        slippage_bps=int(sraw.get("slippage_bps", 50)),
        max_borrow_amount=str(sraw.get("max_borrow_amount", "0")),
        require_estimate_gas=bool(sraw.get("require_estimate_gas", True)),
        require_simulation=bool(sraw.get("require_simulation", False)),
        dynamic_slippage_enabled=bool(sraw.get("dynamic_slippage_enabled", True)),
        dynamic_slippage_probe_bps=int(sraw.get("dynamic_slippage_probe_bps", 25)),
        dynamic_slippage_impact_mult=float(sraw.get("dynamic_slippage_impact_mult", 1.0)),
        dynamic_slippage_min_bps=int(sraw.get("dynamic_slippage_min_bps", 20)),
        dynamic_slippage_max_bps=int(sraw.get("dynamic_slippage_max_bps", 250)),
        mev_adversarial_eval_enabled=bool(sraw.get("mev_adversarial_eval_enabled", True)),
        mev_fail_prob_scale=float(sraw.get("mev_fail_prob_scale", 0.55)),
        mev_gas_premium_mult=float(sraw.get("mev_gas_premium_mult", 0.35)),
        require_adversarial_ev_positive=bool(sraw.get("require_adversarial_ev_positive", True)),
        simulation_try_pending=bool(sraw.get("simulation_try_pending", False)),
        simulation_prev_blocks=int(sraw.get("simulation_prev_blocks", 0)),
        simulation_soft_fail=bool(sraw.get("simulation_soft_fail", True)),
    )
    fraw = raw.get("flags") or {}
    flags = StrategyFlags(
        enable_two_leg_loops=bool(fraw.get("enable_two_leg_loops", True)),
        enable_curve_autogen=bool(fraw.get("enable_curve_autogen", True)),
        enable_balancer_autogen=bool(fraw.get("enable_balancer_autogen", True)),
        enable_three_leg_loops=bool(fraw.get("enable_three_leg_loops", False)),
        enable_v3_triangular=bool(fraw.get("enable_v3_triangular", False)),
        enable_discovery=bool(fraw.get("enable_discovery", False)),
    )
    eraw = raw.get("execution") or {}
    rftraw = eraw.get("rft") or raw.get("rft") or {}
    wraw = eraw.get("withdraw") or {}
    graw = eraw.get("gas_presets") or {}
    gas_presets = GasPresets(
        standard_max_fee_gwei=int(graw.get("standard_max_fee_gwei", 25)),
        standard_priority_fee_gwei=int(graw.get("standard_priority_fee_gwei", 2)),
        fast_max_fee_gwei=int(graw.get("fast_max_fee_gwei", 40)),
        fast_priority_fee_gwei=int(graw.get("fast_priority_fee_gwei", 3)),
        instant_max_fee_gwei=int(graw.get("instant_max_fee_gwei", 60)),
        instant_priority_fee_gwei=int(graw.get("instant_priority_fee_gwei", 4)),
    )
    araw = eraw.get("arbitrage") or {}
    arbitrage = ArbitrageConfig(
        enabled=bool(araw.get("enabled", eraw.get("arbitrage_enabled", False))),
        mode=str(araw.get("mode", "observe")),
        poll_seconds=float(araw.get("poll_seconds", 2.0)),
        pairs=_as_list(araw.get("pairs") or []),
        venues=list(araw.get("venues") or []),
        leverage=float(araw.get("leverage", 1.0)),
        max_notional_usd=float(araw.get("max_notional_usd", 2500.0)),
        min_spread_bps=int(araw.get("min_spread_bps", 8)),
        min_net_profit_usd=float(araw.get("min_net_profit_usd", 2.0)),
        taker_fee_bps=int(araw.get("taker_fee_bps", 10)),
        maker_fee_bps=int(araw.get("maker_fee_bps", 2)),
        latency_seconds=dict(araw.get("latency_seconds") or {}),
        max_open_positions=int(araw.get("max_open_positions", 1)),
        circuit_breaker_vol_spike=float(araw.get("circuit_breaker_vol_spike", 0.15)),
        allow_execution=bool(araw.get("allow_execution", False)),
    )
    mraw = eraw.get("mev") or {}
    mev = MEVConfig(
        enabled=bool(mraw.get("enabled", eraw.get("mev_enabled", False))),
        mode=str(mraw.get("mode", "defensive")),
        ws=_as_list(mraw.get("ws") or []),
        max_pending=int(mraw.get("max_pending", 2000)),
        sample_rate=float(mraw.get("sample_rate", 1.0)),
        reconnect_backoff_s=float(mraw.get("reconnect_backoff_s", 2.0)),
        watched_to=_as_list(mraw.get("watched_to") or []),
        refuse_public_send_on_high_risk=bool(mraw.get("refuse_public_send_on_high_risk", True)),
        high_risk_threshold=float(mraw.get("high_risk_threshold", 0.75)),
        large_value_wei=int(mraw.get("large_value_wei", 2 * 10**18)),
        priority_fee_gwei_alert=int(mraw.get("priority_fee_gwei_alert", 10)),
        suggest_private_when_risky=bool(mraw.get("suggest_private_when_risky", True)),
    )
    metaraw = eraw.get("meta") or {}
    meta = MetaEvolutionConfig(
        enabled=bool(metaraw.get("enabled", False)),
        mode=str(metaraw.get("mode", "observe")),
        tick_seconds=float(metaraw.get("tick_seconds", 10.0)),
        max_candidates=int(metaraw.get("max_candidates", 5)),
        max_registry_items=int(metaraw.get("max_registry_items", 200)),
        max_slippage_bps=int(metaraw.get("max_slippage_bps", 120)),
        min_profit_abs_bump_wei=int(metaraw.get("min_profit_abs_bump_wei", 2 * 10**15)),
        min_profit_bps_step=int(metaraw.get("min_profit_bps_step", 10)),
        max_min_profit_bps=int(metaraw.get("max_min_profit_bps", 80)),
        max_submit_per_block=int(metaraw.get("max_submit_per_block", 2)),
        min_trade_cooldown=int(metaraw.get("min_trade_cooldown", 2)),
        allow_private=bool(metaraw.get("allow_private", True)),
    )

    ssraw = eraw.get("superstructure") or {}
    superstructure = SuperstructureConfig(
        enabled=bool(ssraw.get("enabled", eraw.get("superstructure_enabled", False))),
        require_negotiation=bool(ssraw.get("require_negotiation", True)),
        require_capital_auction=bool(ssraw.get("require_capital_auction", True)),
        require_path_planning=bool(ssraw.get("require_path_planning", True)),
        lambda_risk=float(ssraw.get("lambda_risk", 1.0)),
        lambda_latency=float(ssraw.get("lambda_latency", 0.05)),
        lambda_funding=float(ssraw.get("lambda_funding", 0.5)),
        lambda_reliability=float(ssraw.get("lambda_reliability", 0.6)),
        lambda_graph_conf=float(ssraw.get("lambda_graph_conf", 0.4)),
        capital_total_wei=str(ssraw.get("capital_total_wei", "0")),
        max_capital_fraction_per_task=float(ssraw.get("max_capital_fraction_per_task", 0.60)),
        risk_override_drawdown=float(ssraw.get("risk_override_drawdown", 0.15)),
        entropy_spike_th=float(ssraw.get("entropy_spike_th", 0.25)),
        human_enabled=bool(ssraw.get("human_enabled", True)),
        human_high_risk_threshold=float(ssraw.get("human_high_risk_threshold", 0.80)),
        human_require_approval_for_high_risk=bool(
            ssraw.get("human_require_approval_for_high_risk", True)
        ),
        enable_stability_monitor=bool(ssraw.get("enable_stability_monitor", True)),
        instability_trip_threshold=float(ssraw.get("instability_trip_threshold", 0.75)),
        instability_cooldown_s=float(ssraw.get("instability_cooldown_s", 120.0)),
    )

    # -------------------------
    # Phase 20: FIOA overlay
    # -------------------------
    fioaraw = eraw.get("fioa") or {}
    # Allow legacy enable flag
    fioa_enabled = bool(fioaraw.get("enabled", eraw.get("fioa_enabled", False)))
    # Agent scope override (dict)
    agent_scope = fioaraw.get("agent_scope")
    if isinstance(agent_scope, dict):
        agent_scope = {str(k): str(v) for k, v in agent_scope.items()}
    else:
        agent_scope = None

    # Merge with defaults so HUMAN_OPERATOR escape hatch stays available unless
    # explicitly overridden.
    _default_scope = FIOAConfig().agent_scope
    if agent_scope is not None:
        merged = dict(_default_scope)
        merged.update(agent_scope)
        agent_scope = merged
    else:
        agent_scope = dict(_default_scope)
    fioa = FIOAConfig(
        enabled=fioa_enabled,
        system_mode=str(fioaraw.get("system_mode", "AUTONOMOUS_MULTI_AGENT")),
        architecture_lock=bool(fioaraw.get("architecture_lock", True)),
        core_commands_immutable=bool(fioaraw.get("core_commands_immutable", True)),
        agent_scope=agent_scope,
        max_capital_per_agent=float(fioaraw.get("max_capital_per_agent", 0.25)),
        max_risk_exposure=float(fioaraw.get("max_risk_exposure", 0.18)),
        max_leverage=float(fioaraw.get("max_leverage", 3.0)),
        strategy_director_enabled=bool(fioaraw.get("strategy_director_enabled", True)),
        strategy_review_interval=int(fioaraw.get("strategy_review_interval", 300)),
        enable_dynamic_sizing=bool(fioaraw.get("enable_dynamic_sizing", False)),
        target_success_rate=float(fioaraw.get("target_success_rate", 0.75)),
        sizing_up_step_pct=float(fioaraw.get("sizing_up_step_pct", 5.0)),
        sizing_down_step_pct=float(fioaraw.get("sizing_down_step_pct", 10.0)),
        sizing_min_step_interval_s=float(fioaraw.get("sizing_min_step_interval_s", 60.0)),
        confidentiality_enabled=bool(fioaraw.get("confidentiality_enabled", True)),
        confidentiality_strict=bool(fioaraw.get("confidentiality_strict", False)),
        escalation_threshold=float(fioaraw.get("escalation_threshold", 0.85)),
        safe_mode_default_ttl_s=float(fioaraw.get("safe_mode_default_ttl_s", 120.0)),
        audit_enabled=bool(fioaraw.get("audit_enabled", True)),
        audit_max_bytes=int(fioaraw.get("audit_max_bytes", 25_000_000)),
        stress_w_fail_streak=float(fioaraw.get("stress_w_fail_streak", 0.35)),
        stress_w_mev=float(fioaraw.get("stress_w_mev", 0.25)),
        stress_w_gas=float(fioaraw.get("stress_w_gas", 0.20)),
        stress_w_rpc=float(fioaraw.get("stress_w_rpc", 0.10)),
        stress_w_pending=float(fioaraw.get("stress_w_pending", 0.10)),
    )

    # -------------------------
    # Phase 21: LLM-INL overlay
    # -------------------------
    inlraw = eraw.get("llm_inl") or {}
    inl_enabled = bool(inlraw.get("enabled", eraw.get("llm_inl_enabled", False)))
    llm_inl = LLMINLConfig(
        enabled=inl_enabled,
        system_mode=str(inlraw.get("system_mode", "AUTONOMOUS_MULTI_AGENT")),
        architecture_lock=bool(inlraw.get("architecture_lock", True)),
        core_commands_immutable=bool(inlraw.get("core_commands_immutable", True)),
        max_narrative_memory=int(inlraw.get("max_narrative_memory", 100)),
        persist_history=bool(inlraw.get("persist_history", True)),
        interactive_mode=bool(inlraw.get("interactive_mode", True)),
        require_admin_for_queries=bool(inlraw.get("require_admin_for_queries", True)),
        explanation_level=str(inlraw.get("explanation_level", "STANDARD")),
        conflict_mediation_enabled=bool(inlraw.get("conflict_mediation_enabled", True)),
        audit_enabled=bool(inlraw.get("audit_enabled", True)),
        audit_max_bytes=int(inlraw.get("audit_max_bytes", 25_000_000)),
        loop_interval_s=float(inlraw.get("loop_interval_s", 1.0)),
        emit_block_summaries=bool(inlraw.get("emit_block_summaries", False)),
        block_summary_interval_blocks=int(inlraw.get("block_summary_interval_blocks", 5)),
        block_summary_min_profit_wei=int(inlraw.get("block_summary_min_profit_wei", 0)),
        llm_mode=str(inlraw.get("llm_mode", "template")),
        llm_provider=str(inlraw.get("llm_provider", "openai")),
        llm_api_key_env=str(inlraw.get("llm_api_key_env", "VICTOR_LLM_API_KEY")),
        llm_model=str(inlraw.get("llm_model", "gpt-4o-mini")),
        llm_endpoint=str(inlraw.get("llm_endpoint", "https://api.openai.com/v1/chat/completions")),
        llm_timeout_s=float(inlraw.get("llm_timeout_s", 10.0)),
        llm_temperature=float(inlraw.get("llm_temperature", 0.2)),
        confidentiality_strict=bool(inlraw.get("confidentiality_strict", False)),
    )

    # -------------------------
    # Phase B: additive overlays (BehaveAgent / Treasury / Spread / Consensus / Governance)
    # -------------------------
    brow = eraw.get("behaveagent") or {}
    behaveagent = BehaveAgentConfig(
        enabled=bool(brow.get("enabled", True)),
        unknown_regime_fallback=str(brow.get("unknown_regime_fallback", "conservative")),
        exploration_capital_fraction=float(brow.get("exploration_capital_fraction", 0.05)),
        transparency_min_score=float(brow.get("transparency_min_score", 0.60)),
        reasoning_log_dir=str(brow.get("reasoning_log_dir", "data/behaveagent")),
        enable_similarity_clustering=bool(brow.get("enable_similarity_clustering", True)),
    )

    trow = eraw.get("treasury") or {}
    grow = trow.get("goal") or {}
    goal = ProfitGoal(
        target_return_percentage=float(grow.get("target_return_percentage", 0.0)),
        time_horizon_seconds=int(grow.get("time_horizon_seconds", 7 * 24 * 3600)),
        risk_tolerance=str(grow.get("risk_tolerance", "conservative")),
        max_drawdown_pct=float(grow.get("max_drawdown_pct", 10.0)),
        capital_commitment_pct=float(grow.get("capital_commitment_pct", 0.0)),
        priority_weight=float(grow.get("priority_weight", 1.0)),
    )
    treasury = TreasuryConfig(
        enabled=bool(trow.get("enabled", False)),
        goal=goal,
        liquidity_min_buffer_pct=float(trow.get("liquidity_min_buffer_pct", 25.0)),
        enable_yield_deployment=bool(trow.get("enable_yield_deployment", False)),
        aggressiveness_max_borrow_mult=float(trow.get("aggressiveness_max_borrow_mult", 2.0)),
        max_aggressiveness_without_approval=str(
            trow.get("max_aggressiveness_without_approval", "HIGH") or "HIGH"
        ),
        allow_maximum=bool(trow.get("allow_maximum", False)),
        meta=dict(trow.get("meta") or {}),
    )

    srow = eraw.get("spread") or {}
    spread = None
    if SpreadEngineConfig is not None:
        spread = SpreadEngineConfig(
            enabled=bool(srow.get("enabled", False)),
            min_alpha=float(srow.get("min_alpha", 0.10)),
            default_volume_usd=float(srow.get("default_volume_usd", 10_000.0)),
        )

    crow = eraw.get("consensus") or {}
    consensus = None
    if ConsensusConfig is not None:
        consensus = ConsensusConfig(
            enabled=bool(crow.get("enabled", True)),
            base_threshold=float(crow.get("base_threshold", 0.05)),
            stress_threshold_mult=float(crow.get("stress_threshold_mult", 1.3)),
            conflict_penalty=float(crow.get("conflict_penalty", 0.25)),
            enforce_on_auto=bool(crow.get("enforce_on_auto", True)),
            enforce_on_manual=bool(crow.get("enforce_on_manual", True)),
        )

    graw2 = eraw.get("governance") or {}
    governance = GovernanceConfig(
        enabled=bool(graw2.get("enabled", True)),
        enforce_on_auto=bool(graw2.get("enforce_on_auto", True)),
        enforce_on_manual=bool(graw2.get("enforce_on_manual", True)),
        admin_key_env=str(graw2.get("admin_key_env", "VICTOR_ADMIN_KEY")),
        require_human_for_tier5=bool(graw2.get("require_human_for_tier5", True)),
        require_human_for_maximum_aggressiveness=bool(
            graw2.get("require_human_for_maximum_aggressiveness", True)
        ),
        z_score_limit=float(graw2.get("z_score_limit", 6.0)),
        anomaly_score_limit=float(graw2.get("anomaly_score_limit", 0.85)),
        deterministic_ids=bool(graw2.get("deterministic_ids", True)),
    )

    arow = eraw.get("analytics") or {}
    analytics = QuickSightAnalyticsConfig(
        enabled=bool(arow.get("enabled", False)),
        mode=str(arow.get("mode", "observe")),
        tick_seconds=float(arow.get("tick_seconds", 10.0)),
        export_dir=str(arow.get("export_dir", "backend/data/analytics")),
        export_format=str(arow.get("export_format", "jsonl")),
        export_on_tick=bool(arow.get("export_on_tick", False)),
        max_rows_per_dataset=int(arow.get("max_rows_per_dataset", 5000)),
        datasets=list(arow.get("datasets") or QuickSightAnalyticsConfig().datasets),
        include_recent_trades=bool(arow.get("include_recent_trades", True)),
        rbac=RBACConfig(
            enabled=bool((arow.get("rbac") or {}).get("enabled", False)),
            role_tokens=dict((arow.get("rbac") or {}).get("role_tokens") or {}),
            default_role=str((arow.get("rbac") or {}).get("default_role", "EXECUTIVE_VIEW")),
        ),
        automation=ReportAutomationConfig(
            enabled=bool((arow.get("automation") or {}).get("enabled", True)),
            drawdown_threshold=float(
                (arow.get("automation") or {}).get("drawdown_threshold", 0.70)
            ),
            aggressiveness_escalation_level=str(
                (arow.get("automation") or {}).get("aggressiveness_escalation_level", "HIGH")
            ),
            threat_monitor_breach=float(
                (arow.get("automation") or {}).get("threat_monitor_breach", 0.85)
            ),
            epoch_review_seconds=int(
                (arow.get("automation") or {}).get("epoch_review_seconds", 3600)
            ),
        ),
    )

    execution = ExecutionConfig(
        auto_reinvest_enabled=bool(eraw.get("auto_reinvest_enabled", False)),
        reinvest_rate=int(eraw.get("reinvest_rate", 0)),
        base_borrow_amount=str(eraw.get("base_borrow_amount", "0")),
        # Kelly sizing is disabled by default until explicitly enabled.
        kelly_enabled=bool(eraw.get("kelly_enabled", False)),
        kelly_window=int(eraw.get("kelly_window", 50)),
        kelly_min_history=int(eraw.get("kelly_min_history", 20)),
        kelly_cap_fraction=float(eraw.get("kelly_cap_fraction", 0.75)),
        kelly_min_fraction=float(eraw.get("kelly_min_fraction", 0.05)),
        volatility_downscale=float(eraw.get("volatility_downscale", 0.35)),
        dry_run=bool(eraw.get("dry_run", True)),
        auto_trading=bool(eraw.get("auto_trading", False)),
        send_mode=str(eraw.get("send_mode", "public")),
        gas_mode=str(eraw.get("gas_mode", "standard")),
        gas_limit=int(eraw.get("gas_limit", 550000)),
        max_submit_per_block=int(eraw.get("max_submit_per_block", 1)),
        deadline_seconds=int(eraw.get("deadline_seconds", 30)),
        redact_routes_when_private=bool(eraw.get("redact_routes_when_private", True)),
        private_key_env=str(eraw.get("private_key_env", "VICTOR_PRIVATE_KEY")),
        from_address=str(eraw.get("from_address", "")),
        executor_address=str(eraw.get("executor_address", "")),
        profit_to=str(eraw.get("profit_to", "")),
        withdraw_mode=str(eraw.get("withdraw_mode") or wraw.get("mode", "txdata")),
        withdraw_allowlist=_as_list(
            eraw.get("withdraw_allowlist")
            or wraw.get("allowlist")
            or wraw.get("allowed_destinations")
            or []
        ),
        withdraw_tokens=_as_list(eraw.get("withdraw_tokens") or wraw.get("tokens") or []),
        flash_provider=str(eraw.get("flash_provider", "aave")),
        flashloan_fee_bps=int(eraw.get("flashloan_fee_bps", 9)),
        gas_presets=gas_presets,
        brain_mode=str(eraw.get("brain_mode", "off")),
        min_p_success=float(eraw.get("min_p_success", 0.70)),
        trade_cooldown_blocks=int(eraw.get("trade_cooldown_blocks", 1)),
        max_pending_txs=int(eraw.get("max_pending_txs", 1)),
        daily_gas_budget_wei=str(eraw.get("daily_gas_budget_wei", "0")),
        usd_accounting_enabled=bool(eraw.get("usd_accounting_enabled", False)),
        usd_stable_preference=str(eraw.get("usd_stable_preference", "usdc")),
        enforce_executor_version=bool(eraw.get("enforce_executor_version", False)),
        expected_executor_abi_version=int(eraw.get("expected_executor_abi_version", 2)),
        rft=RFTConfig(
            enabled=bool(rftraw.get("enabled", False)),
            episode_export_enabled=bool(rftraw.get("episode_export_enabled", False)),
            snapshot_top_k=int(rftraw.get("snapshot_top_k", 20)),
            enable_reward_trace_export=bool(rftraw.get("enable_reward_trace_export", True)),
            grader_weights=(
                {str(k): int(v) for k, v in dict(rftraw.get("grader_weights") or {}).items()}
                if dict(rftraw.get("grader_weights") or {})
                else RFTConfig().grader_weights
            ),
        ),
        arbitrage=arbitrage,
        mev=mev,
        meta=meta,
        superstructure=superstructure,
        fioa=fioa,
        llm_inl=llm_inl,
        behaveagent=behaveagent,
        analytics=analytics,
        treasury=treasury,
        spread=spread or SpreadEngineConfig() if SpreadEngineConfig is not None else None,
        consensus=consensus or ConsensusConfig() if ConsensusConfig is not None else None,
        governance=governance,
    )
    cfg = AppConfig(chain=chain, safety=safety, flags=flags, execution=execution)
    # Helpful for diagnostics / admin endpoints / optional integrations.
    try:
        setattr(cfg, "_source_path", str(p))
    except (AttributeError, TypeError, ValueError):
        pass
    return cfg
