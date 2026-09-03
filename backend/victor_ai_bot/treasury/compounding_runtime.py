from __future__ import annotations

from typing import Any, Dict

from .capital_compounding import resolve_profit_promotion
from .runtime import TreasuryRuntime


class CompoundingTreasuryRuntime(TreasuryRuntime):
    """Treasury runtime with canonical profit-to-deployable compounding.

    The existing TreasuryRuntime remains the strategy/governance engine. This
    adapter makes the capital-engine snapshot the explicit authority for
    incremental promotion of settled Treasury-owned profit into the next
    deployable capital pool.
    """

    @staticmethod
    def _scale_capital_bucket(value: Any, ratio: float) -> int:
        try:
            return max(0, int(round(float(value or 0) * float(ratio))))
        except (TypeError, ValueError):
            return 0

    def _apply_profit_promotion(
        self,
        snapshot: Dict[str, Any],
        *,
        realized_profit_wei: int,
    ) -> Dict[str, Any]:
        out = dict(snapshot or {})
        engine = dict(out.get("capital_engine") or {})
        policy = dict(out.get("reinvestment_policy") or {})
        previous_engine = dict(self._last.get("capital_engine") or {})
        previous_promoted = int(previous_engine.get("promoted_profit_wei") or 0)

        # Bootstrap the authority contract from the canonical reinvestment
        # policy once. Thereafter the capital-engine fields are authoritative.
        if "profit_promotion_enabled" not in engine:
            engine["profit_promotion_enabled"] = bool(
                policy.get("reinvest_wei", 0) and policy.get("reinvest_pct", 0)
            )
        if "profit_promotion_rate_pct" not in engine:
            raw_rate = policy.get("reinvest_pct", 0.0)
            try:
                rate = float(raw_rate or 0.0)
            except (TypeError, ValueError):
                rate = 0.0
            engine["profit_promotion_rate_pct"] = rate * 100.0 if 0.0 <= rate <= 1.0 else rate

        promotion = resolve_profit_promotion(
            capital_engine=engine,
            realized_profit_wei=int(realized_profit_wei or 0),
            reinvestment_policy=policy,
            previous_promoted_profit_wei=previous_promoted,
        )

        delta = int(promotion["promoted_profit_delta_wei"] or 0)
        current_estimated = max(0, int(engine.get("estimated_capital_wei") or 0))
        if delta > 0:
            if current_estimated <= 0:
                current_estimated = max(
                    0,
                    int(engine.get("deployable_bankroll_wei") or 0)
                    + int(engine.get("reserve_bankroll_wei") or 0)
                    + int(engine.get("experimental_bankroll_wei") or 0)
                    + int(engine.get("drawdown_buffer_wei") or 0)
                    + int(engine.get("treasury_offramp_wei") or 0),
                )
            base_estimated = max(1, current_estimated)
            effective_estimated = current_estimated + delta
            ratio = float(effective_estimated) / float(base_estimated)
            for key in (
                "deployable_bankroll_wei",
                "reserve_bankroll_wei",
                "experimental_bankroll_wei",
                "drawdown_buffer_wei",
                "treasury_offramp_wei",
            ):
                if key in engine:
                    engine[key] = self._scale_capital_bucket(engine.get(key), ratio)
            family_allocations = dict(engine.get("family_allocations_wei") or {})
            if family_allocations:
                engine["family_allocations_wei"] = {
                    str(k): self._scale_capital_bucket(v, ratio)
                    for k, v in family_allocations.items()
                }
            engine["estimated_capital_wei"] = effective_estimated

        engine["promotable_profit_wei"] = int(promotion["eligible_profit_wei"] or 0)
        engine["promoted_profit_wei"] = int(promotion["promoted_profit_wei"] or 0)
        engine["promotion_delta_wei"] = delta
        engine["promotion_reason_code"] = str(promotion["reason_code"] or "")
        engine["promotion_authority"] = "capital_engine_state"
        engine["promotion_write_boundary"] = "canonical_capital_write_v1"
        out["capital_engine"] = engine
        out["capital_compounding"] = dict(promotion)
        return out

    def pre_select_strategy(
        self,
        *,
        bankroll_state: Dict[str, Any],
        volatility_regime: str = "unknown",
        persist: bool = True,
    ) -> Dict[str, Any]:
        snapshot = super().pre_select_strategy(
            bankroll_state=bankroll_state,
            volatility_regime=volatility_regime,
            persist=False,
        )
        promoted = self._apply_profit_promotion(
            snapshot,
            realized_profit_wei=int(bankroll_state.get("realized_profit_wei") or 0),
        )
        if persist:
            self._last = dict(promoted)
            self._save_last_state()
            self._record_state_snapshot(self._last)
            self._audit({"event": "capital_compounding", "data": promoted})
        return dict(promoted)
