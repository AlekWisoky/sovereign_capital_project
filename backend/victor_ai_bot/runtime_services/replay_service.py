from __future__ import annotations

from typing import Any, Dict, List

from ..runtime_subsystems import ReplayBundleStore


class ReplayService:
    def controls_for_replay(self, runtime: Any) -> Dict[str, Any]:
        try:
            controls = getattr(getattr(runtime, "_cc", None), "controls", None)
            return dict(getattr(controls, "__dict__", {}) or {})
        except (AttributeError, KeyError, TypeError, ValueError):
            return {}

    def runtime_context_for_replay(self, runtime: Any) -> Dict[str, Any]:
        rpc_state = {}
        try:
            rpc_state = runtime.rpc_manager.snapshot()
        except (AttributeError, KeyError, TypeError, ValueError):
            rpc_state = {}
        try:
            rpc_degraded = bool(float((rpc_state or {}).get("error_rate") or 0.0) >= 0.10)
        except (AttributeError, KeyError, TypeError, ValueError):
            rpc_degraded = False
        regime = "unknown"
        try:
            from ..event_bus.publishers import BUS

            snap = BUS.snapshot()
            if isinstance(snap, dict):
                regime = str((snap.get("behaveagent") or {}).get("regime_label") or "unknown")
        except (AttributeError, KeyError, TypeError, ValueError, ImportError):
            regime = "unknown"
        return {
            "portfolio": {
                "state": (
                    "paused"
                    if not bool(getattr(runtime, "_auto_trading", False))
                    else (
                        "defensive"
                        if bool(self.controls_for_replay(runtime).get("defensive_mode", False))
                        else "active"
                    )
                ),
                "updatedAtMs": int(__import__("time").time() * 1000),
            },
            "regime": {"current": regime},
            "risk": {
                "caps": {
                    "maxDailyLossPct": float(
                        getattr(getattr(runtime, "cfg", None).safety, "max_daily_loss_pct", 3.0)
                        if hasattr(getattr(runtime, "cfg", None), "safety")
                        else 3.0
                    ),
                    "maxExposurePct": 80.0,
                    "sandboxCapPct": 10.0,
                    "probationCapPct": 2.5,
                },
                "breakers": {
                    "drawdownBreaker": False,
                    "gasAnomalyBreaker": (
                        bool(
                            getattr(
                                getattr(runtime, "_anomaly", None), "snapshot", lambda: {}
                            )().get("gas_spike", False)
                        )
                        if getattr(runtime, "_anomaly", None) is not None
                        else False
                    ),
                    "driftBreaker": False,
                },
            },
            "rpcDegraded": bool(rpc_degraded),
            "observability": {
                "loopMsP50": int(getattr(runtime.metrics, "loop_p50_ms", 0.0) or 0),
                "loopMsP90": int(getattr(runtime.metrics, "loop_p90_ms", 0.0) or 0),
                "loopMsP99": int(getattr(runtime.metrics, "loop_p99_ms", 0.0) or 0),
                "execLatencyMsP50": int(getattr(runtime.metrics, "exec_e2e_p50_ms", 0.0) or 0),
                "execLatencyMsP90": int(getattr(runtime.metrics, "exec_e2e_p90_ms", 0.0) or 0),
                "execLatencyMsP99": int(getattr(runtime.metrics, "exec_e2e_p99_ms", 0.0) or 0),
                "submitToReceiptMsP50": int(
                    getattr(runtime.metrics, "submit_to_receipt_p50_ms", 0.0) or 0
                ),
                "submitToReceiptMsP90": int(
                    getattr(runtime.metrics, "submit_to_receipt_p90_ms", 0.0) or 0
                ),
                "submitToReceiptMsP99": int(
                    getattr(runtime.metrics, "submit_to_receipt_p99_ms", 0.0) or 0
                ),
            },
            "metrics": (
                runtime.metrics.model_dump()
                if hasattr(runtime.metrics, "model_dump")
                else runtime.metrics.dict()
            ),
        }

    def top_opportunities_for_replay(self, runtime: Any) -> List[Dict[str, Any]]:
        try:
            topk = int(
                getattr(getattr(runtime.cfg.execution, "rft", None), "snapshot_top_k", 20) or 20
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            topk = 20
        try:
            return ReplayBundleStore.summarize_opportunities(runtime._opps, limit=topk)
        except (AttributeError, KeyError, TypeError, ValueError):
            return []

    def replay_export_enabled(self, runtime: Any) -> bool:
        try:
            rft_cfg = getattr(runtime.cfg.execution, "rft", None)
            return bool(
                getattr(rft_cfg, "enable_reward_trace_export", True)
                or getattr(rft_cfg, "episode_export_enabled", False)
                or getattr(rft_cfg, "enabled", False)
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            return False

    def wealth_goal_for_replay(self, runtime: Any) -> Dict[str, Any]:
        service = getattr(runtime, "_wealth_goal_service", None)
        if service is None or not hasattr(service, "replay_payload"):
            return {}
        try:
            return dict(service.replay_payload(runtime) or {})
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError):
            return {}

    def create_bundle(
        self,
        runtime: Any,
        *,
        opportunity_id: str,
        route_id: str,
        mode: str,
        rl_state: str,
        rl_action: int,
        latency_ms: int,
        plan: Dict[str, Any],
        dry_run: bool,
        ok: bool,
        attempted: bool,
        submitted: bool,
        reason: str,
        tx_hash: str = "",
        audit_hash: str = "",
        block_number: int = 0,
        status: str = "draft",
    ) -> str:
        replay = getattr(runtime, "_replay", None)
        if replay is None or not self.replay_export_enabled(runtime):
            return ""
        try:
            block_i = int(block_number or 0)
        except (AttributeError, KeyError, TypeError, ValueError):
            block_i = 0
        if block_i <= 0:
            try:
                block_i = int(
                    plan.get("current_block") or getattr(runtime.metrics, "lastBlock", 0) or 0
                )
            except (AttributeError, KeyError, TypeError, ValueError):
                block_i = 0
        try:
            gas_mode = str(
                plan.get("gas_mode")
                or getattr(runtime.cfg.execution, "gas_mode", "standard")
                or "standard"
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            gas_mode = "standard"
        try:
            send_mode = str(
                plan.get("send_mode")
                or getattr(runtime.cfg.execution, "send_mode", "public")
                or "public"
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            send_mode = "public"
        try:
            slippage_bps = int(
                plan.get("slippage_bps") or getattr(runtime.cfg.safety, "slippage_bps", 50) or 50
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            slippage_bps = 50
        try:
            deadline_seconds = int(
                plan.get("deadline_seconds")
                or getattr(runtime.cfg.execution, "deadline_seconds", 30)
                or 30
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            deadline_seconds = 30
        try:
            bundle = replay.create_bundle(
                block_number=int(block_i),
                opportunity_id=str(opportunity_id or ""),
                route_id=str(route_id or ""),
                mode=str(mode or ""),
                rl_state=str(rl_state or ""),
                rl_action=int(rl_action or -1),
                runtime=self.runtime_context_for_replay(runtime),
                controls=self.controls_for_replay(runtime),
                wealth_goal=self.wealth_goal_for_replay(runtime),
                opportunities=self.top_opportunities_for_replay(runtime),
                execution={
                    "mode": str(mode or ""),
                    "send_mode": send_mode,
                    "gas_mode": gas_mode,
                    "slippage_bps": int(slippage_bps),
                    "deadline_seconds": int(deadline_seconds),
                    "dry_run": bool(dry_run),
                    "ok": bool(ok),
                    "attempted": bool(attempted),
                    "submitted": bool(submitted),
                    "reason": str(reason or ""),
                    "latency_ms": int(latency_ms or 0),
                    "plan": dict(plan or {}),
                },
                tx_hash=str(tx_hash or ""),
                status=str(status or "draft"),
                audit_hash=str(audit_hash or ""),
            )
            return str((bundle or {}).get("event_id") or "")
        except (AttributeError, KeyError, TypeError, ValueError):
            return ""
