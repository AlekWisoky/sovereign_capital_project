from pathlib import Path

from victor_ai_bot.superstructure.negotiation import NegotiationEngine
from victor_ai_bot.superstructure.proposals import Proposal


def _proposal(pid: str, **overrides):
    base = dict(
        proposal_id=pid,
        kind='trade',
        agent_id='agent-a',
        expected_return=10.0,
        risk_score=0.2,
        capital_required=100.0,
        execution_latency=0.1,
        funding_advantage=0.0,
        graph_confidence=0.8,
        reliability_score=0.9,
        confidence=0.7,
        overlap_keys=['eth:usdc'],
        meta={},
    )
    base.update(overrides)
    return Proposal(**base)


def test_negotiation_last_exposes_runtime_state(tmp_path):
    eng = NegotiationEngine(data_dir=str(tmp_path), chain='eth')
    out = eng.negotiate([_proposal('p1')], reason='test')
    snap = eng.last()
    assert out.ok is True
    assert snap['ok'] is True
    assert snap['selected']['proposal_id'] == 'p1'
    assert snap['runtime']['storage']['ok'] is True
    assert snap['runtime']['bus']['ok'] is True
    assert snap['runtime']['degraded'] is False


def test_negotiation_marks_score_failure_and_keeps_best_effort_selection(tmp_path):
    eng = NegotiationEngine(data_dir=str(tmp_path), chain='eth')
    good = _proposal('good', expected_return=8.0)
    bad = _proposal('bad', expected_return='oops')

    out = eng.negotiate([good, bad], reason='score-fail')
    snap = eng.last()

    assert out.ok is True
    assert out.selected.proposal_id == 'good'
    assert snap['scores']['bad'] == -1e9
    assert snap['runtime']['score']['ok'] is False
    assert snap['runtime']['score']['last_error_code'] == 'negotiation_score_failed'
    assert snap['runtime']['degraded'] is True


def test_negotiation_marks_bus_failure_without_failing_result(tmp_path, monkeypatch):
    eng = NegotiationEngine(data_dir=str(tmp_path), chain='eth')

    def _boom(*args, **kwargs):
        raise RuntimeError('bus down')

    monkeypatch.setattr('victor_ai_bot.superstructure.negotiation.BUS.update', _boom)

    out = eng.negotiate([_proposal('p1')], reason='bus-fail')
    snap = eng.last()

    assert out.ok is True
    assert snap['runtime']['bus']['ok'] is False
    assert snap['runtime']['bus']['last_error_code'] == 'negotiation_publish_failed'
    assert snap['runtime']['degraded'] is True


def test_negotiation_marks_storage_failure_without_raising(tmp_path, monkeypatch):
    eng = NegotiationEngine(data_dir=str(tmp_path), chain='eth')

    def _open_fail(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr('victor_ai_bot.superstructure.negotiation.os.open', _open_fail)

    out = eng.negotiate([_proposal('p1')], reason='write-fail')
    snap = eng.last()

    assert out.ok is True
    assert snap['runtime']['storage']['ok'] is False
    assert snap['runtime']['storage']['last_error_code'] == 'negotiation_record_write_failed'
    assert snap['runtime']['degraded'] is True
