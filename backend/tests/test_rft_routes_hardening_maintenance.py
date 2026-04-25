import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.rft import router as rft_router
from victor_ai_bot.auth import require_admin
from victor_ai_bot.rft.episode_builder import build_episodes
from victor_ai_bot.rft.graders.composite import score_proposal
from victor_ai_bot.rft.replay.bundle import list_replay_bundles
from victor_ai_bot.rft.schema import (
    BreakerState,
    EpisodeContext,
    LastOutcome,
    LatencyProfile,
    RiskCaps,
    TopOpportunity,
)
from victor_ai_bot.runtime_subsystems.replay_store import ReplayBundleStore


class _Audit:
    def __init__(self, *, should_raise: bool = False):
        self.should_raise = should_raise
        self.items = []

    def append(self, event: str, payload: dict, *, actor: str, reason: str) -> None:
        if self.should_raise:
            raise ValueError("audit_broken")
        self.items.append(
            {
                "event": event,
                "payload": dict(payload or {}),
                "actor": actor,
                "reason": reason,
            }
        )


class _Controls:
    def __init__(self, *, export_enabled: bool = False):
        self.rft_episode_export_enabled = export_enabled


class _CC:
    def __init__(self, *, export_enabled: bool = False, audit_raises: bool = False):
        self.controls = _Controls(export_enabled=export_enabled)
        self.audit = _Audit(should_raise=audit_raises)


class _Runtime:
    def __init__(
        self,
        *,
        export_enabled: bool = False,
        cc_export_enabled: bool = False,
        audit_raises: bool = False,
    ):
        class _RFT:
            enabled = False
            episode_export_enabled = export_enabled
            snapshot_top_k = 20
            enable_reward_trace_export = True
            grader_weights = {}

        class _Execution:
            rft = _RFT()

        class _Cfg:
            execution = _Execution()

        self.cfg = _Cfg()
        self._cc = _CC(export_enabled=cc_export_enabled, audit_raises=audit_raises)


def _write_bundle(data_dir: Path) -> None:
    store = ReplayBundleStore(data_dir=str(data_dir), chain="ethereum", chain_id=1)
    store.create_bundle(
        block_number=123,
        opportunity_id="opp-1",
        route_id="route-1",
        mode="auto",
        rl_state="s0",
        rl_action=1,
        runtime={
            "regime": {"current": "normal"},
            "risk": {
                "caps": {
                    "maxDailyLossPct": 3.0,
                    "maxExposurePct": 80.0,
                    "sandboxCapPct": 10.0,
                    "probationCapPct": 2.5,
                },
                "breakers": {},
            },
            "observability": {"loopMsP50": 10, "loopMsP90": 20, "loopMsP99": 30},
            "rpcDegraded": False,
        },
        controls={"sandbox_only": False, "paused": False},
        wealth_goal={"target_return_pct": 8.0},
        opportunities=[
            {
                "opportunity_id": "opp-1",
                "route_id": "route-1",
                "strategy_id": "flashloan_atomic",
                "expected_profit_after_costs_wei": "100",
                "expected_profit_after_gas_usd_micro": 5_000_000,
                "expected_profit_usd_micro": 6_000_000,
                "competition": "medium",
                "venue_tags": ["univ3"],
                "why": ["spread"],
            }
        ],
        execution={"send_mode": "protected_rpc", "slippage_bps": 50, "deadline_seconds": 30},
        status="dry_run",
    )


def _ctx() -> EpisodeContext:
    return EpisodeContext(
        episode_id="episode-1",
        replay_event_id="replay-1",
        decision_id="decision-1",
        chain="ethereum",
        chain_id=1,
        block_number=123,
        opportunity_id="opp-1",
        route_id="route-1",
        v1_focus="flashloan_atomic",
        regime_state="normal",
        risk_state="normal",
        risk_caps=RiskCaps(
            max_daily_loss_pct_bps=300,
            max_exposure_pct_bps=8000,
            sandbox_cap_pct_bps=1000,
            probation_cap_pct_bps=250,
        ),
        breakers=BreakerState(
            drawdown_breaker=False,
            gas_anomaly_breaker=False,
            drift_breaker=False,
            rpc_degraded=False,
        ),
        latency=LatencyProfile(
            loop_ms_p90=400,
            loop_ms_p99=900,
            exec_ms_p90=500,
            exec_ms_p99=950,
        ),
        last_outcomes=[
            LastOutcome(
                event_id="old-1",
                ok=True,
                reward_scaled_ppm=2500,
                realized_after_gas_usd_micro=5_000_000,
            )
        ],
        top_opportunities=[
            TopOpportunity(
                opportunity_id="opp-1",
                route_id="route-1",
                strategy_id="flashloan_atomic",
                expected_profit_after_costs_wei="1000000000000000000",
                expected_profit_after_gas_usd_micro=8_000_000,
                expected_profit_usd_micro=9_000_000,
                competition="medium",
                venue_tags=["univ3", "curve"],
                why=["top spread", "gas-adjusted"],
            )
        ],
        controls={"sandbox_only": False, "paused": False},
        wealth_goal={"target_return_pct": 8.0},
        reward_trace={"reward_scaled_ppm": 2500},
        execution_summary={
            "send_mode": "protected_rpc",
            "slippage_bps": 50,
            "deadline_seconds": 30,
        },
    )


def _proposal() -> dict:
    return {
        "proposal_schema_version": "1",
        "backend_builder_version": "test-builder",
        "opportunity_id": "opp-1",
        "strategy_id": "flashloan_atomic",
        "notional_usd_micro": 250_000_000,
        "send_mode": "protected_rpc",
        "why": ["net positive", "route ranked first"],
        "constraints": {"max_slippage_bps": 50, "deadline_seconds": 30},
        "mode": {"sandbox_only": False, "defensive": False, "probation": False},
    }


def test_rft_export_disabled_when_config_and_controls_disable_export(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    monkeypatch.setenv("VICTOR_DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(rft_router)
    app.state.runtime = _Runtime(export_enabled=False, cc_export_enabled=False)
    app.dependency_overrides[require_admin] = lambda: True
    client = TestClient(app)

    res = client.post("/api/rft/episodes/export", json={"limit": 1})

    assert res.status_code == 200
    assert res.json() == {"ok": False, "error": "episode_export_disabled"}


def test_rft_export_succeeds_when_audit_append_fails(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    monkeypatch.setenv("VICTOR_DATA_DIR", str(data_dir))
    app = FastAPI()
    app.include_router(rft_router)
    app.state.runtime = _Runtime(export_enabled=True, audit_raises=True)
    app.dependency_overrides[require_admin] = lambda: True
    client = TestClient(app)

    res = client.post(
        "/api/rft/episodes/export",
        json={"limit": 1, "reason": "monthly-pass", "filename": "episodes.jsonl"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["count"] == 1
    assert body["reason"] == "monthly-pass"
    assert os.path.exists(body["path"])


def test_rft_score_get_rejects_invalid_proposal_json(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    monkeypatch.setenv("VICTOR_DATA_DIR", str(data_dir))
    episode_id = build_episodes(str(data_dir), limit=1, top_k=20)[0].context.episode_id
    app = FastAPI()
    app.include_router(rft_router)
    app.state.runtime = _Runtime(export_enabled=True)
    app.dependency_overrides[require_admin] = lambda: True
    client = TestClient(app)

    res = client.get(
        "/api/rft/grader/score",
        params={"episode_id": episode_id, "proposal": "{not-json}"},
    )

    assert res.status_code == 200
    assert res.json() == {"ok": False, "error": "invalid_proposal_json"}


def test_build_episodes_defaults_invalid_numeric_fields(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    bundle_path = Path(list_replay_bundles(str(data_dir))[0])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["runtime"]["risk"]["caps"] = {
        "maxDailyLossPct": "bad",
        "maxExposurePct": "bad",
        "sandboxCapPct": "bad",
        "probationCapPct": "bad",
    }
    bundle["runtime"]["observability"] = {
        "loopMsP50": "bad",
        "loopMsP90": "bad",
        "loopMsP99": "bad",
        "execLatencyMsP50": "bad",
        "submitToReceiptMsP50": "bad",
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    episode = build_episodes(str(data_dir), limit=1, top_k=20)[0]

    assert episode.context.risk_caps.max_daily_loss_pct_bps == 300
    assert episode.context.risk_caps.max_exposure_pct_bps == 8000
    assert episode.context.risk_caps.sandbox_cap_pct_bps == 1000
    assert episode.context.risk_caps.probation_cap_pct_bps == 250
    assert episode.context.latency.loop_ms_p50 == 0
    assert episode.context.latency.loop_ms_p90 == 0
    assert episode.context.latency.exec_ms_p50 == 0
    assert episode.context.latency.submit_to_receipt_ms_p50 == 0


def test_build_episodes_ranks_top_opportunities_by_after_costs_truth(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    bundle_path = Path(list_replay_bundles(str(data_dir))[0])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["opportunities"] = [
        {
            "opportunity_id": "higher-after-gas",
            "route_id": "route-high-gas",
            "strategy_id": "flashloan_atomic",
            "expected_profit_after_costs_wei": "100",
            "expected_profit_after_gas_usd_micro": 12_000_000,
            "expected_profit_usd_micro": 13_000_000,
            "competition": "medium",
            "venue_tags": ["univ3"],
            "why": ["gross leader"],
        },
        {
            "opportunity_id": "higher-after-costs",
            "route_id": "route-high-after-costs",
            "strategy_id": "flashloan_atomic",
            "expected_profit_after_costs_wei": "250",
            "expected_profit_after_gas_usd_micro": 8_000_000,
            "expected_profit_usd_micro": 9_000_000,
            "competition": "medium",
            "venue_tags": ["curve"],
            "why": ["net leader"],
        },
    ]
    bundle["opportunity_id"] = "higher-after-gas"
    bundle["route_id"] = "route-high-gas"
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    episode = build_episodes(str(data_dir), limit=1, top_k=20)[0]

    assert episode.context.top_opportunities[0].opportunity_id == "higher-after-costs"
    assert episode.reference.quality == "best_known"
    assert episode.reference.proposal is not None
    assert episode.reference.proposal.opportunity_id == "higher-after-costs"
    assert "after_costs_positive" in episode.reference.proposal.why


def test_build_episodes_returns_no_reference_when_after_costs_non_positive(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    bundle_path = Path(list_replay_bundles(str(data_dir))[0])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["opportunities"] = [
        {
            "opportunity_id": "non-positive-a",
            "route_id": "route-a",
            "strategy_id": "flashloan_atomic",
            "expected_profit_after_costs_wei": "0",
            "expected_profit_after_gas_usd_micro": 7_000_000,
            "expected_profit_usd_micro": 8_000_000,
            "competition": "medium",
            "venue_tags": ["univ3"],
            "why": ["gross only"],
        },
        {
            "opportunity_id": "non-positive-b",
            "route_id": "route-b",
            "strategy_id": "flashloan_atomic",
            "expected_profit_after_costs_wei": "-5",
            "expected_profit_after_gas_usd_micro": 6_000_000,
            "expected_profit_usd_micro": 7_000_000,
            "competition": "medium",
            "venue_tags": ["curve"],
            "why": ["still gross only"],
        },
    ]
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

    episode = build_episodes(str(data_dir), limit=1, top_k=20)[0]

    assert [x.opportunity_id for x in episode.context.top_opportunities] == [
        "non-positive-a",
        "non-positive-b",
    ]
    assert episode.reference.quality == "none"
    assert episode.reference.proposal is None


def test_score_proposal_ignores_invalid_weight_values():
    result = score_proposal(_ctx(), _proposal(), weights={"profit": object(), "latency": "bad"})

    assert result.proposal_valid is True
    assert result.total_reward_ppm > 0
