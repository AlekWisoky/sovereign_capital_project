from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict


def simulate_bundle(*, expected_profit_usd: float, gas_cost_usd: float, contention_risk: float) -> Dict[str, float | bool]:
    """Legacy planning estimate; never authoritative for MEV admission."""
    gas = float(gas_cost_usd)
    risk = max(0.0, min(1.0, float(contention_risk)))
    realized = max(0.0, float(expected_profit_usd) - gas - float(expected_profit_usd) * risk * 0.35)
    return {
        'ok': bool(realized > 0.0),
        'expected_realized_profit_usd': round(realized, 6),
        'contention_penalty_usd': round(float(expected_profit_usd) * risk * 0.35, 6),
    }


_REQUIRED_EVIDENCE_KEYS = (
    'simulation_id',
    'fork_block',
    'pre_state_root',
    'post_state_root',
    'scenario_digest',
    'scenario_results',
)
_REQUIRED_SCENARIO_KEYS = (
    'gas_multiplier',
    'liquidity_multiplier',
    'oracle_multiplier',
    'conflict_checked',
    'reverted',
)


def validate_deterministic_simulation_evidence(evidence: Any) -> Dict[str, Any]:
    """Validate producer-supplied fork evidence without inventing simulation truth.

    The validator is deliberately fail-closed. It proves that a candidate carries
    the minimum deterministic-evidence contract; it does not execute a fork and
    does not turn heuristic estimates into execution authority.
    """
    if not isinstance(evidence, Mapping):
        return {'ok': False, 'reason_code': 'simulation_evidence_missing'}

    missing = [key for key in _REQUIRED_EVIDENCE_KEYS if evidence.get(key) in (None, '')]
    if missing:
        return {'ok': False, 'reason_code': 'simulation_evidence_incomplete', 'missing': missing}
    if evidence.get('deterministic') is not True:
        return {'ok': False, 'reason_code': 'simulation_not_deterministic'}
    if evidence.get('reverted') is True:
        return {'ok': False, 'reason_code': 'simulation_reverted'}

    try:
        fork_block = int(evidence['fork_block'])
    except (TypeError, ValueError, OverflowError):
        return {'ok': False, 'reason_code': 'simulation_fork_block_invalid'}
    if fork_block < 0:
        return {'ok': False, 'reason_code': 'simulation_fork_block_invalid'}

    scenarios = evidence.get('scenario_results')
    if not isinstance(scenarios, list) or not scenarios:
        return {'ok': False, 'reason_code': 'simulation_scenarios_missing'}
    for index, scenario in enumerate(scenarios):
        if not isinstance(scenario, Mapping):
            return {'ok': False, 'reason_code': 'simulation_scenario_invalid', 'index': index}
        missing_scenario = [key for key in _REQUIRED_SCENARIO_KEYS if key not in scenario]
        if missing_scenario:
            return {
                'ok': False,
                'reason_code': 'simulation_scenario_incomplete',
                'index': index,
                'missing': missing_scenario,
            }
        if scenario.get('conflict_checked') is not True or scenario.get('reverted') is True:
            return {'ok': False, 'reason_code': 'simulation_scenario_failed', 'index': index}
        for key in ('gas_multiplier', 'liquidity_multiplier', 'oracle_multiplier'):
            try:
                value = float(scenario[key])
            except (TypeError, ValueError, OverflowError):
                return {'ok': False, 'reason_code': 'simulation_scenario_parameter_invalid', 'index': index, 'field': key}
            if value <= 0.0:
                return {'ok': False, 'reason_code': 'simulation_scenario_parameter_invalid', 'index': index, 'field': key}

    return {
        'ok': True,
        'reason_code': 'simulation_evidence_verified',
        'simulation_id': str(evidence['simulation_id']),
        'fork_block': fork_block,
        'pre_state_root': str(evidence['pre_state_root']),
        'post_state_root': str(evidence['post_state_root']),
        'scenario_digest': str(evidence['scenario_digest']),
        'scenario_count': len(scenarios),
    }
