from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_institutional_init as mod


class _EngineService:
    def __init__(self, capture_engine=None, telemetry_service=None):
        self.capture_engine = capture_engine
        self.telemetry_service = telemetry_service


class _OperatorSummaryService:
    def __init__(self, state_summary=None):
        self.state_summary = state_summary


class _AlphaMarketplaceStore:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _AttributionStore:
    def __init__(self, path=None, chain=None):
        self.path = path
        self.chain = chain


class _LifecycleMemory:
    def __init__(self, path=None, chain=None):
        self.path = path
        self.chain = chain


class _FamilyCovarianceStore:
    def __init__(self, path=None):
        self.path = path


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(name="ethereum", chain_id=1),
        execution=SimpleNamespace(meta={"enable_alpha_marketplace": True}),
    )


def test_runtime_institutional_init_wires_service_and_control_plane_stack(monkeypatch, tmp_path):
    created = {}

    monkeypatch.setattr(mod, "CommandCenterOverlay", lambda **kwargs: created.setdefault("cc", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "ReplayBundleStore", lambda **kwargs: created.setdefault("replay", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "OpportunityService", lambda: created.setdefault("opportunity", object()))
    monkeypatch.setattr(mod, "DecisionService", lambda: created.setdefault("decision", object()))
    monkeypatch.setattr(mod, "AdmissionService", lambda: created.setdefault("admission", object()))
    monkeypatch.setattr(mod, "ReceiptService", lambda: created.setdefault("receipt", object()))
    monkeypatch.setattr(mod, "RuntimeControlService", lambda: created.setdefault("control", object()))
    monkeypatch.setattr(mod, "CapitalExplanationService", lambda: created.setdefault("capital_explanation", object()))
    monkeypatch.setattr(mod, "AgentService", lambda: created.setdefault("agent", object()))
    monkeypatch.setattr(mod, "TreasuryService", lambda: created.setdefault("treasury_service", object()))
    monkeypatch.setattr(mod, "AnalyticsService", lambda: created.setdefault("analytics", object()))
    monkeypatch.setattr(mod, "ExecutionService", lambda: created.setdefault("execution", object()))
    monkeypatch.setattr(mod, "WealthGoalService", lambda **kwargs: created.setdefault("wealth_goal", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "ReplayService", lambda: created.setdefault("replay_service", object()))
    monkeypatch.setattr(mod, "StateSummaryService", lambda: created.setdefault("state_summary", object()))
    monkeypatch.setattr(mod, "AuxiliaryStateService", lambda: created.setdefault("aux", object()))
    monkeypatch.setattr(mod, "OperatorSummaryService", _OperatorSummaryService)
    monkeypatch.setattr(mod, "migrate_legacy_data_roots", lambda: {"migrated": True})
    monkeypatch.setattr(mod, "LifecycleService", lambda: created.setdefault("lifecycle_service", object()))
    monkeypatch.setattr(mod, "StateService", lambda: created.setdefault("state_service", object()))
    monkeypatch.setattr(mod, "EngineService", _EngineService)
    monkeypatch.setattr(mod, "FundService", lambda: created.setdefault("fund_service", object()))
    monkeypatch.setattr(mod, "CIOService", lambda: created.setdefault("cio_service", object()))
    monkeypatch.setattr(mod, "LaunchService", lambda: created.setdefault("launch_service", object()))
    monkeypatch.setattr(mod, "FamilyHardeningService", lambda: created.setdefault("family_hardening", object()))
    monkeypatch.setattr(mod, "CapitalTruthService", lambda: created.setdefault("capital_truth", object()))
    monkeypatch.setattr(mod, "WithdrawAllService", lambda **kwargs: created.setdefault("withdraw_all", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "FundMasterOrchestrator", lambda: created.setdefault("fund_master", object()))
    monkeypatch.setattr(mod, "default_profit_doctrine", lambda: created.setdefault("profit_doctrine", object()))
    monkeypatch.setattr(mod, "InMemoryEventBus", lambda: created.setdefault("event_bus", object()))
    monkeypatch.setattr(mod, "TreasuryLedger", lambda **kwargs: created.setdefault("ledger", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "LedgerRepository", lambda db: created.setdefault("ledger_repo", SimpleNamespace(db=db)))
    monkeypatch.setattr(mod, "InternalPrimeAllocator", lambda **kwargs: created.setdefault("internal_prime", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "PolicyRegistry", lambda **kwargs: created.setdefault("policy", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "CandidateStore", lambda **kwargs: created.setdefault("candidates", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "StagedRolloutManager", lambda **kwargs: created.setdefault("rollout", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "AlphaMarketplaceStore", _AlphaMarketplaceStore)
    monkeypatch.setattr(mod, "GovernanceAuditLog", lambda **kwargs: created.setdefault("fund_audit", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "AgentWeightingGovernor", lambda path=None: created.setdefault("agent_weighting", SimpleNamespace(path=path)))
    monkeypatch.setattr(mod, "AgentAttributionStore", _AttributionStore)
    monkeypatch.setattr(mod, "FamilyScorecardStore", lambda path=None, chain=None: created.setdefault("family_scorecards", SimpleNamespace(path=path, chain=chain)))
    monkeypatch.setattr(mod, "FamilyCovarianceStore", _FamilyCovarianceStore)
    monkeypatch.setattr(mod, "StrategyLifecycleMemory", _LifecycleMemory)

    runtime = SimpleNamespace(_db="db", _capture_engine="capture", _telemetry_service="telemetry")
    mod.initialize_runtime_institutional_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._cc is created["cc"]
    assert runtime._replay is created["replay"]
    assert runtime._operator_summary_service.state_summary is created["state_summary"]
    assert runtime._engine_service.capture_engine == "capture"
    assert runtime._engine_service.telemetry_service == "telemetry"
    assert runtime._data_root_migration == {"migrated": True}
    assert runtime._ledger is created["ledger"]
    assert runtime._ledger_repo.db == "db"
    assert runtime._internal_prime is created["internal_prime"]
    assert runtime._research_candidates is created["candidates"]
    assert runtime._launch_rollout is created["rollout"]
    assert runtime._alpha_marketplace.kwargs["enabled"] is True
    assert runtime._engine_last == {"items": [], "capabilities": {}, "summary": {"engines": []}}


def test_runtime_institutional_init_contains_optional_failures_but_preserves_core_services(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "CommandCenterOverlay", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "ReplayBundleStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "OpportunityService", lambda: object())
    monkeypatch.setattr(mod, "DecisionService", lambda: object())
    monkeypatch.setattr(mod, "AdmissionService", lambda: object())
    monkeypatch.setattr(mod, "ReceiptService", lambda: object())
    monkeypatch.setattr(mod, "RuntimeControlService", lambda: object())
    monkeypatch.setattr(mod, "CapitalExplanationService", lambda: object())
    monkeypatch.setattr(mod, "AgentService", lambda: object())
    monkeypatch.setattr(mod, "TreasuryService", lambda: object())
    monkeypatch.setattr(mod, "AnalyticsService", lambda: object())
    monkeypatch.setattr(mod, "ExecutionService", lambda: object())
    monkeypatch.setattr(mod, "WealthGoalService", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "ReplayService", lambda: object())
    monkeypatch.setattr(mod, "StateSummaryService", lambda: object())
    monkeypatch.setattr(mod, "AuxiliaryStateService", lambda: object())
    monkeypatch.setattr(mod, "OperatorSummaryService", _OperatorSummaryService)
    monkeypatch.setattr(mod, "migrate_legacy_data_roots", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "LifecycleService", lambda: object())
    monkeypatch.setattr(mod, "StateService", lambda: object())
    monkeypatch.setattr(mod, "EngineService", _EngineService)
    monkeypatch.setattr(mod, "FundService", lambda: object())
    monkeypatch.setattr(mod, "CIOService", lambda: object())
    monkeypatch.setattr(mod, "LaunchService", lambda: object())
    monkeypatch.setattr(mod, "FamilyHardeningService", lambda: object())
    monkeypatch.setattr(mod, "CapitalTruthService", lambda: object())
    monkeypatch.setattr(mod, "WithdrawAllService", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "FundMasterOrchestrator", lambda: object())
    monkeypatch.setattr(mod, "default_profit_doctrine", lambda: object())
    monkeypatch.setattr(mod, "InMemoryEventBus", lambda: object())
    monkeypatch.setattr(mod, "TreasuryLedger", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "LedgerRepository", lambda db: SimpleNamespace(db=db))
    monkeypatch.setattr(mod, "InternalPrimeAllocator", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "PolicyRegistry", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "CandidateStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "StagedRolloutManager", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "AlphaMarketplaceStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "GovernanceAuditLog", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "AgentWeightingGovernor", lambda path=None: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "AgentAttributionStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "FamilyScorecardStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "FamilyCovarianceStore", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "StrategyLifecycleMemory", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    runtime = SimpleNamespace(_db="db", _capture_engine=None, _telemetry_service=None)
    mod.initialize_runtime_institutional_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._cc is None
    assert runtime._replay is None
    assert runtime._data_root_migration == {}
    assert runtime._operator_summary_service.state_summary is runtime._state_summary_service
    assert runtime._research_candidates is None
    assert runtime._launch_rollout is None
    assert runtime._alpha_marketplace is None
    assert runtime._fund_audit is None
    assert runtime._agent_weighting is None
    assert runtime._agent_attribution is None
    assert runtime._family_scorecards is None
    assert runtime._family_covariance is None
    assert runtime._lifecycle_memory is None
    assert runtime._ledger_repo.db == "db"
