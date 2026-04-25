from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.runtime_services.admission_service import AdmissionService
from victor_ai_bot.runtime_services.runtime_context import (
    RuntimeAccessSnapshot,
    build_admission_context,
    build_runtime_access_snapshot,
)
from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService


class _Decision:
    action = 'trade'
    expected_realized_value = 12.5
    lane = SimpleNamespace(value='PRIVATE')
    metadata = {'envelope': {'route_family': 'flashloan_atomic'}}

    def to_dict(self):
        return {
            'lane': 'PRIVATE',
            'expected_realized_value': 12.5,
            'metadata': {'envelope': {'route_family': 'flashloan_atomic'}},
        }


class _CaptureEngine:
    def evaluate(self, opp, *, chain_id, regime, public_mode, force_send_mode):
        assert chain_id == 1
        assert regime == 'balanced'
        return _Decision()


class _Runtime:
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(chain_id=1, name='ethereum'))
        self._market_regime = {'regime': 'balanced'}
        self._cc = SimpleNamespace(controls=SimpleNamespace(force_send_mode='private'))
        self._capture_engine = _CaptureEngine()
        self._wealth_goal_service = SimpleNamespace(state=lambda runtime: {'state': {'aggressivenessCap': 0.9}})

    def drawdown_state(self):
        return {'drawdownPct': 1.0, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def capital_engine_state(self):
        return {'capital_engine': {'family_targets': {'flashloan_atomic': 0.4}}}


class _Opp:
    def __init__(self):
        self.meta = {}
        self.route_id = 'r1'


def _broad_count(path: str) -> int:
    tree = ast.parse((Path(__file__).resolve().parents[1] / path).read_text(encoding='utf-8'))
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == 'Exception'):
                total += 1
    return total


def test_runtime_access_snapshot_is_explicit_and_reusable():
    rt = _Runtime()
    snapshot = build_runtime_access_snapshot(rt)
    assert isinstance(snapshot, RuntimeAccessSnapshot)
    assert snapshot.chain_id == 1
    assert snapshot.force_send_mode == 'private'
    assert snapshot.treasury_state['capital_engine']['family_targets']['flashloan_atomic'] == 0.4


def test_admission_service_accepts_explicit_context_snapshot():
    rt = _Runtime()
    opp = _Opp()
    snapshot = build_runtime_access_snapshot(rt)
    ctx = build_admission_context(rt, opp, snapshot=snapshot)
    prepared = AdmissionService().prepare_capture(rt, opp, context=ctx)
    assert prepared.route_family == 'flashloan_atomic'
    assert prepared.metadata['admission_context'].force_send_mode == 'private'
    assert prepared.opportunity.meta['execution_lane'] == 'PRIVATE'


def test_state_summary_service_safe_defaults_for_capital_and_launch():
    runtime = SimpleNamespace(_treasury=None, _launch_service=None)
    svc = StateSummaryService()
    assert svc.launch(runtime)['reason_code'] == 'launch_service_unavailable'
    assert svc.launch(runtime)['status'] == 'unavailable'
    assert svc.capital_engine(runtime)['capital_engine'] == {}


def test_broad_exception_counts_continue_downward_in_legacy_hotspots():
    assert _broad_count('victor_ai_bot/runtime_legacy.py') < 150
    assert _broad_count('victor_ai_bot/api_legacy.py') == 0
