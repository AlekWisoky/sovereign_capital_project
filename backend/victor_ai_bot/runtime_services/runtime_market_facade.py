from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from .treasury_governance_truth import treasury_governance_view

from ..caq_kds.bus import BUS
from ..models import Opportunity
from ..regime_engine import classify_market
from .admission_service import AdmissionPreparationError
from .runtime_context import (
    build_admission_context,
    build_runtime_access_snapshot,
    pending_state_for_opp as service_pending_state_for_opp,
    pending_state_context_for_opp as service_pending_state_context_for_opp,
)

_SAFE_MARKET_EXCEPTIONS = (
    AttributeError,
    KeyError,
    RuntimeError,
    TypeError,
    ValueError,
)

_SAFE_BEHAVE_EXCEPTIONS = _SAFE_MARKET_EXCEPTIONS + (OSError,)


class RuntimeMarketFacade:
    """Market/context/capture compatibility facade.

    This isolates non-hot-path regime, pending-state, and capture-annotation
    helpers away from RuntimeBundle's orchestration monolith while preserving
    the existing method surface used by the loop and additive runtimes.
    """

    async def _gas_signal_snapshot(self, rpc: Any) -> Dict[str, float]:
        """Best-effort gas/blockspace signal snapshot with breaker side effects."""
        try:
            control = getattr(self, "_runtime_control_service", None)
            batch_ok = (
                bool(control.rpc_batch_enabled(self))
                if control is not None and hasattr(control, "rpc_batch_enabled")
                else False
            )

            tip_wei = 0
            gp_wei = 0
            if batch_ok:
                try:
                    rs = await rpc.batch(
                        [
                            ("eth_feeHistory", ["0x5", "latest", [50]]),
                            ("eth_gasPrice", []),
                        ]
                    )
                    if len(rs) >= 1 and rs[0].ok and isinstance(rs[0].result, dict):
                        rewards = rs[0].result.get("reward")
                        if (
                            rewards
                            and isinstance(rewards, list)
                            and rewards[-1]
                            and isinstance(rewards[-1], list)
                        ):
                            tip_hex = rewards[-1][0]
                            if isinstance(tip_hex, str):
                                tip_wei = int(tip_hex, 16)
                    if len(rs) >= 2 and rs[1].ok and isinstance(rs[1].result, str):
                        gp_wei = int(rs[1].result, 16)
                except _SAFE_BEHAVE_EXCEPTIONS:
                    tip_wei = 0
                    gp_wei = 0
            if not batch_ok:
                tip_wei = await rpc.fee_history_tip() or 0
                gp_wei = await rpc.gas_price() or 0
            basefee_wei = max(0, int(gp_wei) - int(tip_wei))
            basefee_gwei = float(basefee_wei) / 1e9
            priority_gwei = float(tip_wei) / 1e9
        except _SAFE_BEHAVE_EXCEPTIONS:
            basefee_gwei = 0.0
            priority_gwei = 0.0

        try:
            gas_spike = self._anomaly.observe_gas(basefee_gwei=float(basefee_gwei))
            if gas_spike and getattr(self, "_cc", None) is not None:
                controls = getattr(self._cc, "controls", None)
                if controls is not None and bool(getattr(controls, "chaos_breakers_enabled", True)):
                    setattr(controls, "defensive_mode", True)
                    setattr(controls, "reduce_exposure_half", True)
                    try:
                        self._cc.persist_controls()
                        self._cc.audit.append(
                            "breaker_trip",
                            {"kind": "gas_spike", "basefee_gwei": float(basefee_gwei)},
                            actor="system",
                            reason="gas_spike",
                        )
                    except _SAFE_BEHAVE_EXCEPTIONS:
                        pass
        except (AttributeError, asyncio.QueueFull, RuntimeError, TypeError, ValueError):
            pass

        return {
            "basefee_gwei": float(basefee_gwei),
            "priority_gwei": float(priority_gwei),
        }

    def _route_fail_rate(self) -> float:
        """Best-effort recent failure rate (0..1)."""
        try:
            snap = self._eff.snapshot()
            sr = float(snap.get("success_rate_pct", 0.0) or 0.0) / 100.0
            return max(0.0, min(1.0, 1.0 - sr))
        except _SAFE_MARKET_EXCEPTIONS:
            return 0.0

    def _compute_market_regime(
        self,
        *,
        avg_margin_ratio: float,
        volatility_proxy: float,
        basefee_gwei: float,
        opportunity_rate: float,
        pending_rate: float,
        mev_risk: float,
    ) -> Dict[str, Any]:
        try:
            liquidity = max(
                0.05,
                min(
                    1.0,
                    1.0 - min(1.0, float(self._route_fail_rate()) * 0.6 + float(mev_risk) * 0.4),
                ),
            )
        except (RuntimeError, TypeError, ValueError):
            liquidity = max(0.05, min(1.0, 1.0 - float(mev_risk)))
        gas_norm = min(1.0, float(basefee_gwei) / 100.0)
        spreads = min(1.0, max(0.0, (0.5 - float(avg_margin_ratio)) + float(volatility_proxy)))
        trend = (float(opportunity_rate) - 1.0) * 0.25 - float(pending_rate) * 0.15
        market = classify_market(
            volatility=float(volatility_proxy),
            liquidity=float(liquidity),
            volume=min(1.0, float(opportunity_rate) / 3.0),
            gas=float(gas_norm),
            spreads=float(spreads),
            trend=float(trend),
        )
        self._market_regime = market.to_dict()
        return dict(self._market_regime)

    def _market_signal_snapshot(self, opps: List[Opportunity]) -> Dict[str, float]:
        """Best-effort market/regime prep signals for the current opportunity set."""
        try:
            bus_snap = BUS.snapshot()
        except _SAFE_MARKET_EXCEPTIONS:
            bus_snap = {}
        mev_snap = (bus_snap.get("mev") if isinstance(bus_snap, dict) else {}) or {}
        mev_risk = float(mev_snap.get("sandwich_risk", 0.0) or 0.0)
        pending_rate = float(mev_snap.get("pending_rate", 0.0) or 0.0)

        mrs: List[float] = []
        for opp in list(opps or [])[:200]:
            try:
                meta = getattr(opp, "meta", None)
                if isinstance(meta, dict):
                    margin_ratio = meta.get("margin_ratio")
                    if margin_ratio is not None:
                        mrs.append(float(margin_ratio))
            except _SAFE_MARKET_EXCEPTIONS:
                pass

        avg_margin_ratio = float(sum(mrs) / len(mrs)) if mrs else 0.0
        volatility_proxy = (
            float(min(1.0, (max(mrs) - min(mrs)) / max(1e-9, avg_margin_ratio)))
            if len(mrs) > 3
            else 0.0
        )
        return {
            "mev_risk": float(mev_risk),
            "pending_rate": float(pending_rate),
            "avg_margin_ratio": float(avg_margin_ratio),
            "volatility_proxy": float(volatility_proxy),
        }

    def _behave_regime_state(
        self,
        *,
        basefee_gwei: float,
        priority_gwei: float,
        pending_rate: float,
        mev_risk: float,
        avg_margin_ratio: float,
        volatility_proxy: float,
        opp_count: int,
        current_block: int,
    ) -> Dict[str, Any] | None:
        """Best-effort BehaveAgent regime analysis for the current tick."""
        behave_state = None
        try:
            if getattr(self, "_behave", None) is None:
                return None
            behave_state = self._behave.analyze_market(
                features={
                    "basefee_gwei": float(basefee_gwei),
                    "priority_gwei": float(priority_gwei),
                    "pending_rate": float(pending_rate),
                    "mev_risk": float(mev_risk),
                    "avg_margin_ratio": float(avg_margin_ratio),
                    "volatility_proxy": float(volatility_proxy),
                    "fail_streak": int(getattr(self._bankroll.state, "fail_streak", 0) or 0),
                    "route_fail_rate": float(self._route_fail_rate()),
                    "opp_count": int(opp_count),
                },
                seed=str(current_block),
            )
            try:
                drift = self._behave.monitor_risk(
                    features=dict((behave_state or {}).get("features") or {}),
                    seed=str(current_block),
                )
                if drift and bool(drift.get("drift")):
                    BUS.update("alerts", {"type": "regime_drift", "data": dict(drift)})
            except _SAFE_BEHAVE_EXCEPTIONS:
                pass
            BUS.update("behaveagent", dict(behave_state or {}))
            return dict(behave_state or {})
        except _SAFE_BEHAVE_EXCEPTIONS:
            return None

    def _behave_strategy_overlay(
        self,
        *,
        behave_state: Dict[str, Any] | None,
        treasury_state: Dict[str, Any] | None,
        opps: List[Opportunity],
        current_block: int,
    ) -> Dict[str, Any] | None:
        """Best-effort BehaveAgent strategy overlay under treasury guidance."""
        try:
            if not getattr(self, "_behave", None):
                return behave_state
            if not bool((behave_state or {}).get("enabled")):
                return behave_state
            governance = treasury_governance_view(dict(treasury_state or {}))
            aggressiveness = str(
                governance.get("effective_aggressiveness_level")
                or ((treasury_state or {}).get("aggressiveness") or {}).get("aggressiveness_level")
                or "LOW"
            )
            profit_goal = dict((treasury_state or {}).get("goal") or {})
            overlay = self._behave.select_strategy_overlay(
                opps=list(opps or []),
                profit_goal=profit_goal,
                aggressiveness=aggressiveness,
                seed=str(current_block),
            )
            if isinstance(overlay, dict) and overlay.get("ok"):
                merged_state = {**(behave_state or {}), **overlay}
                BUS.update("behaveagent", dict(merged_state))
                return merged_state
            return behave_state
        except _SAFE_BEHAVE_EXCEPTIONS:
            return behave_state

    def _resolve_market_regime(
        self,
        *,
        regime_label: str,
        avg_margin_ratio: float,
        volatility_proxy: float,
        basefee_gwei: float,
        opportunity_rate: float,
        pending_rate: float,
        mev_risk: float,
    ) -> Dict[str, Any]:
        """Best-effort fallback market-regime classification for the current tick."""
        try:
            market_regime = self._compute_market_regime(
                avg_margin_ratio=float(avg_margin_ratio),
                volatility_proxy=float(volatility_proxy),
                basefee_gwei=float(basefee_gwei),
                opportunity_rate=float(opportunity_rate),
                pending_rate=float(pending_rate),
                mev_risk=float(mev_risk),
            )
            resolved_label = str(regime_label or "unknown")
            if resolved_label == "unknown":
                resolved_label = str(market_regime.get("regime") or "balanced")
            return {
                "regime_label": resolved_label,
                "market_regime": dict(market_regime or {}),
            }
        except _SAFE_MARKET_EXCEPTIONS:
            return {
                "regime_label": str(regime_label or "unknown"),
                "market_regime": dict(getattr(self, "_market_regime", {}) or {}),
            }

    def _pending_state_for_opp(self, opp: Opportunity) -> List[Dict[str, Any]]:
        return service_pending_state_for_opp(self, opp)

    def _pending_state_context_for_opp(self, opp: Opportunity) -> Dict[str, Any]:
        return service_pending_state_context_for_opp(self, opp)

    def _annotate_execution_capture(self, opps: List[Opportunity], regime_label: str) -> None:
        if getattr(self, "_opportunity_service", None) is not None:
            try:
                self._opportunity_service.annotate(opps, regime=str(regime_label or "balanced"))
            except _SAFE_MARKET_EXCEPTIONS:
                pass
        if (
            getattr(self, "_capture_engine", None) is None
            or getattr(self, "_admission_service", None) is None
        ):
            return
        runtime_snapshot = build_runtime_access_snapshot(self)
        scored = []
        for o in list(opps or [])[:80]:
            try:
                admission_ctx = build_admission_context(self, o, snapshot=runtime_snapshot)
                prepared = self._admission_service.prepare_capture(self, o, context=admission_ctx)
                decision = prepared.capture_decision
                expected_value = (
                    float(getattr(decision, "expected_realized_value", 0.0) or 0.0)
                    if decision is not None
                    else 0.0
                )
                scored.append(
                    (expected_value, str(getattr(o, "route_id", "") or ""), prepared.opportunity)
                )
            except AdmissionPreparationError:
                scored.append((0.0, str(getattr(o, "route_id", "") or ""), o))
            except _SAFE_MARKET_EXCEPTIONS:
                scored.append((0.0, str(getattr(o, "route_id", "") or ""), o))
        scored.sort(key=lambda x: (-x[0], x[1]))
        ordered = [x[2] for x in scored] + [x for x in opps if x not in [y[2] for y in scored]]
        opps[:] = ordered
