from __future__ import annotations

import os
from typing import Any

from ..agents import AgentAttributionStore, AgentWeightingGovernor
from ..alpha_marketplace.submissions import AlphaMarketplaceStore
from ..command_center_overlay import CommandCenterOverlay
from ..event_bus.publishers import InMemoryEventBus
from ..fund_os.master_orchestrator import FundMasterOrchestrator
from ..fund_os.profit_doctrine import default_profit_doctrine
from ..fund_os.staged_rollout import StagedRolloutManager
from ..governance.audit_events import GovernanceAuditLog
from ..internal_prime.allocator import InternalPrimeAllocator
from ..pathing import migrate_legacy_data_roots
from ..persistence.repositories.auto_trade_recovery_repository import AutoTradeRecoveryRepository
from ..persistence.repositories.capital_recovery_repository import CapitalRecoveryRepository
from ..persistence.repositories.capital_event_repository import CapitalEventRepository
from ..persistence.repositories.ledger_repository import LedgerRepository
from ..research_pipeline.candidates import CandidateStore
from ..rl_training.policy_registry import PolicyRegistry
from ..runtime_subsystems import ReplayBundleStore
from ..strategies import FamilyScorecardStore
from ..strategies.covariance import FamilyCovarianceStore
from ..strategies.lifecycle_history import StrategyLifecycleMemory
from ..treasury.ledger import TreasuryLedger
from .admission_service import AdmissionService
from .agent_service import AgentService
from .analytics_service import AnalyticsService
from .auxiliary_state_service import AuxiliaryStateService
from .capital_explanation_service import CapitalExplanationService
from .capital_truth_service import CapitalTruthService
from .canonical_capital_write_service import CanonicalCapitalWriteService
from .cio_service import CIOService
from .decision_service import DecisionService
from .engine_service import EngineService
from .execution_service import ExecutionService
from .family_hardening_service import FamilyHardeningService
from .fund_service import FundService
from .launch_service import LaunchService
from .lifecycle_service import LifecycleService
from .operator_summary_service import OperatorSummaryService
from .opportunity_service import OpportunityService
from .receipt_service import ReceiptService
from .replay_service import ReplayService
from .runtime_control_service import RuntimeControlService
from .state_service import StateService
from .state_summary_service import StateSummaryService
from .treasury_service import TreasuryService
from .wealth_goal_service import WealthGoalService
from .capital_admission_service import CapitalAdmissionService
from .withdraw_all_service import WithdrawAllService

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def initialize_runtime_institutional_stack(runtime: Any, cfg: Any, data_dir: str) -> None:
    """Initialize constructor-time institutional/control-plane state on a runtime.

    This is intentionally non-hot-path constructor wiring. It preserves the
    existing RuntimeBundle attribute contract while reducing constructor
    concentration in runtime_legacy.py.
    """

    try:
        runtime._cc = CommandCenterOverlay(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._cc = None

    try:
        runtime._replay = ReplayBundleStore(
            data_dir=data_dir,
            chain=cfg.chain.name,
            chain_id=int(getattr(cfg.chain, "chain_id", 0) or 0),
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._replay = None

    runtime._opportunity_service = OpportunityService()
    runtime._decision_service = DecisionService()
    runtime._admission_service = AdmissionService()
    runtime._receipt_service = ReceiptService()
    runtime._runtime_control_service = RuntimeControlService()
    runtime._capital_explanation_service = CapitalExplanationService()
    runtime._agent_service = AgentService()
    runtime._treasury_service = TreasuryService()
    runtime._analytics_service = AnalyticsService()
    runtime._execution_service = ExecutionService()
    runtime._wealth_goal_service = WealthGoalService(data_dir=data_dir, chain=cfg.chain.name)
    runtime._replay_service = ReplayService()
    runtime._state_summary_service = StateSummaryService()
    runtime._auxiliary_state_service = AuxiliaryStateService()
    runtime._operator_summary_service = OperatorSummaryService(
        state_summary=runtime._state_summary_service
    )
    try:
        runtime._data_root_migration = migrate_legacy_data_roots()
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._data_root_migration = {}
    runtime._lifecycle_service = LifecycleService()
    runtime._state_service = StateService()
    runtime._engine_service = EngineService(
        capture_engine=getattr(runtime, "_capture_engine", None),
        telemetry_service=getattr(runtime, "_telemetry_service", None),
    )
    runtime._fund_service = FundService()
    runtime._cio_service = CIOService()
    runtime._launch_service = LaunchService()
    runtime._family_hardening_service = FamilyHardeningService()
    runtime._capital_truth_service = CapitalTruthService()
    runtime._capital_write_service = CanonicalCapitalWriteService()
    runtime._withdraw_all_service = WithdrawAllService(data_dir=data_dir, chain=cfg.chain.name)
    runtime._fund_master = FundMasterOrchestrator()
    runtime._profit_doctrine = default_profit_doctrine()
    runtime._event_bus = InMemoryEventBus()
    runtime._capital_event_repo = CapitalEventRepository(runtime._db, chain=cfg.chain.name)
    runtime._ledger = TreasuryLedger(data_dir=data_dir, chain=cfg.chain.name)
    runtime._ledger_repo = LedgerRepository(
        runtime._db, capital_event_repo=runtime._capital_event_repo, chain=cfg.chain.name
    )
    runtime._capital_recovery_repo = CapitalRecoveryRepository(runtime._db, chain=cfg.chain.name)
    runtime._auto_trade_recovery_repo = AutoTradeRecoveryRepository(
        runtime._db, chain=cfg.chain.name
    )
    runtime._internal_prime = InternalPrimeAllocator(
        data_dir=data_dir,
        chain=cfg.chain.name,
        db=runtime._db,
        capital_event_repo=runtime._capital_event_repo,
        capital_write_service=runtime._capital_write_service,
    )
    runtime._internal_prime_state_repo = getattr(runtime._internal_prime, "_state_repo", None)
    runtime._rl_registry = PolicyRegistry(data_dir=data_dir, chain=cfg.chain.name)
    runtime._engine_last = {
        "items": [],
        "capabilities": {},
        "summary": {"engines": []},
    }

    try:
        runtime._research_candidates = CandidateStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._research_candidates = None
    try:
        runtime._launch_rollout = StagedRolloutManager(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._launch_rollout = None
    try:
        runtime._alpha_marketplace = AlphaMarketplaceStore(
            data_dir=data_dir,
            chain=cfg.chain.name,
            enabled=bool(
                (getattr(cfg.execution, "meta", {}) or {}).get("enable_alpha_marketplace", False)
            ),
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._alpha_marketplace = None
    try:
        runtime._fund_audit = GovernanceAuditLog(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._fund_audit = None
    try:
        runtime._agent_weighting = AgentWeightingGovernor(
            path=os.path.join(data_dir, "agents", f"weights_{cfg.chain.name}.json")
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._agent_weighting = None
    try:
        runtime._agent_attribution = AgentAttributionStore(
            path=os.path.join(data_dir, "agents", f"attribution_{cfg.chain.name}.json"),
            chain=cfg.chain.name,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._agent_attribution = None
    try:
        runtime._family_scorecards = FamilyScorecardStore(
            path=os.path.join(data_dir, "strategies", f"family_scorecards_{cfg.chain.name}.json"),
            chain=cfg.chain.name,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._family_scorecards = None
    try:
        runtime._family_covariance = FamilyCovarianceStore(
            path=os.path.join(data_dir, "strategies", f"family_covariance_{cfg.chain.name}.json")
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._family_covariance = None
    try:
        runtime._lifecycle_memory = StrategyLifecycleMemory(
            path=os.path.join(data_dir, "strategies", f"lifecycle_{cfg.chain.name}.json"),
            chain=cfg.chain.name,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._lifecycle_memory = None
