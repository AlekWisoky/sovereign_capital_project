from __future__ import annotations

import os
from typing import Any

_SAFE_EXCEPTIONS = (AttributeError, KeyError, TypeError, ValueError, RuntimeError, OSError)


class RuntimeControlService:
    """Centralize deterministic command-center/runtime posture helpers.

    These helpers sit off the execution hot path and keep the legacy runtime from
    re-implementing the same operator/control logic in multiple loops.
    """

    @staticmethod
    def latency_profiling_enabled(runtime: Any) -> bool:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        try:
            return bool(getattr(controls, "latency_profiling_enabled", True))
        except _SAFE_EXCEPTIONS:
            return True

    @staticmethod
    def rpc_batch_enabled(runtime: Any) -> bool:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        try:
            return bool(getattr(controls, "rpc_batch_enabled", False))
        except _SAFE_EXCEPTIONS:
            return False

    @staticmethod
    def apply_brain_mode_override(runtime: Any) -> None:
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is None:
            return
        try:
            brain_mode = str(getattr(controls, "brain_mode", "") or "").strip().lower()
        except _SAFE_EXCEPTIONS:
            brain_mode = ""
        if not brain_mode:
            return
        try:
            runtime._decision.set_brain_mode(brain_mode)
        except _SAFE_EXCEPTIONS:
            return

    def on_block_number_failure(self, runtime: Any) -> None:
        try:
            runtime.metrics.failed_ticks += 1
        except _SAFE_EXCEPTIONS:
            pass
        anomaly = getattr(runtime, "_anomaly", None)
        if anomaly is None or not hasattr(anomaly, "observe_rpc_error"):
            return
        try:
            threshold = int(os.environ.get("VICTOR_RPC_ERR_STREAK", "5") or "5")
        except ValueError:
            threshold = 5
        try:
            storm = bool(anomaly.observe_rpc_error(ok=False, threshold=threshold))
        except _SAFE_EXCEPTIONS:
            storm = False
        if not storm:
            return
        controls = getattr(getattr(runtime, "_cc", None), "controls", None)
        if controls is None:
            return
        try:
            if not bool(getattr(controls, "chaos_breakers_enabled", True)):
                return
        except _SAFE_EXCEPTIONS:
            return
        try:
            setattr(controls, "paused", True)
            setattr(controls, "defensive_mode", True)
            setattr(controls, "reduce_exposure_half", True)
            runtime._auto_trading = False
        except _SAFE_EXCEPTIONS:
            return
        cc = getattr(runtime, "_cc", None)
        if cc is None:
            return
        try:
            cc.persist_controls()
            cc.audit.append(
                "breaker_trip",
                {"kind": "rpc_error_storm", "threshold": threshold},
                actor="system",
                reason="rpc_error_storm",
            )
        except _SAFE_EXCEPTIONS:
            return

    @staticmethod
    def on_block_number_success(runtime: Any) -> None:
        anomaly = getattr(runtime, "_anomaly", None)
        if anomaly is None or not hasattr(anomaly, "observe_rpc_error"):
            return
        try:
            anomaly.observe_rpc_error(ok=True)
        except _SAFE_EXCEPTIONS:
            return

    def record_submit_to_receipt_latency(self, runtime: Any, latency_ms: int) -> None:
        if latency_ms <= 0 or not self.latency_profiling_enabled(runtime):
            return
        latency = getattr(runtime, "_lat", None)
        metrics = getattr(runtime, "metrics", None)
        if latency is None or metrics is None:
            return
        try:
            latency.add("submit_to_receipt_ms", float(latency_ms))
            summary = latency.get("submit_to_receipt_ms")
            metrics.submit_to_receipt_p50_ms = float(summary.get("p50", 0.0) or 0.0)
            metrics.submit_to_receipt_p90_ms = float(summary.get("p90", 0.0) or 0.0)
            metrics.submit_to_receipt_p99_ms = float(summary.get("p99", 0.0) or 0.0)
        except _SAFE_EXCEPTIONS:
            return

    def record_loop_latency(self, runtime: Any, loop_ms: float) -> None:
        try:
            runtime.metrics.last_tick_ms = int(loop_ms)
        except _SAFE_EXCEPTIONS:
            return
        if not self.latency_profiling_enabled(runtime):
            return
        latency = getattr(runtime, "_lat", None)
        if latency is None:
            return
        try:
            latency.add("loop_ms", float(loop_ms))
            summary = latency.get("loop_ms")
            runtime.metrics.loop_p50_ms = float(summary.get("p50", 0.0) or 0.0)
            runtime.metrics.loop_p90_ms = float(summary.get("p90", 0.0) or 0.0)
            runtime.metrics.loop_p99_ms = float(summary.get("p99", 0.0) or 0.0)
        except _SAFE_EXCEPTIONS:
            return
