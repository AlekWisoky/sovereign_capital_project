from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

from victor_ai_bot.command_center_overlay import CommandCenterOverlay
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService


class _Runtime:
    def __init__(self, overlay: CommandCenterOverlay):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(base_borrow_amount='0', gas_mode='fast', send_mode='private'),
            chain=SimpleNamespace(v3_pairs=[{'amount_in': '150'}], curve_pools=[], balancer_pools=[]),
            safety=SimpleNamespace(max_daily_loss_pct=3.0),
        )
        self.metrics = SimpleNamespace(
            exec_e2e_p50_ms=10,
            exec_e2e_p90_ms=20,
            exec_e2e_p99_ms=40,
            submit_to_receipt_p50_ms=30,
            submit_to_receipt_p90_ms=50,
            submit_to_receipt_p99_ms=90,
            loop_p50_ms=5,
            loop_p90_ms=10,
            loop_p99_ms=20,
            gas_mode='fast',
            send_mode='private',
        )
        self._cc = overlay
        self._execution_service = SimpleNamespace(
            build_live_state=lambda runtime: {
                'items': [
                    {'endpoint': 'rpc-fast', 'lane': 'PRIVATE', 'flashloan': {'selectedProvider': 'aave'}}
                ]
            }
        )
        self._telemetry_service = SimpleNamespace(
            service_health=lambda runtime: {
                'admission': {'ok': True},
                'execution': {'ok': True},
                'receipt': {'ok': True},
                'telemetry': {'ok': True},
            }
        )
        self._fund_service = SimpleNamespace(
            summary=lambda runtime: {
                'ok': True,
                'health': {'fundStage': 'staging', 'riskPosture': 'balanced', 'riskScore': 0.22},
            }
        )
        self._analytics_service = SimpleNamespace(system_summary=lambda runtime: {'ok': True, 'services': {}})
        self._capital_explanation_service = SimpleNamespace(
            explain=lambda runtime, snapshot=None: {'ok': True, 'text': 'ok', 'facts': {}, 'causal': {}}
        )
        self._endpoint_universe = SimpleNamespace(snapshot=lambda: {'private': {'candidates': [{'url': 'rpc-fast'}]}})
        self._route_quality = SimpleNamespace(snapshot=lambda: {'items': [{'quality': 0.9}]})
        self._drawdown_state = SimpleNamespace(snapshot=lambda: {'drawdownPct': 1.0, 'hardStop': {'active': False}})
        self._kill_switch = SimpleNamespace(snapshot=lambda: {'suppressions': {}})
        self._risk_memory = SimpleNamespace(snapshot=lambda: {'failures': {}})
        self._path_diversity = SimpleNamespace(snapshot=lambda: {'paths': []})
        self._edge_learning = SimpleNamespace(snapshot=lambda: {'items': []})
        self._rpc_preferences = SimpleNamespace(snapshot=lambda: {'configured': True, 'read': ['rpc-fast']})
        self._agent_attribution = SimpleNamespace(summary=lambda: {'agents': []})
        self._venue_scorecards = SimpleNamespace(snapshot=lambda: {'items': []})
        self._pending = {}
        self._auto_trading = True
        self._pnl = SimpleNamespace(summary=self._pnl_summary)

    async def _pnl_summary(self, window=50):
        return {'realized_profit_after_gas_usd_micro': '1000000', 'recent': []}

    async def snapshot(self):
        return {
            'metrics': {'auto_trading': True},
            'chain': 'ethereum',
            'rpc': {'error_rate': 0.0, 'read': [{'ok': True}], 'send': [{'ok': True}]},
            'opportunities': [],
        }

    def wealth_goal_state(self):
        return {
            'ok': True,
            'state': {
                'targetReturnPct': 8.0,
                'timeframeDays': 14,
                'riskTolerance': 'moderate',
                'progressPct': 55.0,
                'goalAchieved': False,
                'nextGoalAllowed': True,
                'pacing': 'steady',
                'aggressivenessCap': 0.9,
                'goalStatus': 'active',
                'goalUrgency': 'steady',
            },
            'explanation': {'why_posture': 'steady'},
        }


def test_command_center_overlay_defaults_when_controls_json_is_invalid(tmp_path):
    path = tmp_path / 'cc_controls_eth.json'
    path.write_text('{bad json', encoding='utf-8')
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')
    assert overlay.controls.paused is False
    assert overlay.controls.kelly_enabled is False
    state = overlay.state()
    assert state['controls']['load']['ok'] is False
    assert state['controls']['load']['reasonCode'] == 'controls_invalid_json'
    assert state['degraded'] is True


def test_command_center_overlay_reports_control_persist_failure(monkeypatch, tmp_path):
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')

    def _boom(src: str, dst: str) -> None:
        raise OSError('disk full')

    monkeypatch.setattr(os, 'replace', _boom)
    result = overlay.set_controls({'paused': True}, reason='maintenance')
    assert result['ok'] is False
    assert result['reason_code'] == 'controls_persist_failed'
    assert result['details']['storage']['controls']['persist']['ok'] is False
    assert result['details']['storage']['controls']['persist']['reasonCode'] == 'controls_persist_failed'
    assert result['details']['storage']['degraded'] is True
    assert overlay.controls.paused is False


def test_operator_summary_includes_command_center_storage_state(tmp_path):
    controls = tmp_path / 'cc_controls_eth.json'
    controls.write_text('{bad json', encoding='utf-8')
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')
    runtime = _Runtime(overlay)
    out = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    assert out['ok'] is True
    assert out['governance']['storage']['controls']['load']['reasonCode'] == 'controls_invalid_json'
    assert out['governance']['storage']['degraded'] is True


def test_command_center_overlay_rejects_unknown_control_fields(tmp_path):
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')

    result = overlay.set_controls({'unknown_flag': True}, reason='maintenance')

    assert result['ok'] is False
    assert result['reason_code'] == 'invalid_control_patch'
    assert result['details']['errors'][0]['field'] == 'unknown_flag'
    assert overlay.controls.paused is False


def test_command_center_overlay_rejects_invalid_bool_like_values(tmp_path):
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')

    result = overlay.set_controls({'paused': 'not-a-bool'}, reason='maintenance')

    assert result['ok'] is False
    assert result['reason_code'] == 'invalid_control_patch'
    assert result['details']['errors'][0]['reason_code'] == 'invalid_boolean_value'
    assert overlay.controls.paused is False


def test_command_center_overlay_accepts_canonical_boolean_strings(tmp_path):
    overlay = CommandCenterOverlay(data_dir=str(tmp_path), chain='eth')

    result = overlay.set_controls({'paused': 'true', 'sandbox_only': 'false'}, reason='maintenance')

    assert result['ok'] is True
    assert overlay.controls.paused is True
    assert overlay.controls.sandbox_only is False


