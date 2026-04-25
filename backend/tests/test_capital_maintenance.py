from pathlib import Path

from victor_ai_bot.superstructure.capital import CapitalAuctionEngine
from victor_ai_bot.superstructure.proposals import Proposal
import victor_ai_bot.superstructure.capital as capital_mod


def _proposal(pid: str, **overrides) -> Proposal:
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
        meta={'gov_power': 0.2, 'gov_rep': 0.7},
    )
    base.update(overrides)
    return Proposal(**base)


def test_capital_has_no_broad_exception_handlers() -> None:
    text = (Path(__file__).resolve().parents[1] / 'victor_ai_bot' / 'superstructure' / 'capital.py').read_text(encoding='utf-8')
    assert 'except Exception' not in text


def test_capital_marks_bid_failures_and_keeps_best_effort_allocation(tmp_path) -> None:
    engine = CapitalAuctionEngine(data_dir=str(tmp_path), chain='eth')
    good = _proposal('good', expected_return=8.0, capital_required=50.0)
    bad = _proposal('bad', expected_return='oops', capital_required='bad', meta='not-a-dict')

    out = engine.allocate([good, bad], total_capital=100.0)
    snap = engine.last()

    assert out.ok is True
    assert snap['allocations']['good'] > 0.0
    assert snap['allocations']['bad'] == 0.0
    assert snap['runtime']['bid']['ok'] is False
    assert snap['runtime']['bid']['last_error_code'] in {
        'capital_expected_return_invalid',
        'capital_required_invalid',
        'capital_meta_invalid',
    }
    assert snap['runtime']['degraded'] is True


def test_capital_marks_bus_publish_failure_without_failing_result(tmp_path, monkeypatch) -> None:
    engine = CapitalAuctionEngine(data_dir=str(tmp_path), chain='eth')

    def _boom(*args, **kwargs):
        raise RuntimeError('bus down')

    monkeypatch.setattr(capital_mod.BUS, 'update', _boom)

    out = engine.allocate([_proposal('p1')], total_capital=100.0)
    snap = engine.last()

    assert out.ok is True
    assert snap['runtime']['bus']['ok'] is False
    assert snap['runtime']['bus']['last_error_code'] == 'capital_publish_failed'
    assert snap['runtime']['degraded'] is True


def test_capital_marks_storage_failure_without_raising(tmp_path, monkeypatch) -> None:
    engine = CapitalAuctionEngine(data_dir=str(tmp_path), chain='eth')

    def _open_fail(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(capital_mod.os, 'open', _open_fail)

    out = engine.allocate([_proposal('p1')], total_capital=100.0)
    snap = engine.last()

    assert out.ok is True
    assert snap['runtime']['storage']['ok'] is False
    assert snap['runtime']['storage']['last_error_code'] == 'capital_record_write_failed'
    assert snap['runtime']['degraded'] is True
