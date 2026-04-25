from pathlib import Path

from victor_ai_bot.runtime_services.replay_service import ReplayService


class _Metrics:
    loop_p50_ms = 10
    loop_p90_ms = 20
    loop_p99_ms = 30
    exec_e2e_p50_ms = 40
    exec_e2e_p90_ms = 50
    exec_e2e_p99_ms = 60
    submit_to_receipt_p50_ms = 70
    submit_to_receipt_p90_ms = 80
    submit_to_receipt_p99_ms = 90
    lastBlock = 123
    def model_dump(self):
        return {'loop_p50_ms': self.loop_p50_ms}


class _RPC:
    def snapshot(self):
        return {'error_rate': 0.01}


class _CCControls:
    defensive_mode = False


class _CC:
    controls = _CCControls()


class _CfgExecRft:
    enabled = True
    episode_export_enabled = True
    snapshot_top_k = 3
    enable_reward_trace_export = True


class _CfgExec:
    rft = _CfgExecRft()
    gas_mode = 'standard'
    send_mode = 'public'
    deadline_seconds = 30


class _CfgSafety:
    slippage_bps = 50
    max_daily_loss_pct = 3.0


class _Cfg:
    execution = _CfgExec()
    safety = _CfgSafety()


class _Replay:
    def create_bundle(self, **kwargs):
        return {'event_id': 'evt-1', 'payload': kwargs}


class _Runtime:
    def __init__(self):
        self.rpc_manager = _RPC()
        self._cc = _CC()
        self._auto_trading = True
        self.metrics = _Metrics()
        self.cfg = _Cfg()
        self._replay = _Replay()
        self._opps = []
    def _wealth_goal_for_replay(self):
        return {'target_return_pct': 10.0}


def test_replay_service_runtime_context_and_bundle():
    svc = ReplayService()
    rt = _Runtime()
    ctx = svc.runtime_context_for_replay(rt)
    assert ctx['portfolio']['state'] == 'active'
    assert ctx['rpcDegraded'] is False
    eid = svc.create_bundle(rt, opportunity_id='o1', route_id='r1', mode='manual', rl_state='s', rl_action=1, latency_ms=12, plan={}, dry_run=False, ok=True, attempted=True, submitted=True, reason='ok')
    assert eid == 'evt-1'
