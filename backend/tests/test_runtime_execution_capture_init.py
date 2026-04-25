from types import SimpleNamespace

from victor_ai_bot.runtime_services import runtime_execution_capture_init as mod


class _CaptureEngine:
    def __init__(self, telemetry=None, template_cache=None):
        self.telemetry = telemetry
        self.template_cache = template_cache


class _EndpointUniverse:
    def __init__(self, cfg=None, rpc_manager=None, rpc_preferences=None):
        self.cfg = cfg
        self.rpc_manager = rpc_manager
        self.rpc_preferences = rpc_preferences


def _cfg():
    return SimpleNamespace(chain=SimpleNamespace(name="ethereum"))


def test_execution_capture_init_wires_capture_engine_dependencies(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "ExecutionTelemetryStore", lambda **kwargs: "telemetry")
    monkeypatch.setattr(mod, "RouteTemplateCache", lambda **kwargs: "templates")
    monkeypatch.setattr(mod, "ExecutionDecisionEngine", _CaptureEngine)
    monkeypatch.setattr(mod, "EmpiricalCalibrationStore", lambda **kwargs: "calibration")
    monkeypatch.setattr(mod, "VenueReliabilityStore", lambda **kwargs: "venue_profiles")
    monkeypatch.setattr(mod, "ExecutionRiskMemory", lambda *args, **kwargs: "risk_memory")
    monkeypatch.setattr(mod, "PathDiversityMemory", lambda *args, **kwargs: "path_diversity")
    monkeypatch.setattr(mod, "ExecutionLearningEngine", lambda **kwargs: "edge_learning")
    monkeypatch.setattr(mod, "EndpointQualityStore", lambda **kwargs: "endpoint_quality")
    monkeypatch.setattr(mod, "EndpointUniverse", _EndpointUniverse)
    monkeypatch.setattr(mod, "VenueScorecardStore", lambda **kwargs: "venue_scorecards")
    monkeypatch.setattr(mod, "RouteQualityStore", lambda **kwargs: "route_quality")
    monkeypatch.setattr(mod, "DrawdownStateStore", lambda **kwargs: "drawdown_state")
    monkeypatch.setattr(mod, "KillSwitchStore", lambda **kwargs: "kill_switch")
    monkeypatch.setattr(mod, "RpcPreferencesStore", lambda **kwargs: "rpc_prefs")
    monkeypatch.setattr(mod, "NoTradeAnalytics", lambda *args, **kwargs: "no_trade")
    monkeypatch.setattr(mod, "TelemetryStore", lambda **kwargs: "telemetry_store")
    monkeypatch.setattr(mod, "TelemetryService", lambda store: ("telemetry_service", store))

    runtime = SimpleNamespace(rpc_manager="rpc")
    mod.initialize_execution_capture_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._capture_telemetry == "telemetry"
    assert runtime._capture_templates == "templates"
    assert runtime._capture_engine.telemetry == "telemetry"
    assert runtime._capture_engine.template_cache == "templates"
    assert runtime._capture_engine.calibration_store == "calibration"
    assert runtime._capture_engine.venue_profiles == "venue_profiles"
    assert runtime._capture_engine.risk_memory == "risk_memory"
    assert runtime._capture_engine.path_diversity == "path_diversity"
    assert runtime._capture_engine.edge_learning == "edge_learning"
    assert runtime._capture_engine.endpoint_quality == "endpoint_quality"
    assert runtime._capture_engine.endpoint_universe.rpc_preferences == "rpc_prefs"
    assert runtime._capture_engine.venue_scorecards == "venue_scorecards"
    assert runtime._capture_engine.route_quality == "route_quality"
    assert runtime._telemetry_service == ("telemetry_service", "telemetry_store")
    assert runtime._market_regime["regime"] == "balanced"


def test_execution_capture_init_degrades_capture_engine_but_keeps_follow_on_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(
        mod,
        "ExecutionTelemetryStore",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(mod, "EmpiricalCalibrationStore", lambda **kwargs: "calibration")
    monkeypatch.setattr(mod, "VenueReliabilityStore", lambda **kwargs: "venue_profiles")
    monkeypatch.setattr(mod, "ExecutionRiskMemory", lambda *args, **kwargs: "risk_memory")
    monkeypatch.setattr(mod, "PathDiversityMemory", lambda *args, **kwargs: "path_diversity")
    monkeypatch.setattr(mod, "ExecutionLearningEngine", lambda **kwargs: "edge_learning")
    monkeypatch.setattr(mod, "EndpointQualityStore", lambda **kwargs: "endpoint_quality")
    monkeypatch.setattr(mod, "EndpointUniverse", _EndpointUniverse)
    monkeypatch.setattr(mod, "VenueScorecardStore", lambda **kwargs: "venue_scorecards")
    monkeypatch.setattr(mod, "RouteQualityStore", lambda **kwargs: "route_quality")
    monkeypatch.setattr(mod, "DrawdownStateStore", lambda **kwargs: "drawdown_state")
    monkeypatch.setattr(mod, "KillSwitchStore", lambda **kwargs: "kill_switch")
    monkeypatch.setattr(mod, "RpcPreferencesStore", lambda **kwargs: "rpc_prefs")
    monkeypatch.setattr(mod, "NoTradeAnalytics", lambda *args, **kwargs: "no_trade")
    monkeypatch.setattr(mod, "TelemetryStore", lambda **kwargs: "telemetry_store")
    monkeypatch.setattr(mod, "TelemetryService", lambda store: ("telemetry_service", store))

    runtime = SimpleNamespace(rpc_manager="rpc")
    mod.initialize_execution_capture_stack(runtime, _cfg(), str(tmp_path))

    assert runtime._capture_telemetry is None
    assert runtime._capture_templates is None
    assert runtime._capture_engine is None
    assert runtime._execution_calibration == "calibration"
    assert runtime._telemetry_service == ("telemetry_service", "telemetry_store")
    assert runtime._market_regime["enabled_strategies"] == ["flashloan_atomic"]
