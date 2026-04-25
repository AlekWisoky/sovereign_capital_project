from __future__ import annotations

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_replay_facade import RuntimeReplayFacade


EXTRACTED_METHODS = {
    '_controls_for_replay',
    '_wealth_goal_for_replay',
    '_runtime_context_for_replay',
    '_top_opportunities_for_replay',
    '_replay_export_enabled',
    '_create_replay_bundle',
}


class _ReplayService:
    def controls_for_replay(self, runtime):
        return {'defensive_mode': True, 'mode': 'shadow'}

    def wealth_goal_for_replay(self, runtime):
        return {'targetUsd': 1000}

    def runtime_context_for_replay(self, runtime):
        return {'portfolio': {'state': 'defensive'}}

    def top_opportunities_for_replay(self, runtime):
        return [{'id': 'opp-1'}]

    def replay_export_enabled(self, runtime):
        return True

    def create_bundle(self, runtime, **kwargs):
        self.last_create = kwargs
        return 'evt-123'


class _Runtime(RuntimeReplayFacade):
    def __init__(self, replay_service=None):
        self._replay_service = replay_service


def test_runtime_bundle_inherits_extracted_replay_facade():
    assert issubclass(RuntimeBundle, RuntimeReplayFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_replay_facade_preserves_replay_compatibility_surface():
    svc = _ReplayService()
    runtime = _Runtime(replay_service=svc)

    assert runtime._controls_for_replay()['defensive_mode'] is True
    assert runtime._wealth_goal_for_replay()['targetUsd'] == 1000
    assert runtime._runtime_context_for_replay()['portfolio']['state'] == 'defensive'
    assert runtime._top_opportunities_for_replay()[0]['id'] == 'opp-1'
    assert runtime._replay_export_enabled() is True
    event_id = runtime._create_replay_bundle(
        opportunity_id='opp-1',
        route_id='route-1',
        mode='manual',
        rl_state='s',
        rl_action=1,
        latency_ms=12,
        plan={'current_block': 123},
        dry_run=False,
        ok=True,
        attempted=True,
        submitted=False,
        reason='ok',
        tx_hash='0x1',
        audit_hash='audit-1',
        block_number=123,
        status='draft',
    )
    assert event_id == 'evt-123'
    assert svc.last_create['opportunity_id'] == 'opp-1'
    assert svc.last_create['status'] == 'draft'


def test_runtime_replay_facade_unavailable_defaults_remain_safe():
    runtime = _Runtime(replay_service=None)
    assert runtime._controls_for_replay() == {}
    assert runtime._wealth_goal_for_replay() == {}
    assert runtime._runtime_context_for_replay() == {}
    assert runtime._top_opportunities_for_replay() == []
    assert runtime._replay_export_enabled() is False
    assert runtime._create_replay_bundle(
        opportunity_id='opp-1',
        route_id='route-1',
        mode='manual',
        rl_state='s',
        rl_action=1,
        latency_ms=12,
        plan={},
        dry_run=False,
        ok=True,
        attempted=False,
        submitted=False,
        reason='noop',
    ) == ''
