from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from ..execution_capture.pending_state_context import build_pending_state_context
from ..deploy_mode import is_public_mode, public_broadcast_override_enabled


def _safe_dict(x: Any) -> Dict[str, Any]:
    return dict(x or {}) if isinstance(x, dict) else {}


@dataclass(frozen=True)
class PendingStateSnapshot:
    rows: List[Dict[str, Any]]
    context: Dict[str, Any]

    @property
    def summary(self) -> Dict[str, Any]:
        ctx = self.context if isinstance(self.context, dict) else {}
        return dict(ctx.get("summary") or {})


@dataclass(frozen=True)
class RuntimeDecisionContext:
    wealth_goal: Dict[str, Any]
    drawdown_state: Dict[str, Any]
    kill_switch_state: Dict[str, Any]
    treasury_state: Dict[str, Any]


@dataclass(frozen=True)
class RuntimeAccessSnapshot:
    chain_id: int
    regime: str
    public_mode: bool
    force_send_mode: str
    wealth_goal: Dict[str, Any]
    drawdown_state: Dict[str, Any]
    kill_switch_state: Dict[str, Any]
    treasury_state: Dict[str, Any]


def build_runtime_access_snapshot(runtime: Any) -> RuntimeAccessSnapshot:
    decision = build_runtime_decision_context(runtime)
    chain = getattr(getattr(runtime, "cfg", None), "chain", None)
    regime = str(_safe_dict(getattr(runtime, "_market_regime", {})).get("regime") or "balanced")
    return RuntimeAccessSnapshot(
        chain_id=int(getattr(chain, "chain_id", 0) or 0),
        regime=regime,
        public_mode=public_mode_for_capture(runtime),
        force_send_mode=force_send_mode(runtime),
        wealth_goal=dict(decision.wealth_goal),
        drawdown_state=dict(decision.drawdown_state),
        kill_switch_state=dict(decision.kill_switch_state),
        treasury_state=dict(decision.treasury_state),
    )


def build_runtime_decision_context_from_snapshot(
    snapshot: RuntimeAccessSnapshot,
) -> RuntimeDecisionContext:
    return RuntimeDecisionContext(
        wealth_goal=dict(snapshot.wealth_goal),
        drawdown_state=dict(snapshot.drawdown_state),
        kill_switch_state=dict(snapshot.kill_switch_state),
        treasury_state=dict(snapshot.treasury_state),
    )


def _safe_mapping(x: Any) -> Mapping[str, Any]:
    return x if isinstance(x, Mapping) else {}


@dataclass(frozen=True)
class AdmissionContext:
    chain_id: int
    regime: str
    public_mode: bool
    force_send_mode: str
    pending: PendingStateSnapshot
    decision: RuntimeDecisionContext

    @property
    def pending_state(self) -> List[Dict[str, Any]]:
        return list(self.pending.rows)

    @property
    def pending_context(self) -> Dict[str, Any]:
        return dict(self.pending.context)

    @property
    def wealth_goal(self) -> Dict[str, Any]:
        return dict(self.decision.wealth_goal)

    @property
    def drawdown_state(self) -> Dict[str, Any]:
        return dict(self.decision.drawdown_state)

    @property
    def kill_switch_state(self) -> Dict[str, Any]:
        return dict(self.decision.kill_switch_state)

    @property
    def treasury_state(self) -> Dict[str, Any]:
        return dict(self.decision.treasury_state)


@dataclass(frozen=True)
class WealthGoalSignals:
    current_return_pct: float
    fund_stage: str
    drawdown_pct: float
    risk_posture: str
    hard_stop: bool
    kill_switch: bool
    capital_base_usd: float
    stability_score: float
    execution_realism_score: float
    risk_score: float
    false_admission_rate: float
    false_drop_rate: float


def public_mode_for_capture(_: Any) -> bool:
    return bool(is_public_mode() and not public_broadcast_override_enabled())


def force_send_mode(runtime: Any) -> str:
    try:
        cc = getattr(runtime, "_cc", None)
        controls = getattr(cc, "controls", None) if cc is not None else None
        return str(getattr(controls, "force_send_mode", "") or "")
    except (AttributeError, KeyError, TypeError, ValueError):
        return ""


def pending_state_for_opp(runtime: Any, opp: Any) -> List[Dict[str, Any]]:
    try:
        if (
            hasattr(runtime, "_pending_state_for_opp")
            and str(getattr(runtime.__class__, "__module__", "")) != "victor_ai_bot.runtime_legacy"
        ):
            rows = runtime._pending_state_for_opp(opp)
            if isinstance(rows, list):
                return rows[:8]
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    try:
        ctx = build_pending_state_context(runtime=runtime, opp=opp, existing=[])
        return list(ctx.get("rows") or [])[:8]
    except (AttributeError, KeyError, TypeError, ValueError):
        return []


def pending_state_context_for_opp(runtime: Any, opp: Any) -> Dict[str, Any]:
    try:
        if (
            hasattr(runtime, "_pending_state_context_for_opp")
            and str(getattr(runtime.__class__, "__module__", "")) != "victor_ai_bot.runtime_legacy"
        ):
            ctx = runtime._pending_state_context_for_opp(opp)
            if isinstance(ctx, dict):
                return ctx
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    try:
        existing = pending_state_for_opp(runtime, opp)
        return build_pending_state_context(runtime=runtime, opp=opp, existing=existing)
    except (AttributeError, KeyError, TypeError, ValueError):
        return {"rows": pending_state_for_opp(runtime, opp), "summary": {"count": 0, "sources": []}}


def build_pending_state_snapshot(runtime: Any, opp: Any) -> PendingStateSnapshot:
    rows = pending_state_for_opp(runtime, opp)
    context = pending_state_context_for_opp(runtime, opp)
    if not isinstance(context, dict):
        context = {}
    if "rows" not in context:
        context = {**context, "rows": list(rows)}
    return PendingStateSnapshot(rows=list(rows), context=dict(context))


def build_runtime_decision_context(runtime: Any) -> RuntimeDecisionContext:
    wealth_goal: Dict[str, Any] = {}
    drawdown_state: Dict[str, Any] = {}
    kill_switch_state: Dict[str, Any] = {}
    treasury_state: Dict[str, Any] = {}
    try:
        if getattr(runtime, "_wealth_goal_service", None) is not None:
            wealth_goal = runtime._wealth_goal_service.state(runtime)
    except (AttributeError, KeyError, TypeError, ValueError):
        wealth_goal = {}
    try:
        drawdown_state = runtime.drawdown_state() if hasattr(runtime, "drawdown_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        drawdown_state = {}
    try:
        kill_switch_state = (
            runtime.kill_switch_state() if hasattr(runtime, "kill_switch_state") else {}
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        kill_switch_state = {}
    try:
        treasury_state = (
            runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        treasury_state = {}
    return RuntimeDecisionContext(
        wealth_goal=dict(wealth_goal or {}),
        drawdown_state=dict(drawdown_state or {}),
        kill_switch_state=dict(kill_switch_state or {}),
        treasury_state=dict(treasury_state or {}),
    )


def build_admission_context(
    runtime: Any, opp: Any, *, snapshot: RuntimeAccessSnapshot | None = None
) -> AdmissionContext:
    pending = build_pending_state_snapshot(runtime, opp)
    snap = snapshot or build_runtime_access_snapshot(runtime)
    decision = build_runtime_decision_context_from_snapshot(snap)
    return AdmissionContext(
        chain_id=int(snap.chain_id or 0),
        regime=str(snap.regime or "balanced"),
        public_mode=bool(snap.public_mode),
        force_send_mode=str(snap.force_send_mode or ""),
        pending=pending,
        decision=decision,
    )


def build_wealth_goal_signals(runtime: Any) -> WealthGoalSignals:
    fs = {}
    drawdown = {}
    kill_switch = {}
    capital = {}
    live = {}
    endpoint_quality = {}
    try:
        fs = runtime.fund_summary_state() if hasattr(runtime, "fund_summary_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        fs = {}
    try:
        drawdown = runtime.drawdown_state() if hasattr(runtime, "drawdown_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        drawdown = {}
    try:
        kill_switch = runtime.kill_switch_state() if hasattr(runtime, "kill_switch_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        kill_switch = {}
    try:
        capital = runtime.capital_engine_state() if hasattr(runtime, "capital_engine_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        capital = {}
    try:
        live = runtime.execution_live_state() if hasattr(runtime, "execution_live_state") else {}
    except (AttributeError, KeyError, TypeError, ValueError):
        live = {}
    try:
        endpoint_quality = (
            runtime.endpoint_quality_state() if hasattr(runtime, "endpoint_quality_state") else {}
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        endpoint_quality = {}

    health = _safe_dict((_safe_dict(fs).get("health") or fs))
    risk_score = float(health.get("riskScore") or 0.0)
    false_adm = float(health.get("falseAdmissionRate") or 0.0)
    false_drop = float(health.get("falseDropRate") or 0.0)
    fund_stage = str(health.get("fundStage") or health.get("fund_stage") or "unknown")
    risk_posture = str(health.get("riskPosture") or health.get("risk_posture") or "balanced")
    current_return_pct = 0.0
    try:
        snap = getattr(runtime, "_treasury", None)
        snap = snap.snapshot() if snap is not None and hasattr(snap, "snapshot") else {}
        ag = _safe_dict(_safe_dict(snap).get("aggressiveness"))
        current_return_pct = float(ag.get("current_return_pct") or 0.0)
    except (AttributeError, KeyError, TypeError, ValueError):
        current_return_pct = 0.0
    drawdown_pct = float(_safe_dict(drawdown).get("drawdownPct") or 0.0)
    hard_stop = bool(_safe_dict(_safe_dict(drawdown).get("hardStop")).get("active"))
    kill_active = bool(_safe_dict(kill_switch).get("suppressions"))

    capital_base_usd = 1000.0
    try:
        eff = _safe_dict(_safe_dict(capital).get("capital_efficiency_metrics"))
        deployed = float(eff.get("deployedCapitalWei") or 0.0)
        est = float(eff.get("estimatedCapitalWei") or 0.0)
        raw = max(deployed, est)
        capital_base_usd = raw / 1e18 if raw > 1e12 else max(raw, 1000.0)
    except (AttributeError, KeyError, TypeError, ValueError):
        pass

    stability = 0.75
    stability -= min(0.25, false_adm * 0.20)
    stability -= min(0.20, false_drop * 0.20)
    stability -= min(0.20, risk_score * 0.15)
    stability -= min(0.25, drawdown_pct / 20.0)
    stability = max(0.05, min(1.0, stability))

    realism = 0.70
    try:
        lanes = _safe_dict(endpoint_quality).get("lanes") or {}
        top_scores: List[float] = []
        for bucket in lanes.values():
            if not isinstance(bucket, dict):
                continue
            items = list(bucket.get("endpoints") or []) + list(bucket.get("relays") or [])
            for item in items[:2]:
                if isinstance(item, dict):
                    top_scores.append(float(item.get("score") or item.get("quality") or 0.0))
        if top_scores:
            realism = 0.45 * realism + 0.55 * max(0.05, min(1.0, sum(top_scores) / len(top_scores)))
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    try:
        items = list(_safe_dict(live).get("items") or [])[:8]
        if items:
            frag = 0.0
            exe = 0.0
            for item in items:
                if not isinstance(item, dict):
                    continue
                exe += 1.0 if bool(item.get("routeExecutable", True)) else 0.0
                adv = _safe_dict(item.get("adversarial"))
                frag += (
                    float(adv.get("staleProbability") or 0.0) * 0.5
                    + float(adv.get("interferenceProbability") or 0.0) * 0.5
                )
            exe /= max(1, len(items))
            frag /= max(1, len(items))
            realism = 0.50 * realism + 0.50 * max(0.05, min(1.0, exe * (1.0 - frag)))
    except (AttributeError, KeyError, TypeError, ValueError):
        pass

    return WealthGoalSignals(
        current_return_pct=round(current_return_pct, 6),
        fund_stage=fund_stage,
        drawdown_pct=round(drawdown_pct, 6),
        risk_posture=risk_posture,
        hard_stop=hard_stop,
        kill_switch=kill_active,
        capital_base_usd=round(capital_base_usd, 6),
        stability_score=round(stability, 6),
        execution_realism_score=round(realism, 6),
        risk_score=round(risk_score, 6),
        false_admission_rate=round(false_adm, 6),
        false_drop_rate=round(false_drop, 6),
    )


@dataclass(frozen=True)
class ExecutionRuntimeSignals:
    base_borrow_amount: int
    gas_mode: str
    send_mode: str
    route_amount_candidates: List[int]
    controls: Any


def build_execution_runtime_signals(runtime: Any) -> ExecutionRuntimeSignals:
    cfg_exec = getattr(getattr(runtime, "cfg", None), "execution", None)
    base = int(getattr(cfg_exec, "base_borrow_amount", "0") or "0")
    gas_mode = str(getattr(cfg_exec, "gas_mode", "standard") or "standard")
    send_mode = str(getattr(cfg_exec, "send_mode", "public") or "public")
    chain = getattr(getattr(runtime, "cfg", None), "chain", None)
    candidates: List[int] = []
    for collection_name in ("v3_pairs", "curve_pools", "balancer_pools"):
        collection = list(getattr(chain, collection_name, []) or [])
        for row in collection[:24]:
            if not isinstance(row, dict):
                continue
            try:
                amount_in = int(row.get("amount_in", 0) or 0)
            except (TypeError, ValueError):
                amount_in = 0
            if amount_in > 0:
                candidates.append(amount_in)
    controls = getattr(getattr(runtime, "_cc", None), "controls", None)
    return ExecutionRuntimeSignals(
        base_borrow_amount=base,
        gas_mode=gas_mode,
        send_mode=send_mode,
        route_amount_candidates=candidates,
        controls=controls,
    )
