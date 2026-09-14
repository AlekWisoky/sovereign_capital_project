from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services.runtime_agent_consensus_facade import RuntimeAgentConsensusFacade
from victor_ai_bot.runtime_services.runtime_decision_finalize_facade import RuntimeDecisionFinalizeFacade


class _EvidenceRuntime(RuntimeAgentConsensusFacade):
    def __init__(self):
        self._agent_hub_last = {}


def test_agent_decision_evidence_is_write_once_against_later_hub_cycle():
    runtime = _EvidenceRuntime()
    runtime._agent_hub_last = {
        'signals': {'alpha': 0.8},
        'confidences': {'alpha': 0.6},
        'features_used': {'alpha': {'margin_ratio': 0.01}},
        'regime': 'risk_on',
    }
    decision = SimpleNamespace(
        metadata={'canonical_decision_id': 'decision-1', 'correlation_id': 'corr-1'}
    )

    first = runtime.freeze_agent_decision_evidence(decision)
    runtime._agent_hub_last = {
        'signals': {'alpha': 0.1},
        'confidences': {'alpha': 0.2},
        'features_used': {'alpha': {'margin_ratio': 0.99}},
        'regime': 'risk_off',
    }
    second = runtime.freeze_agent_decision_evidence(decision)

    assert first['decision_id'] == 'decision-1'
    assert first['correlation_id'] == 'corr-1'
    assert first['signals'] == {'alpha': 0.8}
    assert first['features_used']['alpha']['margin_ratio'] == 0.01
    assert second == first
    assert decision.metadata['agent_decision_evidence'] == first


class _FinalizeRuntime(RuntimeDecisionFinalizeFacade):
    def __init__(self):
        self._pending = []
        self._auto_trading = False
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name='ethereum'))
        self.calls = []

    def _gas_budget_remaining_wei(self):
        self.calls.append('gas_budget')
        return 1

    def _safe_decide_opportunities(self, opps, **kwargs):
        self.calls.append('decide')
        return SimpleNamespace(action='trade', opp_id='opp-1', metadata={})

    def freeze_agent_decision_evidence(self, decision):
        self.calls.append('freeze')
        return {'decision_id': 'decision-1', 'correlation_id': 'corr-1'}

    def _apply_treasury_borrow_overlay(self, **kwargs):
        self.calls.append('treasury')
        return kwargs['decision']

    def _refresh_auto_queue_from_decision(self, decision, *, current_block):
        self.calls.append('queue')

    async def _run_postdecision_analytics_state(self, **kwargs):
        self.calls.append('postdecision')


@pytest.mark.asyncio
async def test_decision_finalize_freezes_evidence_before_downstream_steps():
    runtime = _FinalizeRuntime()
    runtime._agent_hub_last = {'signals': {'alpha': 0.9}}
    decision = await runtime._run_decision_finalize(
        opps=[SimpleNamespace(id='opp-1')],
        rpc=object(),
        regime_label='balanced',
        treasury_state={},
        current_block=12,
        loop_started_at=1.0,
    )

    assert decision.action == 'trade'
    assert runtime.calls == ['gas_budget', 'decide', 'freeze', 'treasury', 'queue', 'postdecision']
