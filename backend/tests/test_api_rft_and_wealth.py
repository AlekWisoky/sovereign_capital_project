import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from victor_ai_bot.api_routes.rft import router as rft_router
from victor_ai_bot.api_routes.wealth import router as wealth_router
from victor_ai_bot.runtime_subsystems.replay_store import ReplayBundleStore


class _Goal:
    def __init__(self):
        self.target_return_percentage = 8.0
        self.time_horizon_seconds = 14 * 86400
        self.risk_tolerance = "moderate"
        self.max_drawdown_pct = 12.0
        self.capital_commitment_pct = 35.0


class _TreasuryCfg:
    def __init__(self):
        self.goal = _Goal()


class _Treasury:
    def __init__(self):
        self.cfg = _TreasuryCfg()

    def snapshot(self):
        return {"aggressiveness": {"current_return_pct": 4.25}}

    def _save_goal(self):
        return None


class _Runtime:
    def __init__(self):
        class _RFT:
            enabled = False
            episode_export_enabled = True
            snapshot_top_k = 20
            enable_reward_trace_export = True
            grader_weights = {}

        class _Execution:
            rft = _RFT()

        class _Cfg:
            execution = _Execution()

        self.cfg = _Cfg()
        self._treasury = _Treasury()
        self._cc = None



def _write_bundle(data_dir: Path):
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
            "risk": {"caps": {"maxDailyLossPct": 3.0, "maxExposurePct": 80.0, "sandboxCapPct": 10.0, "probationCapPct": 2.5}, "breakers": {}},
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



def test_rft_sample_endpoint_returns_episode(tmp_path: Path):
    data_dir = tmp_path / "data"
    _write_bundle(data_dir)
    os.environ["VICTOR_DATA_DIR"] = str(data_dir)
    app = FastAPI()
    app.include_router(rft_router)
    client = TestClient(app)
    res = client.get("/api/rft/episodes/sample?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert len(body["items"]) == 1
    assert body["items"][0]["context"]["opportunity_id"] == "opp-1"



def test_wealth_goal_endpoint_returns_goal_and_recommendation():
    app = FastAPI()
    app.include_router(wealth_router)
    app.state.runtime = _Runtime()
    client = TestClient(app)
    res = client.get("/api/wealth/goal")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["goal"]["risk_tolerance"] == "moderate"
    assert body["recommendation"]["target_return_pct"] >= 8.0
