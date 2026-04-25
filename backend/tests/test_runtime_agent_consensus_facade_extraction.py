from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.runtime_services.runtime_agent_consensus_facade as ac_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_agent_consensus_facade import RuntimeAgentConsensusFacade

EXTRACTED_METHODS = {
    '_agent_hub_local_state',
    '_agent_hub_weights',
    '_run_agent_consensus_gate',
}


class _Hub:
    def __init__(self, *, exc: Exception | None = None):
        self.exc = exc
        self.calls = []

    def step(self, *, state):
        self.calls.append(state)
        if self.exc is not None:
            raise self.exc
        return SimpleNamespace(
            signals={'alpha': 0.8, 'beta': 0.2},
            confidences={'alpha': 0.6, 'beta': 0.4},
            outputs={'top': 'alpha'},
            contracts={'alpha': {'max_notional': 100}},
            health={'ok': True},
            mandates={'alpha': 'observe'},
            portfolio_manager={'rebalance': False},
        )


class _Consensus:
    def __init__(self):
        self.calls = []

    def compute(self, *, signals, confidences, regime, strategy_type, deterministic_key):
        self.calls.append(
            {
                'signals': dict(signals),
                'confidences': dict(confidences),
                'regime': regime,
                'strategy_type': strategy_type,
                'deterministic_key': deterministic_key,
            }
        )
        return {'consensus_score': 0.77, 'allow': True, 'key': deterministic_key}


class _Weighting:
    def __init__(self, *, exc: Exception | None = None):
        self.exc = exc
        self.calls = []

    def weights_for(self, *, regime, agents):
        self.calls.append({'regime': regime, 'agents': list(agents)})
        if self.exc is not None:
            raise self.exc
        return {'alpha': 0.7, 'beta': 0.3}


class _Runtime(RuntimeAgentConsensusFacade):
    def __init__(self):
        self._agent_hub = None
        self._consensus = None
        self._agent_weighting = None
        self._agent_hub_last = {}
        self._consensus_last = {}


def _opp(
    *,
    can_execute=True,
    opp_id='opp-1',
    margin_ratio=0.25,
    gas_ratio=0.1,
    p_success=0.9,
    ev_wei=123,
    legs=2,
    profit_after_costs=123,
    safety_profit_after_costs=123,
    route_executable=True,
    route_invalid_causes=None,
    route_runtime_degraded=False,
    route_runtime_code='execution_route_profit_degraded',
):
    meta = {
        'margin_ratio': margin_ratio,
        'gas_ratio': gas_ratio,
        'brain': {'p_success': p_success, 'ev_wei': ev_wei},
        'execution_route_plan': {
            'executable': route_executable,
            'route_invalid_causes': list(route_invalid_causes or []),
        },
        'route_invalid_causes': list(route_invalid_causes or []),
        'safety': {},
    }
    if profit_after_costs is not None:
        meta['profit_after_costs'] = profit_after_costs
    if safety_profit_after_costs is not None:
        meta['safety']['profit_after_costs_wei'] = safety_profit_after_costs
    if route_runtime_degraded:
        meta['execution_route_runtime'] = {
            'degraded': True,
            'profit': {'ok': False, 'code': route_runtime_code},
        }
    return SimpleNamespace(
        can_execute=can_execute,
        id=opp_id,
        meta=meta,
        route=SimpleNamespace(legs=[object()] * legs),
    )


def test_runtime_bundle_inherits_extracted_agent_consensus_facade():
    assert issubclass(RuntimeBundle, RuntimeAgentConsensusFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_agent_consensus_facade_preserves_gate(monkeypatch):
    runtime = _Runtime()
    runtime._agent_hub = _Hub()
    runtime._consensus = _Consensus()
    runtime._agent_weighting = _Weighting()
    updates = []
    monkeypatch.setattr(ac_mod.BUS, 'update', lambda key, value: updates.append((key, value)))

    state = runtime._run_agent_consensus_gate(
        opps=[_opp(opp_id='best-1', legs=3)],
        bus_snap={'dex': {'count': 5}, 'cex': {'quotes': 2}},
        mev_snap={'pending_rate': 0.2},
        treasury_state={
            'borrow_mult_target_cap': 2.2,
            'aggressiveness': {'aggressiveness_level': 'HIGH', 'urgency_factor': 0.8},
        },
        regime_label='risk_on',
        current_block=12345,
    )

    assert state['local']['id'] == 'best-1'
    assert runtime._agent_hub.calls[0]['local']['legs'] == 3
    assert runtime._agent_hub.calls[0]['treasury']['borrow_mult_target_cap'] == 2.2
    assert runtime._agent_hub.calls[0]['treasury']['aggressiveness_level'] == 'HIGH'
    assert runtime._agent_weighting.calls[0] == {'regime': 'risk_on', 'agents': ['alpha', 'beta']}
    assert runtime._agent_hub_last['weights'] == {'alpha': 0.7, 'beta': 0.3}
    assert runtime._consensus.calls[0]['deterministic_key'] == '12345:best-1'
    assert runtime._consensus_last['allow'] is True
    assert updates == [('consensus', runtime._consensus_last)]


def test_runtime_agent_consensus_facade_weighting_is_best_effort(monkeypatch):
    runtime = _Runtime()
    runtime._agent_hub = _Hub()
    runtime._consensus = _Consensus()
    runtime._agent_weighting = _Weighting(exc=RuntimeError('boom'))
    monkeypatch.setattr(ac_mod.BUS, 'update', lambda *_args, **_kwargs: None)

    state = runtime._run_agent_consensus_gate(
        opps=[_opp()],
        bus_snap={},
        mev_snap={},
        treasury_state={},
        regime_label='balanced',
        current_block=7,
    )

    assert state is not None
    assert runtime._agent_hub_last['weights'] == {}
    assert runtime._consensus_last['key'] == '7:opp-1'


def test_runtime_agent_consensus_facade_gate_is_best_effort(monkeypatch):
    runtime = _Runtime()
    runtime._agent_hub = _Hub(exc=RuntimeError('boom'))
    runtime._consensus = _Consensus()
    updates = []
    monkeypatch.setattr(ac_mod.BUS, 'update', lambda key, value: updates.append((key, value)))

    state = runtime._run_agent_consensus_gate(
        opps=[_opp()],
        bus_snap={'dex': {'count': 1}},
        mev_snap={'pending_rate': 0.1},
        treasury_state={'aggressiveness': {'aggressiveness_level': 'LOW'}},
        regime_label='balanced',
        current_block=5,
    )

    assert state is None
    assert runtime._agent_hub_last == {}
    assert runtime._consensus_last == {}
    assert updates == []


def test_runtime_agent_consensus_facade_prefers_route_ready_profitable_opportunity(monkeypatch):
    runtime = _Runtime()
    runtime._agent_hub = _Hub()
    runtime._consensus = _Consensus()
    monkeypatch.setattr(ac_mod.BUS, 'update', lambda *_args, **_kwargs: None)

    state = runtime._run_agent_consensus_gate(
        opps=[
            _opp(opp_id='route-broken', route_invalid_causes=['route_plan_not_executable']),
            _opp(opp_id='route-ready', ev_wei=321),
        ],
        bus_snap={},
        mev_snap={},
        treasury_state={},
        regime_label='balanced',
        current_block=88,
    )

    assert state['local']['id'] == 'route-ready'
    assert runtime._consensus_last['key'] == '88:route-ready'


def test_runtime_agent_consensus_facade_skips_unverified_after_fee_candidates(monkeypatch):
    runtime = _Runtime()
    runtime._agent_hub = _Hub()
    runtime._consensus = _Consensus()
    monkeypatch.setattr(ac_mod.BUS, 'update', lambda *_args, **_kwargs: None)

    state = runtime._run_agent_consensus_gate(
        opps=[
            _opp(opp_id='mismatch', profit_after_costs=500, safety_profit_after_costs=200),
        ],
        bus_snap={},
        mev_snap={},
        treasury_state={},
        regime_label='balanced',
        current_block=9,
    )

    assert state['local'] == {}
    assert runtime._consensus_last['key'] == '9:'
