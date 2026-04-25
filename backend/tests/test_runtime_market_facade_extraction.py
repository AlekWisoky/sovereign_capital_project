from __future__ import annotations

from types import SimpleNamespace

import victor_ai_bot.runtime_services.runtime_market_facade as market_mod
from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.admission_service import AdmissionPreparationError
from victor_ai_bot.runtime_services.runtime_market_facade import RuntimeMarketFacade

EXTRACTED_METHODS = {
    '_route_fail_rate',
    '_compute_market_regime',
    '_market_signal_snapshot',
    '_gas_signal_snapshot',
    '_behave_regime_state',
    '_behave_strategy_overlay',
    '_resolve_market_regime',
    '_pending_state_for_opp',
    '_pending_state_context_for_opp',
    '_annotate_execution_capture',
}

class _Eff:
    def __init__(self, *, pct: float = 75.0, fail: bool = False):
        self.pct = pct
        self.fail = fail

    def snapshot(self):
        if self.fail:
            raise RuntimeError('boom')
        return {'success_rate_pct': self.pct}

class _OpportunityService:
    def __init__(self):
        self.calls = []

    def annotate(self, opps, regime: str):
        self.calls.append((list(opps), regime))


class _Behave:
    def __init__(self, *, analyze=None, drift=None, overlay=None, analyze_exc: Exception | None = None, drift_exc: Exception | None = None, overlay_exc: Exception | None = None):
        self._analyze = analyze if analyze is not None else {
            'enabled': True,
            'regime_label': 'risk_on',
            'features': {'pending_rate': 0.2},
        }
        self._drift = drift if drift is not None else {'drift': True, 'score': 0.91}
        self._overlay = overlay if overlay is not None else {
            'ok': True,
            'strategy_priority_matrix': {'dex_flash': 0.9},
            'objectives': {'profit': 1.0},
        }
        self._analyze_exc = analyze_exc
        self._drift_exc = drift_exc
        self._overlay_exc = overlay_exc
        self.analyze_calls = []
        self.drift_calls = []
        self.overlay_calls = []

    def analyze_market(self, *, features, seed):
        self.analyze_calls.append((dict(features), seed))
        if self._analyze_exc is not None:
            raise self._analyze_exc
        return dict(self._analyze)

    def monitor_risk(self, *, features, seed):
        self.drift_calls.append((dict(features), seed))
        if self._drift_exc is not None:
            raise self._drift_exc
        return dict(self._drift)

    def select_strategy_overlay(self, *, opps, profit_goal, aggressiveness, seed):
        self.overlay_calls.append(
            {
                'opps': list(opps),
                'profit_goal': dict(profit_goal),
                'aggressiveness': aggressiveness,
                'seed': seed,
            }
        )
        if self._overlay_exc is not None:
            raise self._overlay_exc
        return dict(self._overlay)



class _RuntimeControl:
    def __init__(self, *, batch: bool = False):
        self.batch = batch

    def rpc_batch_enabled(self, _runtime):
        return self.batch


class _Anomaly:
    def __init__(self, *, gas_spike: bool = False, exc: Exception | None = None):
        self.gas_spike = gas_spike
        self.exc = exc
        self.calls = []

    def observe_gas(self, *, basefee_gwei: float):
        self.calls.append(float(basefee_gwei))
        if self.exc is not None:
            raise self.exc
        return self.gas_spike


class _Audit:
    def __init__(self):
        self.calls = []

    def append(self, kind, payload, *, actor, reason):
        self.calls.append((kind, dict(payload), actor, reason))


class _CC:
    def __init__(self):
        self.controls = SimpleNamespace(chaos_breakers_enabled=True, defensive_mode=False, reduce_exposure_half=False)
        self.audit = _Audit()
        self.persisted = 0

    def persist_controls(self):
        self.persisted += 1


class _RpcResult:
    def __init__(self, *, ok, result):
        self.ok = ok
        self.result = result


class _Rpc:
    def __init__(self, *, batch_results=None, fee_tip=0, gas_price=0, batch_exc: Exception | None = None):
        self.batch_results = list(batch_results or [])
        self.fee_tip_value = fee_tip
        self.gas_price_value = gas_price
        self.batch_exc = batch_exc
        self.batch_calls = []
        self.tip_calls = 0
        self.gas_calls = 0

    async def batch(self, reqs):
        self.batch_calls.append(list(reqs))
        if self.batch_exc is not None:
            raise self.batch_exc
        return list(self.batch_results)

    async def fee_history_tip(self):
        self.tip_calls += 1
        return self.fee_tip_value

    async def gas_price(self):
        self.gas_calls += 1
        return self.gas_price_value


class _AdmissionService:
    def prepare_capture(self, _runtime, opp, *, context):
        if getattr(opp, 'route_id', '') == 'drop-me':
            raise AdmissionPreparationError('denied')
        return SimpleNamespace(
            capture_decision=SimpleNamespace(expected_realized_value=float(getattr(opp, 'score', 0.0))),
            opportunity=opp,
        )

class _Runtime(RuntimeMarketFacade):
    def __init__(self):
        self._eff = _Eff()
        self._market_regime = {}
        self._opportunity_service = _OpportunityService()
        self._capture_engine = object()
        self._admission_service = _AdmissionService()
        self._bankroll = SimpleNamespace(state=SimpleNamespace(fail_streak=2))
        self._behave = None
        self._runtime_control_service = _RuntimeControl()
        self._anomaly = _Anomaly()
        self._cc = None

def test_runtime_bundle_inherits_extracted_market_facade():
    assert issubclass(RuntimeBundle, RuntimeMarketFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))

def test_runtime_market_facade_preserves_route_fail_rate_and_regime():
    runtime = _Runtime()
    fail_rate = runtime._route_fail_rate()
    regime = runtime._compute_market_regime(
        avg_margin_ratio=0.2,
        volatility_proxy=0.35,
        basefee_gwei=25.0,
        opportunity_rate=1.5,
        pending_rate=0.2,
        mev_risk=0.1,
    )
    assert round(fail_rate, 6) == 0.25
    assert regime == runtime._market_regime
    assert 'regime' in regime
    assert 'features' in regime


def test_runtime_market_facade_preserves_market_signal_snapshot(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(market_mod.BUS, 'snapshot', lambda: {'mev': {'sandwich_risk': 0.25, 'pending_rate': 0.4}})
    opps = [
        SimpleNamespace(meta={'margin_ratio': 1.0}),
        SimpleNamespace(meta={'margin_ratio': 1.2}),
        SimpleNamespace(meta={'margin_ratio': 0.8}),
        SimpleNamespace(meta={'margin_ratio': 1.1}),
        SimpleNamespace(meta={'margin_ratio': 'bad'}),
        SimpleNamespace(meta=None),
    ]
    snap = runtime._market_signal_snapshot(opps)
    assert snap['mev_risk'] == 0.25
    assert snap['pending_rate'] == 0.4
    assert round(snap['avg_margin_ratio'], 6) == 1.025
    assert round(snap['volatility_proxy'], 6) == round(min(1.0, (1.2 - 0.8) / 1.025), 6)


def test_runtime_market_facade_market_signal_snapshot_is_best_effort(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(market_mod.BUS, 'snapshot', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
    opps = [SimpleNamespace(meta={'margin_ratio': None}), SimpleNamespace(meta={'margin_ratio': 'oops'})]
    snap = runtime._market_signal_snapshot(opps)
    assert snap == {
        'mev_risk': 0.0,
        'pending_rate': 0.0,
        'avg_margin_ratio': 0.0,
        'volatility_proxy': 0.0,
    }

def test_runtime_market_facade_pending_state_helpers_delegate(monkeypatch):
    runtime = _Runtime()
    opp = SimpleNamespace(route_id='alpha')
    monkeypatch.setattr(market_mod, 'service_pending_state_for_opp', lambda _runtime, _opp: [{'src': 'mempool'}])
    monkeypatch.setattr(market_mod, 'service_pending_state_context_for_opp', lambda _runtime, _opp: {'summary': {'count': 1, 'sources': ['mempool']}})
    assert runtime._pending_state_for_opp(opp) == [{'src': 'mempool'}]
    assert runtime._pending_state_context_for_opp(opp)['summary']['count'] == 1

def test_runtime_market_facade_preserves_capture_annotation_order(monkeypatch):
    runtime = _Runtime()
    monkeypatch.setattr(market_mod, 'build_runtime_access_snapshot', lambda _runtime: {'snap': True})
    monkeypatch.setattr(market_mod, 'build_admission_context', lambda _runtime, _opp, *, snapshot: {'snapshot': snapshot})
    opps = [
        SimpleNamespace(route_id='mid', score=2.0),
        SimpleNamespace(route_id='drop-me', score=99.0),
        SimpleNamespace(route_id='top', score=5.0),
    ]
    runtime._annotate_execution_capture(opps, 'balanced')
    assert runtime._opportunity_service.calls[0][1] == 'balanced'
    assert [opp.route_id for opp in opps] == ['top', 'mid', 'drop-me']

def test_runtime_market_facade_fail_rate_is_best_effort():
    runtime = _Runtime()
    runtime._eff = _Eff(fail=True)
    assert runtime._route_fail_rate() == 0.0


def test_runtime_market_facade_preserves_behave_regime_state(monkeypatch):
    runtime = _Runtime()
    runtime._behave = _Behave()
    updates = []
    monkeypatch.setattr(market_mod.BUS, 'update', lambda key, value: updates.append((key, value)))
    state = runtime._behave_regime_state(
        basefee_gwei=22.0,
        priority_gwei=1.5,
        pending_rate=0.3,
        mev_risk=0.1,
        avg_margin_ratio=0.2,
        volatility_proxy=0.4,
        opp_count=7,
        current_block=12345,
    )
    assert state['regime_label'] == 'risk_on'
    assert runtime._behave.analyze_calls[0][0]['fail_streak'] == 2
    assert runtime._behave.analyze_calls[0][0]['opp_count'] == 7
    assert runtime._behave.drift_calls[0][0] == {'pending_rate': 0.2}
    assert updates[0][0] == 'alerts'
    assert updates[0][1]['type'] == 'regime_drift'
    assert updates[1] == ('behaveagent', state)


def test_runtime_market_facade_behave_regime_state_is_best_effort(monkeypatch):
    runtime = _Runtime()
    runtime._behave = _Behave(analyze_exc=RuntimeError('boom'))
    updates = []
    monkeypatch.setattr(market_mod.BUS, 'update', lambda key, value: updates.append((key, value)))
    state = runtime._behave_regime_state(
        basefee_gwei=22.0,
        priority_gwei=1.5,
        pending_rate=0.3,
        mev_risk=0.1,
        avg_margin_ratio=0.2,
        volatility_proxy=0.4,
        opp_count=7,
        current_block=12345,
    )
    assert state is None
    assert updates == []


def test_runtime_market_facade_behave_regime_state_tolerates_drift_monitor_failure(monkeypatch):
    runtime = _Runtime()
    runtime._behave = _Behave(drift_exc=RuntimeError('boom'))
    updates = []
    monkeypatch.setattr(market_mod.BUS, 'update', lambda key, value: updates.append((key, value)))
    state = runtime._behave_regime_state(
        basefee_gwei=22.0,
        priority_gwei=1.5,
        pending_rate=0.3,
        mev_risk=0.1,
        avg_margin_ratio=0.2,
        volatility_proxy=0.4,
        opp_count=7,
        current_block=12345,
    )
    assert state['regime_label'] == 'risk_on'
    assert updates == [('behaveagent', state)]


def test_runtime_market_facade_preserves_behave_strategy_overlay(monkeypatch):
    runtime = _Runtime()
    runtime._behave = _Behave()
    updates = []
    monkeypatch.setattr(market_mod.BUS, 'update', lambda key, value: updates.append((key, value)))
    original_state = {'enabled': True, 'regime_label': 'risk_on'}
    treasury_state = {
        'aggressiveness': {'aggressiveness_level': 'HIGH'},
        'goal': {'profit_target_usd': 50.0},
    }
    opps = [SimpleNamespace(route_id='a')]
    state = runtime._behave_strategy_overlay(
        behave_state=original_state,
        treasury_state=treasury_state,
        opps=opps,
        current_block=12345,
    )
    assert state['enabled'] is True
    assert state['strategy_priority_matrix']['dex_flash'] == 0.9
    assert runtime._behave.overlay_calls[0]['profit_goal'] == {'profit_target_usd': 50.0}
    assert runtime._behave.overlay_calls[0]['aggressiveness'] == 'HIGH'
    assert runtime._behave.overlay_calls[0]['seed'] == '12345'
    assert updates == [('behaveagent', state)]


def test_runtime_market_facade_behave_strategy_overlay_is_best_effort(monkeypatch):
    runtime = _Runtime()
    runtime._behave = _Behave(overlay_exc=RuntimeError('boom'))
    updates = []
    monkeypatch.setattr(market_mod.BUS, 'update', lambda key, value: updates.append((key, value)))
    original_state = {'enabled': True, 'regime_label': 'risk_on'}
    state = runtime._behave_strategy_overlay(
        behave_state=original_state,
        treasury_state={'aggressiveness': {'aggressiveness_level': 'LOW'}},
        opps=[SimpleNamespace(route_id='a')],
        current_block=12345,
    )
    assert state == original_state
    assert updates == []


def test_runtime_market_facade_resolves_market_regime_and_fallback_label():
    runtime = _Runtime()
    state = runtime._resolve_market_regime(
        regime_label='unknown',
        avg_margin_ratio=0.2,
        volatility_proxy=0.35,
        basefee_gwei=25.0,
        opportunity_rate=1.5,
        pending_rate=0.2,
        mev_risk=0.1,
    )
    assert state['regime_label'] == runtime._market_regime['regime']
    assert state['market_regime'] == runtime._market_regime


def test_runtime_market_facade_resolve_market_regime_is_best_effort(monkeypatch):
    runtime = _Runtime()
    runtime._market_regime = {'regime': 'carry', 'features': {'seeded': True}}
    monkeypatch.setattr(runtime, '_compute_market_regime', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('boom')))
    state = runtime._resolve_market_regime(
        regime_label='unknown',
        avg_margin_ratio=0.2,
        volatility_proxy=0.35,
        basefee_gwei=25.0,
        opportunity_rate=1.5,
        pending_rate=0.2,
        mev_risk=0.1,
    )
    assert state == {
        'regime_label': 'unknown',
        'market_regime': {'regime': 'carry', 'features': {'seeded': True}},
    }



def test_runtime_market_facade_preserves_gas_signal_snapshot_with_batch_and_breaker():
    import asyncio

    runtime = _Runtime()
    runtime._runtime_control_service = _RuntimeControl(batch=True)
    runtime._anomaly = _Anomaly(gas_spike=True)
    runtime._cc = _CC()
    rpc = _Rpc(
        batch_results=[
            _RpcResult(ok=True, result={"reward": [["0x3b9aca00"]]}),
            _RpcResult(ok=True, result="0x2540be400"),
        ]
    )

    snap = asyncio.run(runtime._gas_signal_snapshot(rpc))

    assert snap == {"basefee_gwei": 9.0, "priority_gwei": 1.0}
    assert runtime._anomaly.calls == [9.0]
    assert runtime._cc.controls.defensive_mode is True
    assert runtime._cc.controls.reduce_exposure_half is True
    assert runtime._cc.persisted == 1
    assert runtime._cc.audit.calls[0][0] == 'breaker_trip'
    assert runtime._cc.audit.calls[0][1]['kind'] == 'gas_spike'
    assert rpc.tip_calls == 0
    assert rpc.gas_calls == 0


def test_runtime_market_facade_gas_signal_snapshot_falls_back_and_is_best_effort():
    import asyncio

    runtime = _Runtime()
    runtime._runtime_control_service = _RuntimeControl(batch=False)
    runtime._anomaly = _Anomaly(exc=RuntimeError('boom'))
    rpc = _Rpc(fee_tip=2_000_000_000, gas_price=11_000_000_000)

    snap = asyncio.run(runtime._gas_signal_snapshot(rpc))

    assert snap == {"basefee_gwei": 9.0, "priority_gwei": 2.0}
    assert rpc.tip_calls == 1
    assert rpc.gas_calls == 1


def test_runtime_market_facade_gas_signal_snapshot_degrades_on_batch_failure():
    import asyncio

    runtime = _Runtime()
    runtime._runtime_control_service = _RuntimeControl(batch=True)
    runtime._anomaly = _Anomaly()
    rpc = _Rpc(batch_exc=RuntimeError('boom'))

    snap = asyncio.run(runtime._gas_signal_snapshot(rpc))

    assert snap == {"basefee_gwei": 0.0, "priority_gwei": 0.0}
