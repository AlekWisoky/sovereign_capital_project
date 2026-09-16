from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, List

from victor_ai_bot.engine_control.models import EngineOpportunity

from .simulator import (
    ForkSimulationUnavailable,
    validate_deterministic_simulation_evidence,
)


class MEVSearchEngine:
    engine_type = 'mev_search'

    def __init__(self, *, fork_executor: Any | None = None):
        self._fork_executor = fork_executor

    def _simulation_boundary(self, *, evidence: Any, request: Any) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
        candidate_evidence = evidence
        if (not isinstance(candidate_evidence, Mapping) or not candidate_evidence) and isinstance(request, Mapping) and self._fork_executor is not None:
            try:
                candidate_evidence = self._fork_executor.simulate(
                    fork_url=request.get('fork_url'),
                    fork_block=request.get('fork_block'),
                    transaction=request.get('transaction'),
                    scenarios=request.get('scenarios'),
                )
            except (ForkSimulationUnavailable, TypeError, ValueError):
                return {'ok': False, 'reason_code': 'simulation_executor_unavailable'}, None
        gate = validate_deterministic_simulation_evidence(candidate_evidence)
        if not gate.get('ok'):
            return gate, None
        return gate, dict(candidate_evidence)

    @staticmethod
    def _simulation_economics(evidence: Mapping[str, Any] | None) -> tuple[float | None, str]:
        """Return only explicitly producer-supplied simulation economics."""
        if not isinstance(evidence, Mapping):
            return None, 'missing'
        economics = evidence.get('economics')
        if not isinstance(economics, Mapping):
            return None, 'missing'
        try:
            value = float(economics.get('expected_realized_profit_usd'))
        except (TypeError, ValueError, OverflowError):
            return None, 'invalid'
        if value <= 0.0:
            return None, 'non_positive'
        return value, 'simulation_evidence'

    def search(self, *, mev_state: Dict[str, Any], base_opportunities: List[Any], regime: str = 'balanced', chain: str = 'ethereum', chain_id: int = 1) -> List[EngineOpportunity]:
        pending = list(mev_state.get('sample_pending') or [])
        high_risk = float(mev_state.get('high_risk_ratio') or 0.0)
        out: List[EngineOpportunity] = []
        for tx in pending[:8]:
            tags = set(tx.get('tags') or [])
            if 'dex_like' not in tags and not str(tx.get('sel') or '').startswith('0x'):
                continue
            heuristic_expected = 4.0 + float(tx.get('value_wei') or 0) / 1e18 * 0.02
            heuristic_realized = heuristic_expected * max(0.25, 0.85 - high_risk * 0.35)
            risk_flags = ['private_send']
            conf = max(0.35, min(0.90, 0.58 + (0.15 if 'sandwich_risk' not in tags else -0.10)))
            simulation_gate, simulation_evidence = self._simulation_boundary(
                evidence=tx.get('simulation_evidence'),
                request=tx.get('simulation_request'),
            )
            simulated_profit, economics_source = self._simulation_economics(simulation_evidence)
            simulation_usable = bool(simulation_gate.get('ok')) and simulated_profit is not None
            metadata = {
                'tx_hash': tx.get('hash'),
                'candidate_type': 'backrun_or_protection',
                'economics_status': 'simulation_backed' if simulation_usable else 'heuristic_non_authoritative',
                'economics_source': economics_source,
                'heuristic_expected_profit_usd': round(heuristic_expected, 6),
                'heuristic_expected_realized_profit_usd': round(heuristic_realized, 6),
                'simulation_gate': simulation_gate,
            }
            flash_arb_context = tx.get('flash_arb_context')
            if isinstance(flash_arb_context, Mapping):
                metadata['flash_arb_context'] = dict(flash_arb_context)
            if simulation_evidence is not None:
                metadata['simulation_evidence'] = simulation_evidence
            out.append(EngineOpportunity(
                opportunity_id=f"mev:{tx.get('hash')}",
                engine_type=self.engine_type,
                strategy_family='mev_search',
                route_family=f"mev_search|backrun_protection|{tx.get('to')}",
                chain=chain,
                chain_id=int(chain_id),
                expected_profit_usd=round(simulated_profit, 6) if simulation_usable else 0.0,
                expected_realized_profit_usd=round(simulated_profit, 6) if simulation_usable else 0.0,
                capital_required_usd=25.0,
                inventory_requirements={},
                confidence=round(conf, 6),
                regime=str(regime),
                latency_sensitivity=0.95,
                risk_flags=risk_flags,
                lifecycle_eligibility='observe_only',
                policy_eligibility='observe_only',
                venues=['private_relay'],
                metadata=metadata,
            ))
        for base in list(base_opportunities or [])[:4]:
            meta = dict(getattr(base, 'meta', {}) or {}) if isinstance(getattr(base, 'meta', None), dict) else {}
            mev_risk = float((((meta.get('aqe') or {}) if isinstance(meta.get('aqe'), dict) else {}).get('mev_risk') or 0.0))
            if mev_risk < 0.55:
                continue
            heuristic_expected = float(getattr(base, 'expected_profit_usd', 0.0) or 0.0)
            if heuristic_expected > 1000:
                heuristic_expected /= 1_000_000.0
            heuristic_realized = heuristic_expected * max(0.25, 0.9 - mev_risk * 0.4)
            simulation_gate, simulation_evidence = self._simulation_boundary(
                evidence=meta.get('simulation_evidence'),
                request=meta.get('simulation_request'),
            )
            simulated_profit, economics_source = self._simulation_economics(simulation_evidence)
            simulation_usable = bool(simulation_gate.get('ok')) and simulated_profit is not None
            metadata = {
                'base_opportunity_id': getattr(base, 'id', ''),
                'candidate_type': 'route_protection',
                'economics_status': 'simulation_backed' if simulation_usable else 'heuristic_non_authoritative',
                'economics_source': economics_source,
                'heuristic_expected_profit_usd': round(heuristic_expected, 6),
                'heuristic_expected_realized_profit_usd': round(heuristic_realized, 6),
                'simulation_gate': simulation_gate,
            }
            flash_arb_context = meta.get('flash_arb_context')
            if isinstance(flash_arb_context, Mapping):
                metadata['flash_arb_context'] = dict(flash_arb_context)
            if simulation_evidence is not None:
                metadata['simulation_evidence'] = simulation_evidence
            out.append(EngineOpportunity(
                opportunity_id=f"mev-protect:{getattr(base, 'id', '')}",
                engine_type='mev_search',
                strategy_family='mev_search',
                route_family='mev_search|protect_existing_route',
                chain=chain,
                chain_id=int(chain_id),
                expected_profit_usd=round(simulated_profit, 6) if simulation_usable else 0.0,
                expected_realized_profit_usd=round(simulated_profit, 6) if simulation_usable else 0.0,
                capital_required_usd=50.0,
                inventory_requirements={},
                confidence=round(max(0.5, 0.82 - mev_risk * 0.2), 6),
                regime=str(regime),
                latency_sensitivity=0.98,
                risk_flags=['private_send'],
                lifecycle_eligibility='observe_only',
                policy_eligibility='observe_only',
                venues=['private_relay'],
                metadata=metadata,
            ))
        out.sort(key=lambda o: (-float(o.expected_realized_profit_usd), str(o.opportunity_id)))
        return out
