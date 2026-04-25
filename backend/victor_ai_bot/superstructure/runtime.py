from __future__ import annotations

from ..pathing import canonical_data_dir

import time
import asyncio
from typing import Any, Dict, Optional, List, Mapping, Sequence, Tuple

from .registry import AgentRegistry, default_registry
from .types import AgentState
from .config import SuperstructureConfig
from .proposals import Proposal
from .negotiation import NegotiationEngine, NegotiationResult
from .capital import CapitalAuctionEngine, CapitalAllocation
from .path_planning import StrategyPathPlanner
from .stability import OrgStabilityMonitor
from ..caq_kds.bus import BUS
from ..runtime_services.profitability_truth import inspect_profit_after_costs_truth
from ..profitability_projection import profitability_summary_projection

import uuid
import hashlib

from .command_center import CommandCenter
from .gmao_governance import GMAOGovernance, GovernanceState


_SAFE_TASK_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, RuntimeError, TypeError, ValueError)
_SAFE_RUNTIME_EXCEPTIONS: Tuple[type[BaseException], ...] = (
    AttributeError,
    KeyError,
    IndexError,
    RuntimeError,
    TypeError,
    ValueError,
)
_SAFE_BUS_EXCEPTIONS: Tuple[type[BaseException], ...] = (AttributeError, KeyError, RuntimeError, TypeError, ValueError)


class SuperstructureRuntime:
    """Organizational multi-agent superstructure orchestrator.

    Phase 14 provides AGR + agent state machine + logging.
    Later phases add negotiation/capital/path planning/command center.

    This runtime is designed to be optional and non-invasive.
    """

    def __init__(self, *, cfg: Optional[Any], chain: str, data_dir: str):
        self.chain = str(chain or "global")
        self.data_dir = str(data_dir or canonical_data_dir('backend/data'))
        # cfg may be dict-like (older presets) or SuperstructureConfig
        self.cfg = self._coerce_cfg(cfg)
        self.registry: AgentRegistry = default_registry(data_dir=self.data_dir, chain=self.chain)
        self._running = False

        # Phase 17: human directives / overrides live here
        self._force_safe_mode_until: float = 0.0

        # Phase 15/16/18 modules are attached later (add-only)
        self.negotiation: Optional[NegotiationEngine] = None
        self.capital: Optional[CapitalAuctionEngine] = None
        self.path_planner = None
        self.command = None
        self.stability: Optional[OrgStabilityMonitor] = None

        # Phase 19: GMAO governance overlay (add-only)
        self.governance: Optional[GMAOGovernance] = None
        self._gov_task: Optional[asyncio.Task] = None

        self._loop_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_action": "",
            "last_ts": 0,
        }
        self._bus_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_channel": "",
            "last_ts": 0,
        }
        self._proposal_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }
        self._negotiation_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }
        self._governance_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }
        self._capital_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }
        self._path_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }
        self._stability_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_reason": "",
            "last_ts": 0,
        }
        self._directive_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_mode": "",
            "last_ts": 0,
        }
        self._outcome_state: Dict[str, Any] = {
            "ok": True,
            "last_error_code": "",
            "last_error": "",
            "last_proposal_id": "",
            "last_ts": 0,
        }

        if bool(self.cfg.enabled):
            # PHASE 15 engines
            self.negotiation = NegotiationEngine(
                data_dir=self.data_dir,
                chain=self.chain,
                lambda_risk=self.cfg.lambda_risk,
                lambda_latency=self.cfg.lambda_latency,
                lambda_funding=self.cfg.lambda_funding,
                lambda_reliability=self.cfg.lambda_reliability,
                lambda_graph_conf=self.cfg.lambda_graph_conf,
            )
            self.capital = CapitalAuctionEngine(max_fraction_per_task=self.cfg.max_capital_fraction_per_task, data_dir=self.data_dir, chain=self.chain)
            # PHASE 16 planner
            self.path_planner = StrategyPathPlanner(data_dir=self.data_dir, chain=self.chain)
            # PHASE 17: human command center
            if bool(self.cfg.human_enabled):
                self.command = CommandCenter(data_dir=self.data_dir, chain=self.chain)

            # PHASE 18: stability monitor
            if bool(self.cfg.enable_stability_monitor):
                self.stability = OrgStabilityMonitor(data_dir=self.data_dir, chain=self.chain, window_s=600.0)

            # PHASE 19: governance overlay
            if bool(getattr(self.cfg, "gmao_enabled", True)):
                gs = GovernanceState(
                    enabled=True,
                    autonomy_weight=float(getattr(self.cfg, "gmao_trilemma_autonomy_weight", 0.65)),
                    decentralization_weight=float(getattr(self.cfg, "gmao_trilemma_decentralization_weight", 0.55)),
                    efficiency_weight=float(getattr(self.cfg, "gmao_trilemma_efficiency_weight", 0.75)),
                    power_decay_rate=float(getattr(self.cfg, "gmao_power_decay_rate", 0.02)),
                    max_agent_power=float(getattr(self.cfg, "gmao_max_agent_power", 0.40)),
                    power_rotation_interval=int(getattr(self.cfg, "gmao_power_rotation_interval", 500) or 500),
                    reputation_decay_rate=float(getattr(self.cfg, "gmao_reputation_decay_rate", 0.01)),
                    reputation_min_threshold=float(getattr(self.cfg, "gmao_reputation_min_threshold", 0.30)),
                    risk_threshold_drawdown=float(getattr(self.cfg, "gmao_risk_threshold_drawdown", 0.15)),
                    risk_threshold_volatility=float(getattr(self.cfg, "gmao_risk_threshold_volatility", 0.30)),
                    risk_human_verified=float(getattr(self.cfg, "gmao_risk_human_verified", 0.80)),
                    risk_supervised=float(getattr(self.cfg, "gmao_risk_supervised", 0.50)),
                    health_interval_s=float(getattr(self.cfg, "gmao_health_interval_s", 1.0)),
                )
                self.governance = GMAOGovernance(
                    data_dir=self.data_dir,
                    chain=self.chain,
                    state=gs,
                    registry=self.registry,
                    command_center=self.command,
                )

    def _coerce_cfg(self, raw: Any) -> SuperstructureConfig:
        if isinstance(raw, SuperstructureConfig):
            return raw
        d = {}
        if isinstance(raw, dict):
            d = raw
        c = SuperstructureConfig(
            enabled=bool(d.get("enabled", False)),
            require_negotiation=bool(d.get("require_negotiation", True)),
            require_capital_auction=bool(d.get("require_capital_auction", True)),
            require_path_planning=bool(d.get("require_path_planning", True)),
            lambda_risk=float(d.get("lambda_risk", 1.0)),
            lambda_latency=float(d.get("lambda_latency", 0.05)),
            lambda_funding=float(d.get("lambda_funding", 0.5)),
            lambda_reliability=float(d.get("lambda_reliability", 0.6)),
            lambda_graph_conf=float(d.get("lambda_graph_conf", 0.4)),
            capital_total_wei=str(d.get("capital_total_wei", "0")),
            max_capital_fraction_per_task=float(d.get("max_capital_fraction_per_task", 0.60)),
            risk_override_drawdown=float(d.get("risk_override_drawdown", 0.15)),
            entropy_spike_th=float(d.get("entropy_spike_th", 0.25)),
            human_enabled=bool(d.get("human_enabled", True)),
            human_high_risk_threshold=float(d.get("human_high_risk_threshold", 0.80)),
            human_require_approval_for_high_risk=bool(d.get("human_require_approval_for_high_risk", True)),
            enable_stability_monitor=bool(d.get("enable_stability_monitor", True)),
            instability_trip_threshold=float(d.get("instability_trip_threshold", 0.75)),
            instability_cooldown_s=float(d.get("instability_cooldown_s", 120.0)),

            # Phase 19: GMAO governance overlay
            gmao_enabled=bool(d.get("gmao_enabled", True)),
            gmao_trilemma_autonomy_weight=float(d.get("gmao_trilemma_autonomy_weight", 0.65)),
            gmao_trilemma_decentralization_weight=float(d.get("gmao_trilemma_decentralization_weight", 0.55)),
            gmao_trilemma_efficiency_weight=float(d.get("gmao_trilemma_efficiency_weight", 0.75)),
            gmao_power_decay_rate=float(d.get("gmao_power_decay_rate", 0.02)),
            gmao_max_agent_power=float(d.get("gmao_max_agent_power", 0.40)),
            gmao_power_rotation_interval=int(d.get("gmao_power_rotation_interval", 500) or 500),
            gmao_reputation_decay_rate=float(d.get("gmao_reputation_decay_rate", 0.01)),
            gmao_reputation_min_threshold=float(d.get("gmao_reputation_min_threshold", 0.30)),
            gmao_risk_threshold_drawdown=float(d.get("gmao_risk_threshold_drawdown", 0.15)),
            gmao_risk_threshold_volatility=float(d.get("gmao_risk_threshold_volatility", 0.30)),
            gmao_risk_human_verified=float(d.get("gmao_risk_human_verified", 0.80)),
            gmao_risk_supervised=float(d.get("gmao_risk_supervised", 0.50)),
            gmao_health_interval_s=float(d.get("gmao_health_interval_s", 1.0)),
        )
        return c

    def _mark_bucket(
        self,
        bucket: Dict[str, Any],
        *,
        ok: bool,
        code: str = "",
        error: str = "",
        **extra: Any,
    ) -> None:
        bucket["ok"] = bool(ok)
        bucket["last_error_code"] = str(code or "")
        bucket["last_error"] = str(error or "")
        bucket["last_ts"] = int(time.time())
        if extra:
            bucket.update(extra)

    def _runtime_state(self) -> Dict[str, Any]:
        buckets = (
            self._loop_state,
            self._bus_state,
            self._proposal_state,
            self._negotiation_state,
            self._governance_state,
            self._capital_state,
            self._path_state,
            self._stability_state,
            self._directive_state,
            self._outcome_state,
        )
        return {
            "loop": dict(self._loop_state),
            "bus": dict(self._bus_state),
            "proposal": dict(self._proposal_state),
            "negotiation": dict(self._negotiation_state),
            "governance": dict(self._governance_state),
            "capital": dict(self._capital_state),
            "path_planning": dict(self._path_state),
            "stability": dict(self._stability_state),
            "directive": dict(self._directive_state),
            "outcomes": dict(self._outcome_state),
            "degraded": not all(bool(bucket.get("ok", True)) for bucket in buckets),
        }

    def _int_or_default(self, value: Any, *, default: int = 0) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return int(default)

    def _float_or_default(self, value: Any, *, default: float = 0.0) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return float(default)

    def _meta_dict(self, obj: Any) -> Dict[str, Any]:
        meta = getattr(obj, "meta", None)
        return dict(meta) if isinstance(meta, Mapping) else {}

    def _route_legs(self, opp: Any) -> List[Any]:
        route = getattr(opp, "route", None)
        legs = getattr(route, "legs", None)
        if isinstance(legs, Sequence):
            return list(legs)
        return []

    def _safe_snapshot(self, obj: Any, method_name: str, fallback: Dict[str, Any], *, bucket: Optional[Dict[str, Any]] = None, code: str = "") -> Dict[str, Any]:
        if obj is None:
            return dict(fallback)
        method = getattr(obj, method_name, None)
        if not callable(method):
            if bucket is not None and code:
                self._mark_bucket(bucket, ok=False, code=f"{code}_missing", error=f"missing_method:{method_name}")
            return dict(fallback)
        try:
            snap = method()
            if bucket is not None:
                self._mark_bucket(bucket, ok=True)
            return snap if isinstance(snap, dict) else dict(fallback)
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            if bucket is not None and code:
                self._mark_bucket(bucket, ok=False, code=code, error=str(exc))
            return dict(fallback)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.registry.transition("coordinator", AgentState.IDLE, reason="superstructure_start")

        # Phase 19: governance health loop (append-only extension)
        if self.governance is not None and self._gov_task is None:
            try:
                self._gov_task = asyncio.create_task(self._gov_loop())
                self._mark_bucket(self._loop_state, ok=True, last_action="gov_loop_start")
            except _SAFE_TASK_EXCEPTIONS as exc:
                self._gov_task = None
                self._mark_bucket(self._loop_state, ok=False, code="gov_loop_start_failed", error=str(exc), last_action="gov_loop_start")

    async def stop(self) -> None:
        self._running = False
        self.registry.transition("coordinator", AgentState.IDLE, reason="superstructure_stop")
        try:
            if self._gov_task is not None:
                self._gov_task.cancel()
            self._mark_bucket(self._loop_state, ok=True, last_action="gov_loop_cancel")
        except _SAFE_TASK_EXCEPTIONS as exc:
            self._mark_bucket(self._loop_state, ok=False, code="gov_loop_cancel_failed", error=str(exc), last_action="gov_loop_cancel")
        self._gov_task = None

    async def _gov_loop(self) -> None:
        """SYSTEM LOOP EXTENSION: governance health check (non-breaking).

        Runs at ~1s cadence while the runtime is active.
        """
        interval = 1.0
        try:
            interval = float(getattr(self.cfg, "gmao_health_interval_s", 1.0) or 1.0)
        except (AttributeError, TypeError, ValueError) as exc:
            interval = 1.0
            self._mark_bucket(self._loop_state, ok=False, code="gov_loop_interval_invalid", error=str(exc), last_action="gov_loop_interval")
        interval = max(0.5, min(5.0, interval))
        while self._running:
            try:
                st = self.stability.last() if self.stability is not None else None
                if self.governance is not None:
                    self.governance.health_check(stability_snapshot=(st or {}))
                self._mark_bucket(self._loop_state, ok=True, last_action="gov_health_check")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_bucket(self._loop_state, ok=False, code="gov_health_check_failed", error=str(exc), last_action="gov_health_check")
            await asyncio.sleep(interval)

    def state(self) -> Dict[str, Any]:
        directive = {}
        if self.command is not None:
            try:
                raw_directive = self.command.directive()
                directive = raw_directive if isinstance(raw_directive, dict) else {}
                self._mark_bucket(
                    self._directive_state,
                    ok=True,
                    last_mode=str(directive.get("mode") or directive.get("directive") or ""),
                )
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                directive = {}
                self._mark_bucket(self._directive_state, ok=False, code="directive_snapshot_failed", error=str(exc), last_mode="")
        return {
            "ok": True,
            "enabled": bool(self.cfg.enabled),
            "chain": self.chain,
            "running": bool(self._running),
            "directive": directive,
            "safe_mode": bool(time.time() <= self._force_safe_mode_until),
            "registry": self.registry.snapshot(limit_transitions=200),
            "negotiation": self._safe_snapshot(self.negotiation, "last", {"ok": True, "negotiation": None}, bucket=self._negotiation_state, code="negotiation_snapshot_failed"),
            "capital": self._safe_snapshot(self.capital, "last", {"ok": True, "allocation": None}, bucket=self._capital_state, code="capital_snapshot_failed"),
            "path_planning": self._safe_snapshot(self.path_planner, "last", {"ok": True, "plan": None}, bucket=self._path_state, code="path_snapshot_failed"),
            "command_center": self._safe_snapshot(self.command, "snapshot", {"ok": True, "enabled": False}),
            "stability": self._safe_snapshot(self.stability, "last", {"ok": True, "enabled": False}, bucket=self._stability_state, code="stability_snapshot_failed"),
            "governance": self._safe_snapshot(self.governance, "snapshot", {"ok": True, "enabled": False}, bucket=self._governance_state, code="governance_snapshot_failed"),
            "runtime": self._runtime_state(),
        }

    # --- Phase 17: human directives ---
    def set_directive(self, directive: Dict[str, Any], *, ttl_s: float = 6 * 3600.0) -> None:
        if self.command is not None:
            self.command.set_directive(directive, ttl_s=float(ttl_s or 0.0))

    def force_safe_mode(self, *, ttl_s: float = 120.0, reason: str = "") -> None:
        self._force_safe_mode_until = max(self._force_safe_mode_until, float(time.time() + max(10.0, float(ttl_s or 0.0))))
        self.registry.transition("coordinator", AgentState.SUSPENDED, reason=f"safe_mode:{reason}"[:200])


    # -------------------------
    # PHASE 15: negotiation gate
    # -------------------------
    def _bus(self) -> Dict[str, Any]:
        try:
            snap = BUS.snapshot()
            self._mark_bucket(self._bus_state, ok=True, last_channel="snapshot")
            return snap if isinstance(snap, dict) else {}
        except _SAFE_BUS_EXCEPTIONS as exc:
            self._mark_bucket(self._bus_state, ok=False, code="bus_snapshot_failed", error=str(exc), last_channel="snapshot")
            return {}

    def _reliability(self) -> float:
        snap = self._bus()
        rel = (snap.get("reliability") or {}).get("data") or {}
        return self._float_or_default(rel.get("reliability", 0.0), default=0.0)

    def _funding_adv(self) -> float:
        snap = self._bus()
        cex = (snap.get("cex") or {}).get("data") or {}
        return self._float_or_default(cex.get("funding_bps", 0.0), default=0.0) / 10.0

    def _graph_conf(self) -> float:
        # best effort: from MKG GraphRAG context if present
        snap = self._bus()
        try:
            sg = (snap.get("S_global") or {}).get("data") or {}
            ctx = sg.get("context") or {}
            if isinstance(ctx, dict):
                return float(ctx.get("graph_confidence", 0.5) or 0.5)
        except (AttributeError, TypeError, ValueError) as exc:
            self._mark_bucket(self._bus_state, ok=False, code="graph_confidence_unavailable", error=str(exc), last_channel="S_global")
        return 0.5

    def _expected_return_bps(self, *, profit_after_costs: int, amount_in: int) -> float:
        if amount_in <= 0:
            return 0.0
        return float((profit_after_costs / float(amount_in)) * 10000.0)

    def _risk_score(self, *, gas_ratio: float, p_success: float, legs: int, mev_risk: float, drawdown: float) -> float:
        # Produce [0,1] score.
        # gas_ratio typical ~0.0001, scale up.
        gr = min(1.0, abs(float(gas_ratio)) / 0.002)
        ps = min(1.0, max(0.0, float(p_success)))
        lpen = min(1.0, max(0.0, (int(legs) - 2) / 3.0))
        mr = min(1.0, max(0.0, float(mev_risk)))
        dd = min(1.0, max(0.0, float(drawdown)))
        r = 0.30 * gr + 0.25 * (1.0 - ps) + 0.20 * lpen + 0.15 * mr + 0.10 * dd
        return float(max(0.0, min(1.0, r)))

    def _profit_after_costs_info(self, opp: Any) -> Tuple[int, bool, str]:
        projection = profitability_summary_projection(opp)
        amount = int(max(0, self._int_or_default(projection.get("displayProfitAfterCostsWeiInt") or 0, default=0)))
        valid = bool(projection.get("valid", False))
        reason = str(projection.get("reason") or "profit_after_costs_unavailable")
        stale = bool(projection.get("stale", False))
        if stale or reason in {"profit_after_costs_invalid", "profit_after_costs_mismatch"}:
            self._mark_bucket(
                self._proposal_state,
                ok=False,
                code=f"proposal_{reason}",
                error=reason,
                last_proposal_id="",
            )
            return 0, False, reason
        return amount, valid, reason

    def build_trade_proposal(self, *, opp: Any, decision: Any = None, mode: str = "auto") -> Proposal:
        legs_list = self._route_legs(opp)
        first_leg = legs_list[0] if legs_list else None
        meta_dict = self._meta_dict(opp)

        # Extract base quantities
        amount_in = self._int_or_default(getattr(first_leg, "amount_in", "0") if first_leg is not None else 0, default=0)
        profit_after, profit_after_verified, profit_after_reason = self._profit_after_costs_info(opp)

        # local state and safety
        raw_brain = meta_dict.get("brain") or {}
        brain = dict(raw_brain) if isinstance(raw_brain, Mapping) else {}
        p_succ = self._float_or_default(brain.get("p_success", getattr(decision, "p_success", 0.75)), default=0.75)
        gas_ratio = self._float_or_default(brain.get("gas_ratio", 0.0), default=0.0)
        legs = len(legs_list) if legs_list else 2

        snap = self._bus()
        mev = (snap.get("mev") or {}).get("data") or {}
        mev_risk = self._float_or_default(mev.get("sandwich_risk", 0.0), default=0.0)

        rel = (snap.get("reliability") or {}).get("data") or {}
        drawdown = self._float_or_default(rel.get("max_drawdown", 0.0), default=0.0)

        risk_score = self._risk_score(gas_ratio=gas_ratio, p_success=p_succ, legs=legs, mev_risk=mev_risk, drawdown=drawdown)
        exp_bps = self._expected_return_bps(profit_after_costs=profit_after, amount_in=amount_in)

        overlap: List[str] = []
        rid = str(meta_dict.get("route_id") or getattr(opp, "route_id", "") or "")
        if rid:
            overlap.append(f"route:{rid}")
        for lg in legs_list[:6]:
            to = str(getattr(lg, "to", "") or "")
            if to:
                overlap.append(f"to:{to.lower()}")

        confidence = max(0.0, min(1.0, float(p_succ)))
        # Deterministic proposal id enables human approval workflows.
        pid_src = f"{self.chain}|trade|{getattr(opp, 'id', '')}|{meta_dict.get('route_id','')}|{amount_in}"
        pid = hashlib.blake2b(pid_src.encode("utf-8", errors="ignore"), digest_size=16).hexdigest()

        projection = profitability_summary_projection(opp)
        meta = {"mode": str(mode), "legs": int(legs), "profit_after_costs_wei": str(int(max(0, profit_after))), "profit_after_costs_verified": bool(profit_after_verified), "profit_after_costs_reason": str(profit_after_reason or "ok"), "profitability": {"stale": bool(projection.get("stale", False)), "reason": str(projection.get("reason") or "ok"), "state_contract": dict(projection.get("stateContract") or {}), "post_mutation_revalidation": dict(projection.get("postMutationRevalidation") or {})}}

        # Phase 19: attach governance power/reputation (add-only)
        if self.governance is not None:
            try:
                meta["gov_power"] = float(self.governance.get_agent_power("strategy_initiator"))
                meta["gov_rep"] = float(self.governance.get_agent_reputation("strategy_initiator"))
                self._mark_bucket(self._governance_state, ok=True, last_proposal_id=f"trade:{pid}")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_bucket(self._governance_state, ok=False, code="proposal_governance_metadata_failed", error=str(exc), last_proposal_id=f"trade:{pid}")

        proposal = Proposal(
            proposal_id=f"trade:{pid}",
            kind="trade",
            agent_id="strategy_initiator",
            expected_return=float(exp_bps),
            risk_score=float(risk_score),
            capital_required=float(max(0.0, float(amount_in))),
            execution_latency=float(0.0),
            funding_advantage=float(self._funding_adv()),
            graph_confidence=float(self._graph_conf()),
            reliability_score=float(self._reliability()),
            confidence=float(confidence),
            overlap_keys=overlap,
            meta=meta,
        )
        if profit_after_reason in {"profit_after_costs_invalid", "profit_after_costs_mismatch"}:
            self._mark_bucket(
                self._proposal_state,
                ok=False,
                code=(
                    "proposal_profit_after_costs_invalid"
                    if profit_after_reason == "profit_after_costs_invalid"
                    else "proposal_profit_after_costs_mismatch"
                ),
                error=str(profit_after_reason),
                last_proposal_id=str(proposal.proposal_id),
            )
        else:
            self._mark_bucket(self._proposal_state, ok=True, last_proposal_id=str(proposal.proposal_id))
        return proposal

    def pre_execute_trade(self, *, opp: Any, decision: Any = None, mode: str = "auto", current_gas_mode: str = "standard", current_send_mode: str = "public") -> Dict[str, Any]:
        """Run negotiation + capital auction gate for a *trade* opportunity."""
        if not bool(self.cfg.enabled):
            return {"ok": True, "allow": True, "reason": "disabled", "size_mult": 1.0}
        if time.time() <= self._force_safe_mode_until:
            return {"ok": True, "allow": False, "reason": "safe_mode", "size_mult": 0.0}

        # Governance/Command safety: suspended initiator/executor blocks execution.
        try:
            h = self.registry.get("strategy_initiator")
            if h is not None and bool(getattr(h, "suspended", False)):
                return {"ok": True, "allow": False, "reason": "agent_suspended:strategy_initiator", "size_mult": 0.0}
            ex = self.registry.get("trade_executor")
            if ex is not None and bool(getattr(ex, "suspended", False)):
                return {"ok": True, "allow": False, "reason": "agent_suspended:trade_executor", "size_mult": 0.0}
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_bucket(self._negotiation_state, ok=False, code="registry_suspend_check_failed", error=str(exc), last_proposal_id="")
        if self.negotiation is None and self.cfg.require_negotiation:
            return {"ok": False, "allow": False, "reason": "negotiation_unavailable", "size_mult": 0.0}

        self.registry.transition("strategy_initiator", AgentState.EVALUATING, reason="build_proposal")
        p = self.build_trade_proposal(opp=opp, decision=decision, mode=mode)
        profit_after_verified = bool((p.meta or {}).get("profit_after_costs_verified", False))
        profit_after_reason = str((p.meta or {}).get("profit_after_costs_reason") or "profit_after_costs_unavailable")
        if not profit_after_verified:
            return {
                "ok": True,
                "allow": False,
                "reason": profit_after_reason,
                "size_mult": 0.0,
                "overrides": {},
            }
        if float(p.expected_return) <= 0.0:
            return {
                "ok": True,
                "allow": False,
                "reason": "profit_after_costs_not_positive",
                "size_mult": 0.0,
                "overrides": {},
            }
        props = [p]
        self.registry.transition("negotiator", AgentState.NEGOTIATING, reason="negotiate")

        nr = self.negotiation.negotiate(props, reason=f"trade:{mode}") if self.negotiation else None
        self._mark_bucket(self._negotiation_state, ok=True, last_proposal_id=str(p.proposal_id))
        if self.stability is not None and nr is not None:
            try:
                self.stability.record("negotiation", nr.as_dict())
                # conflicts are suppressed with reason=conflict_overlap
                for s in (nr.suppressed or []):
                    if str(s.get("reason")) == "conflict_overlap":
                        self.stability.record("conflict", s)
                self._mark_bucket(self._stability_state, ok=True, last_reason="negotiation")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_bucket(self._stability_state, ok=False, code="stability_negotiation_record_failed", error=str(exc), last_reason="negotiation")
        chosen = (nr.selected if nr else p)
        if not chosen or chosen.proposal_id != p.proposal_id:
            if self.stability is not None:
                try:
                    self.stability.record("rejection", {"reason": "proposal_not_selected"})
                    self._mark_bucket(self._stability_state, ok=True, last_reason="proposal_not_selected")
                except _SAFE_RUNTIME_EXCEPTIONS as exc:
                    self._mark_bucket(self._stability_state, ok=False, code="stability_rejection_record_failed", error=str(exc), last_reason="proposal_not_selected")
            return {"ok": True, "allow": False, "reason": "proposal_not_selected", "size_mult": 0.0, "negotiation": (nr.as_dict() if nr else None)}

        # Phase 19: Governance wrapper (non-breaking overlay)
        gov = None
        if self.governance is not None:
            try:
                gov = self.governance.wrapper_execution(
                    core_command="trade_execute",
                    agent_id=str(chosen.agent_id),
                    risk_level=float(chosen.risk_score),
                    proposal_id=str(chosen.proposal_id),
                )
                self._mark_bucket(self._governance_state, ok=True, last_proposal_id=str(chosen.proposal_id))
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                gov = None
                self._mark_bucket(self._governance_state, ok=False, code="governance_wrapper_failed", error=str(exc), last_proposal_id=str(chosen.proposal_id))
        if isinstance(gov, dict) and not bool(gov.get("allow", True)):
            # Governance blocks execution until human override.
            if self.stability is not None:
                try:
                    self.stability.record("rejection", {"reason": "governance_block", "governance": gov, "proposal_id": chosen.proposal_id})
                    self._mark_bucket(self._stability_state, ok=True, last_reason="governance_block")
                except _SAFE_RUNTIME_EXCEPTIONS as exc:
                    self._mark_bucket(self._stability_state, ok=False, code="stability_governance_block_record_failed", error=str(exc), last_reason="governance_block")
            return {"ok": True, "allow": False, "reason": f"governance_block:{gov.get('authority','')}", "size_mult": 0.0, "negotiation": (nr.as_dict() if nr else None), "governance": gov}

        if bool(self.cfg.human_enabled) and bool(self.cfg.human_require_approval_for_high_risk):
            # Also require human approval when governance requests it.
            gov_needs = bool((gov or {}).get("human_required", False)) if isinstance(gov, dict) else False
            if float(chosen.risk_score) >= float(self.cfg.human_high_risk_threshold) or gov_needs:
                approved = bool(self.command.is_approved(chosen.proposal_id)) if self.command is not None else False
                if not approved:
                    if self.stability is not None:
                        try:
                            self.stability.record("rejection", {"reason": "human_approval_required", "proposal_id": chosen.proposal_id, "governance": gov})
                            self._mark_bucket(self._stability_state, ok=True, last_reason="human_approval_required")
                        except _SAFE_RUNTIME_EXCEPTIONS as exc:
                            self._mark_bucket(self._stability_state, ok=False, code="stability_human_approval_record_failed", error=str(exc), last_reason="human_approval_required")
                    return {"ok": True, "allow": False, "reason": "human_approval_required", "size_mult": 0.0, "negotiation": (nr.as_dict() if nr else None)}

        size_mult = 1.0
        alloc = None
        if self.capital is not None and bool(self.cfg.require_capital_auction):
            total = float(self._int_or_default(str(self.cfg.capital_total_wei or "0"), default=0))
            if total <= 0.0:
                total = float(max(0.0, chosen.capital_required))
            alloc = self.capital.allocate(props, total_capital=total)
            self._mark_bucket(self._capital_state, ok=True, last_proposal_id=str(chosen.proposal_id))
            if self.stability is not None and alloc is not None:
                try:
                    self.stability.record("capital", alloc.as_dict())
                    self._mark_bucket(self._stability_state, ok=True, last_reason="capital")
                except _SAFE_RUNTIME_EXCEPTIONS as exc:
                    self._mark_bucket(self._stability_state, ok=False, code="stability_capital_record_failed", error=str(exc), last_reason="capital")
            got = float(alloc.allocations.get(chosen.proposal_id, 0.0) or 0.0)
            req = float(max(1.0, chosen.capital_required))
            size_mult = float(max(0.10, min(1.0, got / req)))

        overrides: Dict[str, Any] = {}
        plan = None
        if self.path_planner is not None and bool(self.cfg.require_path_planning):
            try:
                plan = self.path_planner.plan(opp=opp, current_gas_mode=current_gas_mode, current_send_mode=current_send_mode)
                overrides = dict(plan.chosen or {})
                if self.stability is not None and plan is not None:
                    self.stability.record("plan", plan.as_dict())
                    self._mark_bucket(self._stability_state, ok=True, last_reason="path_plan")
                self._mark_bucket(self._path_state, ok=True, last_proposal_id=str(chosen.proposal_id))
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                plan = None
                overrides = {}
                self._mark_bucket(self._path_state, ok=False, code="path_plan_failed", error=str(exc), last_proposal_id=str(chosen.proposal_id))

        # Phase 18: compute stability and auto-degrade to safe mode if needed.
        if self.stability is not None:
            try:
                snap = self.stability.compute(trip_threshold=float(self.cfg.instability_trip_threshold))
                if bool(snap.tripped):
                    # safest response: temporary safe mode, reduce exploration.
                    self.force_safe_mode(ttl_s=float(self.cfg.instability_cooldown_s), reason="org_instability")
                    if self.command is not None:
                        self.command.set_exploration_cap(0.25)
                        self.command.set_risk_multiplier(0.60)
                        self.command.set_directive({"mode": "Maximize stability mode", "reason": "org_instability"}, ttl_s=float(self.cfg.instability_cooldown_s))
                self._mark_bucket(self._stability_state, ok=True, last_reason="compute")
            except _SAFE_RUNTIME_EXCEPTIONS as exc:
                self._mark_bucket(self._stability_state, ok=False, code="stability_compute_failed", error=str(exc), last_reason="compute")

        self.registry.transition("trade_executor", AgentState.EXECUTING, reason="approved")
        self.registry.transition("trade_executor", AgentState.WAITING, reason="dispatched")
        # Apply macro directive (best-effort, conservative)
        try:
            directive = self.command.directive() if self.command else {}
            if isinstance(directive, dict) and directive:
                mode_hint = str(directive.get("mode") or directive.get("directive") or "").lower()
                if "stability" in mode_hint:
                    # force conservative exec params
                    overrides["gas_mode"] = "standard"
                    overrides["send_mode"] = "private" if overrides.get("send_mode") != "private" else overrides.get("send_mode")
                    size_mult = min(size_mult, 0.60)
                if "reduce mev" in mode_hint:
                    overrides["send_mode"] = "private"
            self._mark_bucket(self._directive_state, ok=True, last_mode=str((directive or {}).get("mode") or (directive or {}).get("directive") or ""))
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_bucket(self._directive_state, ok=False, code="directive_apply_failed", error=str(exc), last_mode="")

        return {
            "ok": True,
            "allow": True,
            "reason": "approved",
            "size_mult": float(size_mult),
            "negotiation": (nr.as_dict() if nr else None),
            "capital": (alloc.as_dict() if alloc else None),
            "path_plan": (plan.as_dict() if plan else None),
            "overrides": overrides,
            "governance": gov,
        }

    # -------------------------
    # Phase 19: outcome hooks (governance power/reputation)
    # -------------------------

    def trade_proposal_id(self, *, opportunity_id: str, route_id: str, amount_in: int) -> str:
        """Deterministic mapping used by human approvals + governance."""
        pid_src = f"{self.chain}|trade|{opportunity_id}|{route_id}|{int(amount_in)}"
        pid = hashlib.blake2b(pid_src.encode("utf-8", errors="ignore"), digest_size=16).hexdigest()
        return f"trade:{pid}"

    def on_trade_outcome(
        self,
        *,
        opportunity_id: str,
        route_id: str,
        amount_in: int,
        ok: bool,
        expected_after_costs_wei: int,
        realized_after_gas_wei: int,
    ) -> None:
        if self.governance is None:
            return

        # performance_score: scaled by realized vs expected (bounded)
        perf = 0.0
        try:
            exp = max(1, int(expected_after_costs_wei))
            real = int(max(0, realized_after_gas_wei)) if ok else 0
            perf = float(min(1.0, real / float(exp)))
        except (TypeError, ValueError) as exc:
            perf = 1.0 if ok else 0.0
            self._mark_bucket(self._outcome_state, ok=False, code="outcome_perf_invalid", error=str(exc), last_proposal_id=self.trade_proposal_id(opportunity_id=opportunity_id, route_id=route_id, amount_in=amount_in))

        # outcome_score: +1 for success, -1 for revert, small negatives for low-realization
        out = 1.0 if ok else -1.0
        if ok and perf < 0.25:
            out = -0.25
        if ok and perf < 0.05:
            out = -0.75

        try:
            self.governance.on_outcome(agent_id="strategy_initiator", performance_score=float(perf), outcome_score=float(out))
            self._mark_bucket(self._outcome_state, ok=True, last_proposal_id=self.trade_proposal_id(opportunity_id=opportunity_id, route_id=route_id, amount_in=amount_in))
        except _SAFE_RUNTIME_EXCEPTIONS as exc:
            self._mark_bucket(self._outcome_state, ok=False, code="outcome_governance_hook_failed", error=str(exc), last_proposal_id=self.trade_proposal_id(opportunity_id=opportunity_id, route_id=route_id, amount_in=amount_in))
