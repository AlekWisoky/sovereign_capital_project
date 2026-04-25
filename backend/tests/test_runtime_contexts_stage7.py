from victor_ai_bot.runtime_services.runtime_context import build_admission_context, build_wealth_goal_signals
from victor_ai_bot.treasury.config import ProfitGoal


class _GoalCfg:
    def __init__(self):
        self.goal = ProfitGoal(
            target_return_percentage=8.0,
            time_horizon_seconds=14 * 86400,
            risk_tolerance='moderate',
            max_drawdown_pct=12.0,
            capital_commitment_pct=35.0,
        )


class _Treasury:
    def __init__(self):
        self.cfg = _GoalCfg()

    def snapshot(self):
        return {'aggressiveness': {'current_return_pct': 6.0}}


class _Capture:
    def evaluate(self, opp, **kwargs):
        class D:
            metadata = {'envelope': {'route_family': 'flashloan_atomic'}}
            action = 'trade'
            lane = type('Lane', (), {'value': 'PRIVATE'})()
            def to_dict(self):
                return {'metadata': self.metadata}
        return D()


class _Runtime:
    def __init__(self):
        self._treasury = _Treasury()
        self._capture_engine = _Capture()
        self._market_regime = {'regime': 'balanced'}
        self.cfg = type('Cfg', (), {'chain': type('Chain', (), {'chain_id': 1, 'name': 'ethereum'})()})()
        self._cc = type('CC', (), {'controls': type('Controls', (), {'force_send_mode': 'private'})()})()
        self._wealth_goal_service = type('WGS', (), {'state': lambda self2, runtime: {'state': {'aggressivenessCap': 1.05}}})()

    def drawdown_state(self):
        return {'drawdownPct': 2.0, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def capital_engine_state(self):
        return {'capital_engine': {'family_targets': {'flashloan_atomic': 0.4}}, 'capital_efficiency_metrics': {'deployedCapitalWei': 2_500 * 10**18}}

    def fund_summary_state(self):
        return {'health': {'fundStage': 'staging', 'riskPosture': 'balanced', 'riskScore': 0.2, 'falseAdmissionRate': 0.02, 'falseDropRate': 0.03}}

    def endpoint_quality_state(self):
        return {'lanes': {'private': {'relays': [{'score': 0.92}]}}}

    def execution_live_state(self):
        return {'items': [{'routeExecutable': True, 'adversarial': {'staleProbability': 0.05, 'interferenceProbability': 0.08}}]}

    def _pending_state_for_opp(self, opp):
        return [{'hash': '0x1'}]

    def _pending_state_context_for_opp(self, opp):
        return {'rows': [{'hash': '0x1'}], 'summary': {'count': 1, 'sources': ['runtime']}}


class _Opp:
    def __init__(self):
        self.meta = {}


def test_build_admission_context_collects_structured_inputs():
    rt = _Runtime()
    ctx = build_admission_context(rt, _Opp())
    assert ctx.chain_id == 1
    assert ctx.force_send_mode == 'private'
    assert ctx.pending_context['summary']['count'] == 1
    assert ctx.treasury_state['capital_engine']['family_targets']['flashloan_atomic'] == 0.4


def test_build_wealth_goal_signals_uses_canonical_runtime_summaries():
    rt = _Runtime()
    sig = build_wealth_goal_signals(rt)
    assert sig.capital_base_usd >= 2500
    assert sig.execution_realism_score > 0.5
    assert sig.stability_score > 0.5
    assert sig.fund_stage == 'staging'
