from __future__ import annotations

from typing import Any, Dict


class RuntimeTickScanFacade:
    """Own the main scan-time orchestration for a single tick.

    This facade intentionally keeps the per-tick process-boundary broad catch in
    runtime_legacy._loop. The facade only sequences the existing scan/overlay/
    decision helpers so the legacy loop no longer owns that orchestration.
    """

    def _mev_snapshot(self, fallback: Dict[str, Any]) -> Dict[str, Any]:
        """Return the current MEV observation without creating a new authority."""
        mev_runtime = getattr(self, "_mev", None)
        if mev_runtime is None or not hasattr(mev_runtime, "state"):
            return dict(fallback)
        try:
            raw_mev_snap = mev_runtime.state()
        except (AttributeError, KeyError, TypeError, ValueError):
            return dict(fallback)
        return dict(raw_mev_snap) if isinstance(raw_mev_snap, dict) else dict(fallback)

    def _merge_admitted_mev_opportunities(self, opps: list[Any]) -> None:
        """Append only already-admitted, validated MEV flash-arb opportunities."""
        engine_service = getattr(self, "_engine_service", None)
        if engine_service is None or not hasattr(engine_service, "flash_arb_opportunities"):
            return
        try:
            existing_ids = {str(getattr(opp, "id", "") or "") for opp in opps}
            candidates = list(engine_service.flash_arb_opportunities() or [])
        except (AttributeError, KeyError, TypeError, ValueError):
            return
        for mev_opp in candidates:
            mev_id = str(getattr(mev_opp, "id", "") or "")
            if mev_id and mev_id not in existing_ids:
                opps.append(mev_opp)
                existing_ids.add(mev_id)

    async def _run_tick_scan_pipeline(
        self,
        *,
        rpc: Any,
        current_block: int,
        loop_started_at: float,
    ) -> Dict[str, Any]:
        opps = []
        regime_label = "balanced"
        treasury_state = None
        mev_snap: Dict[str, Any] = {}

        amount_in = self._resolve_amount_in()
        opps = await self._scan_primary_opportunities(
            rpc,
            current_block=int(current_block),
            amount_in=int(amount_in),
        )

        gas_signals = await self._gas_signal_snapshot(rpc)
        basefee_gwei = float(gas_signals.get("basefee_gwei", 0.0) or 0.0)
        prio_gwei = float(gas_signals.get("priority_gwei", 0.0) or 0.0)

        market_signals = self._market_signal_snapshot(opps)
        mev_risk = float(market_signals.get("mev_risk", 0.0) or 0.0)
        pending_rate = float(market_signals.get("pending_rate", 0.0) or 0.0)
        avg_mr = float(market_signals.get("avg_margin_ratio", 0.0) or 0.0)
        vol_proxy = float(market_signals.get("volatility_proxy", 0.0) or 0.0)

        behave_state = self._behave_regime_state(
            basefee_gwei=float(basefee_gwei),
            priority_gwei=float(prio_gwei),
            pending_rate=float(pending_rate),
            mev_risk=float(mev_risk),
            avg_margin_ratio=float(avg_mr),
            volatility_proxy=float(vol_proxy),
            opp_count=int(len(opps)),
            current_block=int(current_block),
        )

        regime_label = str((behave_state or {}).get("regime_label") or "unknown")

        market_regime_state = self._resolve_market_regime(
            regime_label=str(regime_label),
            avg_margin_ratio=float(avg_mr),
            volatility_proxy=float(vol_proxy),
            basefee_gwei=float(basefee_gwei),
            opportunity_rate=float(len(opps)),
            pending_rate=float(pending_rate),
            mev_risk=float(mev_risk),
        )
        regime_label = str(market_regime_state.get("regime_label") or regime_label or "unknown")

        treasury_guidance = self._apply_treasury_guidance(
            behave_state=behave_state,
            regime_label=str(regime_label),
            opps=opps,
            current_block=int(current_block),
        )
        treasury_state = treasury_guidance.get("treasury_state")
        behave_state = treasury_guidance.get("behave_state")

        predecision_state = self._run_predecision_additive_state(
            opps=opps,
            regime_label=str(regime_label),
            behave_state=behave_state,
            treasury_state=dict(treasury_state or {}),
            basefee_gwei=float(basefee_gwei),
            priority_gwei=float(prio_gwei),
            mev_risk=float(mev_risk),
            pending_rate=float(pending_rate),
            current_block=int(current_block),
        )
        mev_snap = self._mev_snapshot(dict(predecision_state.get("mev_snap") or {}))

        # Engine admission remains the prerequisite. This inserts only validated
        # MEV flash-arb opportunities before the existing canonical decision path.
        self._scan_engine_opportunities(
            regime_label=str(regime_label or "balanced"),
            mev_state=dict(mev_snap or {}),
            base_opportunities=list(opps or []),
            treasury_state=dict(treasury_state or {}),
        )
        self._merge_admitted_mev_opportunities(opps)
        await self._safe_annotate_can_execute(rpc, opps)

        decision = await self._run_decision_finalize(
            opps=opps,
            rpc=rpc,
            regime_label=str(regime_label),
            treasury_state=dict(treasury_state or {}),
            current_block=int(current_block),
            loop_started_at=loop_started_at,
        )

        return {
            "opps": list(opps or []),
            "regime_label": str(regime_label or "balanced"),
            "treasury_state": dict(treasury_state or {}),
            "mev_snap": dict(mev_snap or {}),
            "decision": decision,
        }
