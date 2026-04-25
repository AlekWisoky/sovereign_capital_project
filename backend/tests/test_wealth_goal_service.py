from pathlib import Path

from victor_ai_bot.runtime_services.wealth_goal_service import WealthGoalService
from victor_ai_bot.treasury.config import ProfitGoal


class _TreasuryCfg:
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
        self.cfg = _TreasuryCfg()

    def snapshot(self):
        return {'aggressiveness': {'current_return_pct': 4.0}}

    def _save_goal(self):
        return None


class _Runtime:
    def __init__(self):
        self._treasury = _Treasury()

    def drawdown_state(self):
        return {'drawdownPct': 2.0, 'hardStop': {'active': False}}

    def kill_switch_state(self):
        return {'suppressions': {}}

    def fund_summary_state(self):
        return {'fundStage': 'staging', 'riskPosture': 'balanced'}


def test_wealth_goal_state_and_progress(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    state = svc.state(rt)
    assert state['ok'] is True
    assert state['state']['goalAchieved'] is False
    assert state['state']['progressPct'] == 50.0
    assert state['recommendation']['target_return_pct'] >= 8.0


def test_wealth_goal_update_creates_new_goal_id(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    before = svc.state(rt)
    updated = svc.set_goal(rt, {'target_return_pct': 12.0, 'timeframe_days': 21, 'risk_tolerance': 'aggressive'}, actor='operator', reason='raise_target')
    assert updated['ok'] is True
    assert updated['goal']['target_return_percentage'] == 12.0
    assert updated['state']['goalId'] != before['state']['goalId']
    assert updated['state']['goalRevision'] > before['state']['goalRevision']


def test_wealth_goal_achievement_records_history(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    rt._treasury.snapshot = lambda: {'aggressiveness': {'current_return_pct': 9.5}}
    state = svc.state(rt)
    assert state['state']['goalAchieved'] is True
    assert state['state']['achievedAtMs'] > 0
    assert any(item.get('status') == 'achieved' for item in state['history'])


def test_wealth_goal_blockers_and_ladder(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    rt.drawdown_state = lambda: {'drawdownPct': 9.0, 'hardStop': {'active': True}}
    rt._treasury.snapshot = lambda: {'aggressiveness': {'current_return_pct': 8.5}}
    state = svc.state(rt)
    assert state['state']['nextGoalAllowed'] is False
    assert 'drawdown_hard_stop_active' in state['state']['nextGoalBlockedReasons']
    assert len(state['state']['goalLadder']) >= 1


def test_wealth_goal_state_contains_goal_status_and_urgency(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    state = svc.state(rt)
    assert state['state']['goalStatus'] in {'active', 'blocked', 'achieved'}
    assert state['state']['goalUrgency'] in {'steady', 'catch_up', 'unlock_next_goal', 'stabilize'}
    assert isinstance(state['state']['blockedGoalReasonCodes'], list)


def test_wealth_goal_state_contains_velocity_and_horizon_metrics(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    rt = _Runtime()
    state = svc.state(rt)
    assert 'goalVelocityPctPerDay' in state['state']
    assert 'goalHorizonCompatibility' in state['state']


class _NoGoalTreasuryCfg:
    def __init__(self):
        self.goal = None


class _NoGoalTreasury:
    def __init__(self):
        self.cfg = _NoGoalTreasuryCfg()


class _NoGoalRuntime:
    def __init__(self):
        self._treasury = _NoGoalTreasury()


def test_wealth_goal_state_is_canonical_when_goal_unavailable(tmp_path: Path):
    svc = WealthGoalService(data_dir=str(tmp_path), chain='ethereum')
    state = svc.state(_NoGoalRuntime())
    assert state['ok'] is False
    assert state['status'] == 'unavailable'
    assert state['reason_code'] == 'treasury_goal_unavailable'
    assert state['error'] == 'treasury_goal_unavailable'
    assert state['goal'] is None
    assert state['history'] == []
