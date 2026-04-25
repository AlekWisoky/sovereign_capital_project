from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.runtime_services.capital_explanation_service import CapitalExplanationService
from victor_ai_bot.runtime_services.runtime_context import (
    PendingStateSnapshot,
    RuntimeDecisionContext,
    build_admission_context,
    build_runtime_decision_context,
)


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(chain_id=1, name='ethereum'),
            execution=SimpleNamespace(base_borrow_amount='0', gas_mode='fast', send_mode='private'),
        )
        self._market_regime = {'regime': 'balanced'}
        self._cc = SimpleNamespace(controls=SimpleNamespace(force_send_mode='private'))
        self._wealth_goal_service = SimpleNamespace(state=lambda runtime: {'state': {'aggressivenessCap': 0.9}})
        self._opps = []

    def drawdown_state(self):
        return {'drawdownPct': 1.0, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def capital_engine_state(self):
        return {'capital_engine': {'family_targets': {'flashloan_atomic': 0.4}}}

    def execution_live_state(self):
        return {'items': []}

    def wealth_goal_state(self):
        return {'state': {'goalStatus': 'active', 'aggressivenessCap': 0.9}, 'explanation': {'why_posture': 'steady'}}


class _Opp:
    def __init__(self):
        self.meta = {'pending_transactions': [{'hash': '0x1', 'gasPrice': 1, 'tokenIn': 'a', 'tokenOut': 'b', 'venues': ['uni']}], 'capture': {'expected_realized_value': 12.5, 'lane': 'PRIVATE', 'metadata': {'envelope': {'route_family': 'flashloan_atomic', 'safe_size_curve': [{'size_mult': 1.0, 'expected_profit_usd': 12.0}]}, 'route_plan': {'selected_venues': ['uni'], 'fallback_tree': []}, 'execution_route_plan': {'selected_venues': ['uni'], 'executable': True}, 'endpoint_selection': {'endpoint': 'rpc-fast', 'reason': 'quality_ranked'}, 'adversarial_state': {'stale_probability': 0.1, 'interference_probability': 0.05, 'post_ordering_realized_edge': 11.0}, 'flashloan_resilience': {'selected_provider': 'aave', 'sizing': {'borrow_mult': 1.2, 'provider_choice_reason': 'depth_ok'}}, 'pipeline_latency_ms': 120}}}
        self.route_id = 'r1'


def _broad_count(path: str) -> int:
    tree = ast.parse((Path(__file__).resolve().parents[1] / path).read_text(encoding='utf-8'))
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == 'Exception'):
                total += 1
    return total


def test_runtime_context_uses_typed_snapshots():
    rt = _Runtime()
    ctx = build_admission_context(rt, _Opp())
    assert isinstance(ctx.pending, PendingStateSnapshot)
    assert isinstance(ctx.decision, RuntimeDecisionContext)
    assert ctx.pending.summary['count'] >= 0
    assert ctx.decision.treasury_state['capital_engine']['family_targets']['flashloan_atomic'] == 0.4


def test_capital_explanation_uses_canonical_context():
    rt = _Runtime()
    opp = _Opp()
    rt._opps = [opp]
    out = CapitalExplanationService().explain(rt)
    assert out['ok'] is True
    assert 'Why this route:' in out['text']
    assert out['facts']['wealthGoalAggressivenessCap'] == 0.9


def test_broad_exception_counts_reduced_in_legacy_hotspots():
    assert _broad_count('victor_ai_bot/api_legacy.py') == 0
    assert _broad_count('victor_ai_bot/runtime_legacy.py') < 180


def test_capital_explanation_blocks_degraded_route_runtime():
    rt = _Runtime()
    opp = _Opp()
    opp.meta['capture']['metadata']['execution_route_runtime'] = {
        'degraded': True,
        'reason_codes': ['execution_route_runtime_degraded'],
    }
    rt._opps = [opp]
    out = CapitalExplanationService().explain(rt)
    assert out['ok'] is True
    assert out['facts']['routeExecutable'] is False
    assert out['facts']['routeRuntimeDegraded'] is True
    assert 'execution route is refreshed' in out['causal']['whyNow']
    assert out['causal']['routeRuntimeReasonCodes'] == ['execution_route_runtime_degraded']
    assert out['causal']['whyNot'][0]['candidate'] == 'no_trade'
