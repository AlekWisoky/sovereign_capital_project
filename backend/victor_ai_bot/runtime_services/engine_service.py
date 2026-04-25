from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, Iterable, List

from victor_ai_bot.aqe.arbitrage.cross_cex_dex_engine import CrossCEXDEXArbitrageEngine
from victor_ai_bot.aqe.cross_chain import CrossChainArbitrageEngine
from victor_ai_bot.aqe.funding import FundingArbStrategy, FundingArbConfig
from victor_ai_bot.aqe.mev.search_engine import MEVSearchEngine
from victor_ai_bot.aqe.meta.predictor import predict_candidate_success
from victor_ai_bot.engine_control import (
    EngineAdmissionGovernor,
    apply_engine_budgets,
    apply_interference_controls,
    default_engine_capability_registry,
)
from victor_ai_bot.engine_control.models import EngineOpportunity
from victor_ai_bot.telemetry.engine_metrics import EngineMetrics
from victor_ai_bot.treasury.engine_capital_policy import engine_capital_limits


class EngineService:
    def __init__(self, *, capture_engine: Any | None = None, telemetry_service: Any | None = None):
        self.capture_engine = capture_engine
        self.telemetry_service = telemetry_service
        self.registry = default_engine_capability_registry()
        self.governor = EngineAdmissionGovernor(self.registry)
        self.metrics = EngineMetrics()
        self.cross_cex_dex = CrossCEXDEXArbitrageEngine()
        self.funding = FundingArbStrategy(
            cfg=FundingArbConfig(enabled=True, min_rate_diff=0.00005, max_positions=6)
        )
        self.cross_chain = CrossChainArbitrageEngine()
        self.mev = MEVSearchEngine()
        self._last: Dict[str, Any] = {"items": []}

    def _telemetry_points(self, engine_type: str) -> int:
        if self.telemetry_service is None:
            return 0
        rows = self.telemetry_service.store.filter(event_type="engine_outcome", limit=2000)
        return sum(
            1
            for row in rows
            if str((row.get("payload") or {}).get("engine_type") or "") == str(engine_type)
        )

    def _calibration_points(self, engine_type: str) -> int:
        if self.telemetry_service is None:
            return 0
        rows = self.telemetry_service.store.filter(event_type="engine_decision", limit=2000)
        return sum(
            1
            for row in rows
            if str((row.get("payload") or {}).get("engine_type") or "") == str(engine_type)
        )

    def _pseudo_opp(self, opportunity: EngineOpportunity) -> Any:
        legs = [
            SimpleNamespace(venue=v, token_in="USD", token_out="USD")
            for v in (opportunity.venues or ["unknown"])
        ]
        return SimpleNamespace(
            id=opportunity.opportunity_id,
            route_id=opportunity.opportunity_id,
            strategy=opportunity.strategy_family,
            expected_profit_usd=opportunity.expected_realized_profit_usd,
            meta={
                "route_family": opportunity.route_family,
                "p_success": opportunity.confidence,
                "freshness_score": max(0.15, 1.0 - opportunity.latency_sensitivity * 0.4),
                "liquidity_fragility": (
                    0.40 if "inventory_thin" in set(opportunity.risk_flags) else 0.18
                ),
                "slippage_sensitivity": 0.22 if opportunity.engine_type != "funding_arb" else 0.08,
                "private_send_preference": (
                    True if opportunity.engine_type in {"mev_search", "cross_chain_arb"} else False
                ),
                "venue_reliability_score": 0.70,
                "safety": {"exec_ready": opportunity.policy_eligibility in {"capped_live", "live"}},
                "unit_econ": {
                    "expected_profit_usd_micro": str(
                        int(max(0.0, opportunity.expected_profit_usd) * 1_000_000)
                    ),
                    "gas_cost_usd_micro": str(
                        int(max(0.0, opportunity.capital_required_usd * 0.002) * 1_000_000)
                    ),
                },
            },
            route=SimpleNamespace(legs=legs),
        )

    def scan(
        self,
        *,
        chain: str,
        chain_id: int,
        regime: str,
        quotes: List[Dict[str, Any]],
        funding_rows: List[Dict[str, Any]],
        dex_prices: Dict[str, float],
        dex_depths: Dict[str, float],
        venue_inventory: Dict[str, Dict[str, float]],
        bridge_spreads: List[Dict[str, Any]],
        bridge_quotes: Dict[str, Dict[str, Any]],
        chain_inventory: Dict[str, float],
        mev_state: Dict[str, Any],
        base_opportunities: List[Any],
        meta_candidates: List[Dict[str, Any]],
        treasury_state: Dict[str, Any] | None = None,
        public_mode: bool = False,
    ) -> Dict[str, Any]:
        treasury_state = dict(treasury_state or {})
        items: List[EngineOpportunity] = []
        items.extend(
            self.cross_cex_dex.scan(
                quotes=quotes,
                dex_prices=dex_prices,
                dex_depths=dex_depths,
                venue_inventory=venue_inventory,
                chain=chain,
                chain_id=chain_id,
                regime=regime,
            )
        )
        items.extend(
            self.funding.scan(
                funding_rows=funding_rows, chain=chain, chain_id=chain_id, regime=regime
            )
        )
        items.extend(
            self.cross_chain.scan(
                spreads=bridge_spreads,
                chain_inventory=chain_inventory,
                bridge_quotes=bridge_quotes,
                regime=regime,
            )
        )
        items.extend(
            self.mev.search(
                mev_state=mev_state,
                base_opportunities=base_opportunities,
                regime=regime,
                chain=chain,
                chain_id=chain_id,
            )
        )
        for row in list(meta_candidates or [])[:5]:
            pred = predict_candidate_success(
                candidate=row, memory_rows=list(meta_candidates or []), regime=regime
            )
            items.append(
                EngineOpportunity(
                    opportunity_id=f"auto-strategy:{row.get('id')}",
                    engine_type="auto_strategy_generator",
                    strategy_family=str(row.get("strategy_family") or "auto_generated_strategy"),
                    route_family=f"auto_strategy_generator|{row.get('strategy_family') or 'generated'}",
                    chain=chain,
                    chain_id=chain_id,
                    expected_profit_usd=float(max(0.0, float(row.get("score") or 0.0))),
                    expected_realized_profit_usd=float(max(0.0, float(row.get("score") or 0.0)))
                    * float(pred.get("predicted_success") or 0.0),
                    capital_required_usd=25.0,
                    inventory_requirements={},
                    confidence=float(pred.get("predicted_success") or 0.0),
                    regime=regime,
                    latency_sensitivity=0.10,
                    risk_flags=["generated_strategy"],
                    lifecycle_eligibility="sandbox",
                    policy_eligibility="observe_only",
                    venues=[],
                    metadata={
                        "candidate_id": row.get("id"),
                        "prediction": pred,
                        "lifecycle_stage": row.get("lifecycle_stage"),
                    },
                )
            )
        items = apply_engine_budgets(items)
        items = apply_interference_controls(items)
        entries: List[Dict[str, Any]] = []
        for opp in items:
            tel_pts = self._telemetry_points(opp.engine_type)
            cal_pts = self._calibration_points(opp.engine_type)
            admission = self.governor.decide(
                opportunity=opp,
                env_mode="live" if not public_mode else "paper",
                telemetry_points=tel_pts,
                calibration_points=cal_pts,
                treasury_state=treasury_state,
            )
            capture = None
            if admission.allowed and self.capture_engine is not None:
                try:
                    capture = self.capture_engine.evaluate(
                        self._pseudo_opp(opp),
                        chain_id=chain_id,
                        regime=regime,
                        public_mode=public_mode,
                        force_send_mode="PRIVATE" if opp.engine_type == "mev_search" else "",
                    )
                except (AttributeError, KeyError, TypeError, ValueError):
                    capture = None
            entry = {
                "opportunity": opp.to_dict(),
                "admission": admission.to_dict(),
                "capital_limits": engine_capital_limits(
                    engine_type=opp.engine_type, treasury_state=treasury_state
                ),
                "capture": capture.to_dict() if capture is not None else None,
            }
            entries.append(entry)
            if self.telemetry_service is not None:
                self.telemetry_service.record(
                    "engine_decision",
                    {
                        "engine_type": opp.engine_type,
                        "route_family": opp.route_family,
                        "strategy_family": opp.strategy_family,
                        "regime": regime,
                        "projected_realized_edge_usd": float(opp.expected_realized_profit_usd),
                        "actual_realized_edge_usd": 0.0,
                        "lane": str(((capture or {}).lane.value) if capture is not None else ""),
                        "mode": str(admission.mode),
                    },
                    chain=chain,
                )
        self._last = {
            "items": entries,
            "capabilities": self.registry.snapshot(),
            "summary": self.metrics.summarize(
                self.telemetry_service.store.filter(limit=500, event_type="engine_outcome")
                if self.telemetry_service is not None
                else []
            ),
        }
        return self._last

    def state(self) -> Dict[str, Any]:
        return dict(self._last or {"items": []})
