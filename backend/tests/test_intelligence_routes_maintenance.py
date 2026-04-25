from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.runtime import MultiRuntimeBundle, RuntimeBundle
from victor_ai_bot.server import app
import victor_ai_bot.api_routes.intelligence_routes as intelligence_routes


class _FakeAudit:
    def __init__(self, chain: str):
        self._chain = chain

    def latest(self, limit: int):
        return [{"id": f"{self._chain}-{i}", "ts": float(limit - i)} for i in range(min(limit, 2))]

    def get(self, decision_id: str):
        return {"id": str(decision_id), "chain": self._chain}


class _FakeXaiEngine:
    def __init__(self, chain: str):
        self.audit = _FakeAudit(chain)


class _FakeReliabilityTracker:
    def __init__(self, chain: str):
        self._chain = chain

    def state(self):
        return {"ok": True, "chain": self._chain, "reliability": 0.99}


class _FakeKdsEngine:
    def __init__(self, chain: str):
        self._chain = chain

    def state(self):
        return {"ok": True, "chain": self._chain, "mode": "observe"}


class _FakeRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="base"),
            safety=SimpleNamespace(slippage_bps=42, minProfitBps=7),
        )
        self._opps = [
            SimpleNamespace(
                id="opp-1",
                strategy="flash_arb",
                meta={
                    "margin_ratio": 1.25,
                    "brain": {"p_success": 0.91, "ev_wei": "123", "gas_mode": "fast"},
                    "overlay": {
                        "regime_label": "TRENDING",
                        "consensus_score": 0.77,
                        "mev_risk": 0.11,
                    },
                    "safety": {"slippage_bps": 12},
                    "intent_id": "intent-7",
                },
                route=SimpleNamespace(legs=[1, 2]),
            )
        ]

    async def pnl_summary(self, *, window: int):
        return {"window": int(window), "realized": "9.1"}

    def behaveagent_state(self):
        return {"ok": True, "confidence": 0.63}

    def blockspace_state(self):
        return {"ok": True, "lane": "private"}


class _FakeMultiRuntime:
    def chains(self):
        return ["base", "arbitrum"]


def _install_fakes(monkeypatch):
    monkeypatch.setattr(
        intelligence_routes,
        "xai_engine",
        lambda *, data_dir, chain: _FakeXaiEngine(str(chain)),
    )
    monkeypatch.setattr(
        intelligence_routes,
        "reliability_tracker",
        lambda *, data_dir, chain: _FakeReliabilityTracker(str(chain)),
    )
    monkeypatch.setattr(
        intelligence_routes,
        "kds_engine",
        lambda *, data_dir, chain: _FakeKdsEngine(str(chain)),
    )
    monkeypatch.setattr(
        intelligence_routes,
        "BUS",
        SimpleNamespace(snapshot=lambda: {"behaveagent": {"confidence": 0.88}}),
    )


def test_intelligence_routes_use_canonical_module(monkeypatch):
    _install_fakes(monkeypatch)
    runtime = _FakeRuntime()
    app.dependency_overrides[RuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        latest = client.get("/api/xai/latest?limit=2")
        decision = client.get("/api/xai/decision/dec-1")
        reliability = client.get("/api/reliability/state")
        kds = client.get("/api/kds/state")
        explain = client.get("/api/inl/explain/opportunity/opp-1")
        scenario = client.post(
            "/api/inl/scenario_sweep",
            json={
                "changes": [
                    {"slippage_bps": 55, "minProfitBps": 8},
                    {"slippage_bps": "bad"},
                ]
            },
        )
        digest = client.get("/api/inl/daily_digest")

        assert latest.status_code == 200
        assert latest.json()["items"][0]["id"] == "base-0"
        assert decision.json()["item"]["id"] == "dec-1"
        assert reliability.json()["state"]["chain"] == "base"
        assert kds.json()["state"]["mode"] == "observe"
        body = explain.json()
        assert body["strategy"] == "flash_arb"
        assert body["why_this_strategy"]["legs"] == 2
        assert body["show_regime_confidence"]["confidence"] == 0.88
        assert body["intent_id"] == "intent-7"
        assert scenario.json()["scenarios"] == [
            {"slippage_bps": 55, "minProfitBps": "8", "note": "sweep_stub"}
        ]
        digest_body = digest.json()
        assert digest_body["pnl"]["window"] == 100
        assert digest_body["behaveagent"]["confidence"] == 0.63
        assert digest_body["blockspace"]["lane"] == "private"
    finally:
        app.dependency_overrides.pop(RuntimeBundle.dep, None)


def test_intelligence_multichain_routes_use_canonical_module(monkeypatch):
    _install_fakes(monkeypatch)
    runtime = _FakeMultiRuntime()
    app.dependency_overrides[MultiRuntimeBundle.dep] = lambda request=None: runtime
    client = TestClient(app)
    try:
        latest = client.get("/api/xai/multichain/latest?limit=4")
        reliability = client.get("/api/reliability/multichain/state")
        kds = client.get("/api/kds/multichain/state")

        assert latest.status_code == 200
        items = latest.json()["items"]
        assert {item["id"].split("-")[0] for item in items} == {"base", "arbitrum"}
        assert reliability.json()["states"]["base"]["reliability"] == 0.99
        assert reliability.json()["states"]["arbitrum"]["chain"] == "arbitrum"
        assert kds.json()["states"]["base"]["mode"] == "observe"
        assert kds.json()["states"]["arbitrum"]["chain"] == "arbitrum"
    finally:
        app.dependency_overrides.pop(MultiRuntimeBundle.dep, None)
