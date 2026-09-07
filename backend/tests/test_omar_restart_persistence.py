from pathlib import Path

from victor_ai_bot.omar.config import OmarConfig
from victor_ai_bot.omar.runtime import OmarRuntime
from victor_ai_bot.pathing import CANONICAL_BACKEND_DATA_DIR


def _context() -> dict:
    return {
        "margin_ratio": 0.001,
        "gas_ratio": 0.0004,
        "p_success": 0.9,
        "drawdown_pct": 1.0,
        "execution_realism": 0.9,
        "stability": 0.9,
        "goal_gap_pct": 0.0,
        "volatility": 0.1,
        "legs": 2,
        "capital_source": "internal_prime",
        "internal_prime_available": True,
        "prime_capacity_ratio": 0.9,
        "prime_cost_bps": 2.0,
    }


def test_omar_default_root_is_canonical_backend_data(monkeypatch):
    monkeypatch.delenv("VICTOR_DATA_DIR", raising=False)
    rt = OmarRuntime(OmarConfig(enabled=False), chain_name="default-root")
    assert Path(rt.data_dir) == CANONICAL_BACKEND_DATA_DIR / "superstructure"
    assert Path(rt.omar_data_dir) == CANONICAL_BACKEND_DATA_DIR / "superstructure" / "omar"


def test_omar_restart_preserves_settled_learning_and_lineage(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VICTOR_DATA_DIR", str(tmp_path))

    cfg = OmarConfig(enabled=True, self_play_enabled=False, real_learning_min_observations=1)
    first = OmarRuntime(cfg, chain_name="restart")
    expected_root = tmp_path / "superstructure"
    assert Path(first.data_dir) == expected_root
    assert Path(first.omar_data_dir) == expected_root / "omar"
    assert Path(first.learning_path).parent == expected_root / "omar" / "learning"

    context = _context()
    state_key = first._real_learner.state_key(context)
    first.observe_decision(
        decision_id="decision-restart-1",
        opportunity_id="opportunity-restart-1",
        route_id="route-restart-1",
        action="EXECUTE",
        state_key=state_key,
        context=context,
        metadata={"correlation_id": "corr-restart-1"},
    )
    result = first.observe_outcome(
        decision_id="decision-restart-1",
        ok=True,
        realized_net_usd=5.0,
        expected_net_usd=4.0,
        amount_in_wei=100,
        gas_cost_usd=0.1,
        slippage_bps=2.0,
        latency_ms=25,
        route_id="route-restart-1",
        tx_hash="0xtx-restart-1",
        outcome_truth_verified=True,
        metadata={"correlation_id": "corr-restart-1"},
    )
    assert result["ok"] is True
    assert first._real_learner.total_observations == 1
    assert first.last_outcome["decision_id"] == "decision-restart-1"
    first.stop()

    second = OmarRuntime(cfg, chain_name="restart")
    assert second._real_learner is not None
    assert second._real_learner.total_observations == 1
    assert state_key in second._real_learner.q
    assert second._real_learner.q[state_key]["EXECUTE"] > 0.0

    event_path = Path(second.learning_path + ".jsonl")
    lines = event_path.read_text(encoding="utf-8").splitlines()
    assert any(
        '"tx_hash": "0xtx-restart-1"' in line
        and '"decision_id": "decision-restart-1"' in line
        and '"route_id": "route-restart-1"' in line
        for line in lines
    )
