from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

from fastapi.testclient import TestClient

from victor_ai_bot.api import router as api_router
from victor_ai_bot.api_legacy import router as legacy_router
from victor_ai_bot.server import app
import victor_ai_bot.api_routes.ops_routes as ops_routes


OPS_ROUTES = {
    ("GET", "/api/arbitrage/state"),
    ("POST", "/api/arbitrage/start"),
    ("POST", "/api/arbitrage/stop"),
    ("GET", "/api/mev/state"),
    ("POST", "/api/mev/start"),
    ("POST", "/api/mev/stop"),
    ("GET", "/api/meta/state"),
    ("POST", "/api/meta/start"),
    ("POST", "/api/meta/stop"),
    ("POST", "/api/meta/generate"),
    ("POST", "/api/meta/apply"),
    ("POST", "/api/safety"),
    ("GET", "/api/gas/presets"),
    ("POST", "/api/opportunities/trade"),
    ("POST", "/api/opportunities/simulate"),
    ("POST", "/api/tx/receipt"),
    ("GET", "/api/pnl/summary"),
    ("GET", "/api/pnl/income"),
    ("GET", "/api/presets"),
    ("GET", "/api/presets/{chain}/{name}"),
    ("POST", "/api/presets/apply"),
    ("GET", "/api/admin/state"),
}


class _FakeTask:
    def done(self) -> bool:
        return False


class _OpsRuntime:
    def __init__(self):
        gas_presets = SimpleNamespace(
            standard_max_fee_gwei=50,
            standard_priority_fee_gwei=2,
            fast_max_fee_gwei=70,
            fast_priority_fee_gwei=3,
            instant_max_fee_gwei=90,
            instant_priority_fee_gwei=4,
        )
        execution = SimpleNamespace(
            gas_mode="fast",
            auto_reinvest_enabled=True,
            reinvest_rate=25,
            gas_presets=gas_presets,
        )
        safety = SimpleNamespace(
            minProfitAbs="100",
            minProfitBps=10,
            slippage_bps=20,
            max_borrow_amount="1000",
            require_estimate_gas=True,
            require_simulation=True,
        )
        self.cfg = SimpleNamespace(execution=execution, safety=safety)
        self._auto_trading = True
        self.calls: list[tuple[str, object]] = []
        self._bankroll = SimpleNamespace(cfg=SimpleNamespace(max_borrow_amount_wei=0))
        self._task = _FakeTask()
        self._ws_clients = []

    def arbitrage_state(self):
        return {"ok": True, "enabled": True, "engine": "arb"}

    def arbitrage_start(self):
        self.calls.append(("arbitrage_start", None))
        return True

    async def arbitrage_stop(self):
        self.calls.append(("arbitrage_stop", None))
        return True

    def mev_state(self):
        return {"ok": True, "enabled": True, "engine": "mev"}

    def mev_start(self):
        self.calls.append(("mev_start", None))
        return True

    async def mev_stop(self):
        self.calls.append(("mev_stop", None))
        return True

    def meta_state(self):
        return {"ok": True, "enabled": True, "engine": "meta"}

    def meta_start(self):
        self.calls.append(("meta_start", None))
        return True

    async def meta_stop(self):
        self.calls.append(("meta_stop", None))
        return True

    def meta_generate(self):
        self.calls.append(("meta_generate", None))
        return {"ok": True, "candidates": 1}

    def meta_apply(self, cand_id: str):
        self.calls.append(("meta_apply", cand_id))
        return {"ok": True, "id": cand_id}

    async def execute_opportunity_by_id(self, opp_id: str, **kwargs):
        self.calls.append(("execute", {"id": opp_id, **kwargs}))
        return SimpleNamespace(
            ok=True, dry_run=True, reason="ok", tx_hash=None, plan={"id": opp_id}
        )

    async def poll_and_update_receipt(self, tx_hash: str):
        self.calls.append(("receipt", tx_hash))
        return {"ok": True, "tx_hash": tx_hash, "status": "confirmed"}

    async def pnl_summary(self, window: int = 50):
        self.calls.append(("pnl_summary", window))
        return {"window": window, "realized": "123"}

    async def pnl_income(self, window: int = 3600):
        self.calls.append(("pnl_income", window))
        return {"ok": True, "window": window, "income": []}

    async def admin_snapshot(self):
        return {
            "chain": "base",
            "metrics": {
                "last_block": 123,
                "scan_ms": 42,
                "send_mode": "private",
                "gas_mode": "fast",
                "realized_profit_raw": "123",
                "efficiency_pct": 91.0,
                "success_rate_pct": 87.0,
            },
            "opportunities": [],
            "rpc": {"read": [], "send": []},
            "errors": [],
            "exec_log": [],
            "efficiency": {},
            "pnl_summary": {},
        }


def test_api_legacy_no_longer_declares_ops_routes():
    mounted = set()
    for route in getattr(legacy_router, "routes", []) or []:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        for method in methods:
            mounted.add((method, path))
    assert mounted.isdisjoint(OPS_ROUTES)


def test_public_app_mounts_single_copy_of_each_ops_route_from_canonical_module():
    counts: Counter[tuple[str, str]] = Counter()
    modules: dict[tuple[str, str], list[str]] = {}
    for route in app.routes:
        path = str(getattr(route, "path", "") or "")
        methods = [
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        ]
        module = str(getattr(getattr(route, "endpoint", None), "__module__", "") or "")
        for method in methods:
            key = (method, path)
            counts[key] += 1
            modules.setdefault(key, []).append(module)
    for key in OPS_ROUTES:
        assert counts[key] == 1
        assert modules[key] == ["victor_ai_bot.api_routes.ops_routes"]


def test_ops_routes_use_canonical_module(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OpsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    assert client.get("/api/arbitrage/state").json()["engine"] == "arb"
    assert "auto_trade_recovery" in client.get("/api/arbitrage/state").json()
    assert client.get("/api/mev/state").json()["engine"] == "mev"
    assert "auto_trade_recovery" in client.get("/api/mev/state").json()
    assert client.get("/api/meta/state").json()["engine"] == "meta"
    assert "auto_trade_recovery" in client.get("/api/meta/state").json()
    assert client.get("/api/gas/presets").json()["current_mode"] == "fast"

    meta_generate = client.post("/api/meta/generate", headers={"X-Admin-Key": "secret"})
    meta_apply = client.post(
        "/api/meta/apply",
        json={"id": "cand-1"},
        headers={"X-Admin-Key": "secret"},
    )
    simulate = client.post(
        "/api/opportunities/simulate",
        json={"id": "opp-1"},
        headers={"X-Admin-Key": "secret"},
    )
    receipt = client.post(
        "/api/tx/receipt",
        json={"tx_hash": "0xabc"},
        headers={"X-Admin-Key": "secret"},
    )
    pnl_summary = client.get("/api/pnl/summary")
    pnl_income = client.get("/api/pnl/income")
    presets = client.get("/api/presets")
    admin = client.get("/api/admin/state")

    assert meta_generate.json()["candidates"] == 1
    assert meta_apply.json()["id"] == "cand-1"
    assert simulate.json()["plan"]["id"] == "opp-1"
    assert receipt.json()["status"] == "confirmed"
    assert pnl_summary.json()["summary"]["window"] == 50
    assert pnl_income.json()["window"] == 3600
    assert presets.json()["ok"] is True
    assert admin.json()["settings"]["auto_trading"] is True
    assert admin.json()["summaryContract"]["truthFamily"] == "admin_state"
    assert admin.json()["summaryContract"]["readModel"] == "admin_state_projection_v1"
    assert ("meta_apply", "cand-1") in runtime.calls


class _OpsUnavailableRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(gas_presets=SimpleNamespace()), safety=SimpleNamespace()
        )


def test_ops_route_unavailable_defaults_are_canonical_and_explicit(monkeypatch):
    runtime = _OpsUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    mev = client.get("/api/mev/state").json()
    meta = client.get("/api/meta/state").json()

    assert mev["ok"] is False
    assert mev["enabled"] is False
    assert mev["reason"] == "unavailable"
    assert mev["status"] == "unavailable"
    assert mev["reason_code"] == "unavailable"

    assert meta["ok"] is False
    assert meta["enabled"] is False
    assert meta["reason"] == "meta_unavailable"
    assert meta["status"] == "unavailable"
    assert meta["reason_code"] == "meta_unavailable"


def test_meta_route_action_unavailable_defaults_are_explicit(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OpsUnavailableRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    generated = client.post("/api/meta/generate", headers={"X-Admin-Key": "secret"}).json()
    applied = client.post(
        "/api/meta/apply", json={"id": "cand-1"}, headers={"X-Admin-Key": "secret"}
    ).json()

    assert generated == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "meta_unavailable",
        "reason": "meta_unavailable",
        "error": "meta_unavailable",
        "candidates": [],
    }
    assert applied == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "meta_unavailable",
        "reason": "meta_unavailable",
        "error": "meta_unavailable",
        "id": "cand-1",
    }


def test_update_safety_uses_canonical_boolean_parsing_and_rejects_ambiguous_values(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OpsRuntime()
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    accepted = client.post(
        "/api/safety",
        json={"require_estimate_gas": "false", "require_simulation": "yes"},
        headers={"X-Admin-Key": "secret"},
    )
    assert accepted.json() == {"ok": True}
    assert runtime.cfg.safety.require_estimate_gas is False
    assert runtime.cfg.safety.require_simulation is True

    rejected = client.post(
        "/api/safety",
        json={"minProfitBps": 25, "require_estimate_gas": "definitely"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert rejected["ok"] is False
    assert rejected["status"] == "invalid"
    assert rejected["reason_code"] == "invalid_boolean_value"
    assert rejected["details"]["field"] == "require_estimate_gas"
    assert runtime.cfg.safety.minProfitBps == 10
    assert runtime.cfg.safety.require_estimate_gas is False


def test_update_safety_rejects_invalid_numeric_values_without_partial_mutation(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OpsRuntime()
    runtime.cfg.safety.minProfitAbs = "100"
    runtime.cfg.safety.minProfitBps = 10
    runtime.cfg.safety.slippage_bps = 20
    runtime.cfg.safety.max_borrow_amount = "1000"
    runtime._bankroll.cfg.max_borrow_amount_wei = 1000
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    rejected = client.post(
        "/api/safety",
        json={"minProfitAbs": "250", "slippage_bps": "not-a-number"},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert rejected["ok"] is False
    assert rejected["status"] == "invalid"
    assert rejected["reason_code"] == "invalid_integer_value"
    assert rejected["details"]["field"] == "slippage_bps"
    assert runtime.cfg.safety.minProfitAbs == "100"
    assert runtime.cfg.safety.slippage_bps == 20


class _FailingBankrollCfg:
    def __init__(self, max_borrow_amount_wei: int):
        self._max_borrow_amount_wei = max_borrow_amount_wei

    @property
    def max_borrow_amount_wei(self) -> int:
        return self._max_borrow_amount_wei

    @max_borrow_amount_wei.setter
    def max_borrow_amount_wei(self, value: int) -> None:
        raise RuntimeError("bankroll_write_failed")


class _OpsRuntimeWithFailingBankroll(_OpsRuntime):
    def __init__(self):
        super().__init__()
        self._bankroll = SimpleNamespace(cfg=_FailingBankrollCfg(777))


def test_update_safety_fails_closed_when_bankroll_sync_fails(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    runtime = _OpsRuntimeWithFailingBankroll()
    runtime.cfg.safety.max_borrow_amount = "1000"
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)
    client = TestClient(app)

    rejected = client.post(
        "/api/safety",
        json={"max_borrow_amount": "2500", "require_simulation": "false"},
        headers={"X-Admin-Key": "secret"},
    ).json()

    assert rejected == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "safety_update_failed",
        "reason": "safety_update_failed",
        "error": "safety_update_failed",
    }
    assert runtime.cfg.safety.max_borrow_amount == "1000"
    assert runtime.cfg.safety.require_simulation is True
    assert runtime._bankroll.cfg.max_borrow_amount_wei == 777


class _PresetTask:
    def __init__(self):
        self._done = False

    def done(self) -> bool:
        return self._done


class _PresetOldRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(chain=SimpleNamespace(name="old-chain"))
        self._task = _PresetTask()
        self._ws_clients = ["ws"]
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


class _PresetNewRuntime:
    def __init__(self, cfg):
        self.cfg = cfg
        self.started = False
        self._ws_clients = None

    def start(self):
        self.started = True


def test_presets_apply_uses_canonical_boolean_parsing(monkeypatch):
    monkeypatch.setenv("VICTOR_ADMIN_KEY", "secret")
    old_runtime = _PresetOldRuntime()
    monkeypatch.setattr(app.state, "runtime", old_runtime, raising=False)

    created = {}

    def fake_find_preset_path(chain: str, name: str):
        return f"/tmp/{chain}-{name}.yaml"

    def fake_load_config(path: str):
        created["path"] = path
        return SimpleNamespace(chain=SimpleNamespace(name="base"))

    def fake_runtime_bundle(cfg):
        rt = _PresetNewRuntime(cfg)
        created["runtime"] = rt
        return rt

    monkeypatch.setattr(ops_routes, "find_preset_path", fake_find_preset_path)
    monkeypatch.setattr(ops_routes, "load_config", fake_load_config)
    monkeypatch.setattr(ops_routes, "RuntimeBundle", fake_runtime_bundle)

    client = TestClient(app)

    accepted = client.post(
        "/api/presets/apply",
        json={"chain": "base", "name": "default", "auto_start": "false"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert accepted["ok"] is True
    assert accepted["active_chain"] == "base"
    assert old_runtime.stop_calls == 1
    assert created["runtime"].started is False
    assert getattr(created["runtime"], "_ws_clients") == ["ws"]

    old_runtime_2 = _PresetOldRuntime()
    monkeypatch.setattr(app.state, "runtime", old_runtime_2, raising=False)
    rejected = client.post(
        "/api/presets/apply",
        json={"chain": "base", "name": "default", "auto_start": "later"},
        headers={"X-Admin-Key": "secret"},
    ).json()
    assert rejected["ok"] is False
    assert rejected["status"] == "invalid"
    assert rejected["reason_code"] == "invalid_boolean_value"
    assert rejected["details"]["field"] == "auto_start"
    assert old_runtime_2.stop_calls == 0
