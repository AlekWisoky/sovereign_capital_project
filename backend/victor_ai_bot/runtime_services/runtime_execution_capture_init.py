from __future__ import annotations

import os
from typing import Any

from ..execution_capture import ExecutionDecisionEngine, ExecutionTelemetryStore
from ..execution_capture.calibration import EmpiricalCalibrationStore
from ..execution_capture.edge_model import ExecutionLearningEngine
from ..execution_capture.endpoint_quality import EndpointQualityStore
from ..execution_capture.endpoint_universe import EndpointUniverse
from ..execution_capture.no_trade_analytics import NoTradeAnalytics
from ..execution_capture.path_diversity import PathDiversityMemory
from ..execution_capture.risk_memory import ExecutionRiskMemory
from ..execution_capture.route_quality_store import RouteQualityStore
from ..execution_capture.smart_order_router import VenueScorecardStore
from ..execution_capture.template_cache import RouteTemplateCache
from ..execution_capture.venue_profiles import VenueReliabilityStore
from ..governance.kill_switch import KillSwitchStore
from ..risk_engine.drawdown_state import DrawdownStateStore
from ..rpc_preferences import RpcPreferencesStore
from ..telemetry.store import TelemetryStore
from .telemetry_service import TelemetryService

_SAFE_RUNTIME_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


def initialize_execution_capture_stack(runtime: Any, cfg: Any, data_dir: str) -> None:
    """Initialize execution-capture and telemetry support on an existing RuntimeBundle.

    This is intentionally non-hot-path constructor logic. It preserves the
    existing RuntimeBundle attribute contract while reducing constructor
    concentration in runtime_legacy.py.
    """

    try:
        runtime._capture_telemetry = ExecutionTelemetryStore(
            data_dir=data_dir, chain=cfg.chain.name
        )
        runtime._capture_templates = RouteTemplateCache(data_dir=data_dir, chain=cfg.chain.name)
        runtime._capture_engine = ExecutionDecisionEngine(
            telemetry=runtime._capture_telemetry,
            template_cache=runtime._capture_templates,
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._capture_telemetry = None
        runtime._capture_templates = None
        runtime._capture_engine = None

    runtime._market_regime = {
        "regime": "balanced",
        "confidence": 0.60,
        "features": {},
        "enabled_strategies": ["flashloan_atomic"],
    }

    try:
        runtime._execution_calibration = EmpiricalCalibrationStore(
            data_dir=data_dir, chain=cfg.chain.name
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._execution_calibration = None
    try:
        runtime._venue_profiles = VenueReliabilityStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._venue_profiles = None
    try:
        runtime._risk_memory = ExecutionRiskMemory(
            os.path.join(data_dir, "execution_capture", f"risk_memory_{cfg.chain.name}.json")
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._risk_memory = None
    try:
        runtime._path_diversity = PathDiversityMemory(
            os.path.join(data_dir, "execution_capture", f"path_diversity_{cfg.chain.name}.json")
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._path_diversity = None
    try:
        runtime._edge_learning = ExecutionLearningEngine(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._edge_learning = None
    try:
        runtime._endpoint_quality = EndpointQualityStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._endpoint_quality = None
    try:
        runtime._endpoint_universe = EndpointUniverse(
            cfg=cfg, rpc_manager=runtime.rpc_manager, rpc_preferences=None
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._endpoint_universe = None
    try:
        runtime._venue_scorecards = VenueScorecardStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._venue_scorecards = None
    try:
        runtime._route_quality = RouteQualityStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._route_quality = None
    try:
        runtime._drawdown_state = DrawdownStateStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._drawdown_state = None
    try:
        runtime._kill_switch = KillSwitchStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._kill_switch = None
    try:
        runtime._rpc_preferences = RpcPreferencesStore(data_dir=data_dir, chain=cfg.chain.name)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._rpc_preferences = None
    try:
        if getattr(runtime, "_endpoint_universe", None) is not None:
            runtime._endpoint_universe.rpc_preferences = runtime._rpc_preferences
    except _SAFE_RUNTIME_EXCEPTIONS:
        pass
    try:
        if getattr(runtime, "_capture_engine", None) is not None:
            runtime._capture_engine.calibration_store = runtime._execution_calibration
            runtime._capture_engine.venue_profiles = runtime._venue_profiles
            runtime._capture_engine.risk_memory = runtime._risk_memory
            runtime._capture_engine.path_diversity = runtime._path_diversity
            runtime._capture_engine.edge_learning = runtime._edge_learning
            runtime._capture_engine.endpoint_quality = runtime._endpoint_quality
            runtime._capture_engine.endpoint_universe = runtime._endpoint_universe
            runtime._capture_engine.venue_scorecards = runtime._venue_scorecards
            runtime._capture_engine.route_quality = runtime._route_quality
    except _SAFE_RUNTIME_EXCEPTIONS:
        pass
    try:
        runtime._no_trade_analytics = NoTradeAnalytics(
            os.path.join(data_dir, "execution_capture", f"no_trade_{cfg.chain.name}.json")
        )
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._no_trade_analytics = None
    try:
        runtime._telemetry_store = TelemetryStore(data_dir=data_dir, chain=cfg.chain.name)
        runtime._telemetry_service = TelemetryService(store=runtime._telemetry_store)
    except _SAFE_RUNTIME_EXCEPTIONS:
        runtime._telemetry_store = None
        runtime._telemetry_service = None
