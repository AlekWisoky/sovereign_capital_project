from __future__ import annotations

import os
from typing import Any

from ..analytics import BlockspaceIntel, QuickSightAnalyticsRuntime
from ..aqe.agents.hub import AgentHub
from ..aqe.coordination import SharedFeatureBus, AgentConsensusEngine, AgentPerformanceTracker
from ..aqe.execution import ExecutionOrchestrator
from ..aqe.spread import SpreadEngine
from ..bankroll import BankrollManager, BankrollConfig
from ..behaveagent import BehaveAgentRuntime
from ..efficiency import EfficiencyTracker
from ..governance import GovernanceRuntime
from ..pnl import PnLStore
from ..persistence.repositories.bankroll_repository import BankrollEventRepository
from ..treasury import TreasuryRuntime

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def initialize_execution_support_stack(runtime: Any, cfg: Any, data_dir: str) -> None:
    """Initialize execution-support overlays on an existing RuntimeBundle.

    This is intentionally non-hot-path constructor logic. It preserves the
    existing RuntimeBundle attribute contract while reducing constructor
    concentration in runtime_legacy.py.
    """

    runtime._pnl = PnLStore(os.path.join(data_dir, f"pnl_{cfg.chain.name}.sqlite"))

    runtime._executor_version_checked = False
    runtime._executor_abi_version = None
    runtime._executor_impl_version = None
    runtime._executor_version_error = None

    max_borrow = int(cfg.safety.max_borrow_amount or "0")
    base_override = int(getattr(cfg.execution, "base_borrow_amount", "0") or "0")
    runtime._bankroll_history_repo = BankrollEventRepository(runtime._db, chain=cfg.chain.name)
    runtime._bankroll = BankrollManager(
        BankrollConfig(
            auto_reinvest_enabled=bool(getattr(cfg.execution, "auto_reinvest_enabled", False)),
            reinvest_rate_pct=int(getattr(cfg.execution, "reinvest_rate", 0)),
            max_borrow_amount_wei=max_borrow,
            base_borrow_amount_wei=base_override,
            kelly_enabled=bool(getattr(cfg.execution, "kelly_enabled", False)),
            kelly_window=int(getattr(cfg.execution, "kelly_window", 50) or 50),
            kelly_min_history=int(getattr(cfg.execution, "kelly_min_history", 20) or 20),
            kelly_cap_fraction=float(getattr(cfg.execution, "kelly_cap_fraction", 0.75) or 0.75),
            kelly_min_fraction=float(getattr(cfg.execution, "kelly_min_fraction", 0.05) or 0.05),
            volatility_downscale=float(
                getattr(cfg.execution, "volatility_downscale", 0.35) or 0.35
            ),
        ),
        state_path=os.path.join(data_dir, "state", f"bankroll_{cfg.chain.name}.json"),
        history_repo=runtime._bankroll_history_repo,
        capital_event_repo=getattr(runtime, "_capital_event_repo", None),
    )
    runtime._eff = EfficiencyTracker(window=50)

    runtime._blockspace = BlockspaceIntel()

    try:
        runtime._quicksight = QuickSightAnalyticsRuntime(
            cfg=getattr(cfg.execution, "analytics", None), pnl_store=runtime._pnl
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._quicksight = None

    runtime._feature_bus = SharedFeatureBus()

    try:
        runtime._spread_engine = SpreadEngine(cfg=getattr(cfg.execution, "spread", None))
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._spread_engine = SpreadEngine(cfg=None)
    runtime._spread_opps = []
    runtime._spread_last = {}

    try:
        perf_path = os.path.join(data_dir, "rl", f"agent_perf_{cfg.chain.name}.json")
        runtime._agent_perf = AgentPerformanceTracker(path=perf_path)
        runtime._consensus = AgentConsensusEngine(
            cfg=getattr(cfg.execution, "consensus", None), tracker=runtime._agent_perf
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._agent_perf = None
        runtime._consensus = AgentConsensusEngine(cfg=None, tracker=None)

    runtime._consensus_last = {}

    try:
        runtime._behave = BehaveAgentRuntime(
            cfg=getattr(cfg.execution, "behaveagent", None), data_dir=data_dir
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._behave = None

    try:
        runtime._treasury = TreasuryRuntime(
            cfg=getattr(cfg.execution, "treasury", None),
            data_dir=data_dir,
            db=runtime._db,
            chain=cfg.chain.name,
            capital_event_repo=getattr(runtime, "_capital_event_repo", None),
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._treasury = None

    try:
        runtime._gov = GovernanceRuntime(
            cfg=getattr(cfg.execution, "governance", None), data_dir=data_dir
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._gov = None

    try:
        runtime._orchestrator = ExecutionOrchestrator(
            allow_live=(not bool(getattr(cfg.execution, "dry_run", True)))
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._orchestrator = None

    try:
        runtime._agent_hub = AgentHub(data_dir=data_dir)
        runtime._agent_hub_last = {}
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._agent_hub = None
        runtime._agent_hub_last = {}
