from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_execution_support_init as mod


def _cfg():
    return SimpleNamespace(
        chain=SimpleNamespace(name="ethereum"),
        safety=SimpleNamespace(max_borrow_amount="123"),
        execution=SimpleNamespace(
            analytics=SimpleNamespace(enabled=True),
            spread=SimpleNamespace(enabled=True),
            consensus=SimpleNamespace(enabled=True),
            behaveagent=SimpleNamespace(enabled=True),
            treasury=SimpleNamespace(enabled=True),
            governance=SimpleNamespace(enabled=True),
            auto_reinvest_enabled=True,
            reinvest_rate=5,
            base_borrow_amount="11",
            kelly_enabled=True,
            kelly_window=50,
            kelly_min_history=20,
            kelly_cap_fraction=0.75,
            kelly_min_fraction=0.05,
            volatility_downscale=0.35,
            dry_run=True,
        ),
    )


def test_execution_support_init_wires_quicksight_and_consensus(monkeypatch, tmp_path):
    created = {}

    monkeypatch.setattr(mod, "PnLStore", lambda path: created.setdefault("pnl", SimpleNamespace(path=path)))
    monkeypatch.setattr(
        mod,
        "BankrollManager",
        lambda cfg, **kwargs: created.setdefault(
            "bankroll", SimpleNamespace(cfg=cfg, kwargs=kwargs)
        ),
    )
    monkeypatch.setattr(mod, "EfficiencyTracker", lambda window: created.setdefault("eff", SimpleNamespace(window=window)))
    monkeypatch.setattr(mod, "BlockspaceIntel", lambda: created.setdefault("blockspace", object()))
    monkeypatch.setattr(mod, "QuickSightAnalyticsRuntime", lambda **kwargs: created.setdefault("qs", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "SharedFeatureBus", lambda: created.setdefault("bus", object()))
    monkeypatch.setattr(mod, "SpreadEngine", lambda cfg=None: created.setdefault("spread", SimpleNamespace(cfg=cfg)))
    monkeypatch.setattr(mod, "AgentPerformanceTracker", lambda path: created.setdefault("perf", SimpleNamespace(path=path)))
    monkeypatch.setattr(mod, "AgentConsensusEngine", lambda **kwargs: created.setdefault("consensus", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "BehaveAgentRuntime", lambda **kwargs: created.setdefault("behave", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "TreasuryRuntime", lambda **kwargs: created.setdefault("treasury", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "GovernanceRuntime", lambda **kwargs: created.setdefault("gov", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "ExecutionOrchestrator", lambda **kwargs: created.setdefault("orch", SimpleNamespace(kwargs=kwargs)))
    monkeypatch.setattr(mod, "AgentHub", lambda **kwargs: created.setdefault("hub", SimpleNamespace(kwargs=kwargs)))

    runtime = SimpleNamespace()
    mod.initialize_execution_support_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._pnl is created["pnl"]
    assert runtime._quicksight is created["qs"]
    assert created["qs"].kwargs["pnl_store"] is created["pnl"]
    assert runtime._consensus is created["consensus"]
    assert created["consensus"].kwargs["tracker"] is created["perf"]
    assert runtime._agent_hub is created["hub"]
    assert runtime._agent_hub_last == {}
    assert runtime._spread_opps == []
    assert runtime._spread_last == {}
    assert runtime._executor_version_checked is False


def test_execution_support_init_degrades_locally_without_breaking_follow_on_state(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "PnLStore", lambda path: SimpleNamespace(path=path))
    monkeypatch.setattr(mod, "BankrollManager", lambda cfg, **kwargs: SimpleNamespace(cfg=cfg, kwargs=kwargs))
    monkeypatch.setattr(mod, "EfficiencyTracker", lambda window: SimpleNamespace(window=window))
    monkeypatch.setattr(mod, "BlockspaceIntel", lambda: object())
    monkeypatch.setattr(mod, "QuickSightAnalyticsRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "SharedFeatureBus", lambda: object())
    monkeypatch.setattr(mod, "SpreadEngine", lambda cfg=None: (_ for _ in ()).throw(RuntimeError("boom")) if cfg is not None else SimpleNamespace(cfg=None))
    monkeypatch.setattr(mod, "AgentPerformanceTracker", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "AgentConsensusEngine", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr(mod, "BehaveAgentRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "TreasuryRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "GovernanceRuntime", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "ExecutionOrchestrator", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(mod, "AgentHub", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    runtime = SimpleNamespace()
    mod.initialize_execution_support_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._quicksight is None
    assert runtime._spread_engine.cfg is None
    assert runtime._agent_perf is None
    assert runtime._consensus.kwargs["tracker"] is None
    assert runtime._behave is None
    assert runtime._treasury is None
    assert runtime._gov is None
    assert runtime._orchestrator is None
    assert runtime._agent_hub is None
    assert runtime._agent_hub_last == {}


def test_execution_support_init_defaults_kelly_disabled_when_config_omits_it(monkeypatch, tmp_path):
    created = {}

    monkeypatch.setattr(mod, "PnLStore", lambda path: SimpleNamespace(path=path))
    monkeypatch.setattr(
        mod,
        "BankrollManager",
        lambda cfg, **kwargs: created.setdefault(
            "bankroll", SimpleNamespace(cfg=cfg, kwargs=kwargs)
        ),
    )
    monkeypatch.setattr(mod, "EfficiencyTracker", lambda window: SimpleNamespace(window=window))
    monkeypatch.setattr(mod, "BlockspaceIntel", lambda: object())
    monkeypatch.setattr(mod, "QuickSightAnalyticsRuntime", lambda **kwargs: None)
    monkeypatch.setattr(mod, "SharedFeatureBus", lambda: object())
    monkeypatch.setattr(mod, "SpreadEngine", lambda cfg=None: SimpleNamespace(cfg=cfg))
    monkeypatch.setattr(mod, "AgentPerformanceTracker", lambda path: None)
    monkeypatch.setattr(mod, "AgentConsensusEngine", lambda **kwargs: None)
    monkeypatch.setattr(mod, "BehaveAgentRuntime", lambda **kwargs: None)
    monkeypatch.setattr(mod, "TreasuryRuntime", lambda **kwargs: None)
    monkeypatch.setattr(mod, "GovernanceRuntime", lambda **kwargs: None)
    monkeypatch.setattr(mod, "ExecutionOrchestrator", lambda **kwargs: None)
    monkeypatch.setattr(mod, "AgentHub", lambda **kwargs: None)

    cfg = _cfg()
    delattr(cfg.execution, "kelly_enabled")

    runtime = SimpleNamespace()
    mod.initialize_execution_support_stack(runtime, cfg, str(tmp_path))

    assert created["bankroll"].cfg.kelly_enabled is False
