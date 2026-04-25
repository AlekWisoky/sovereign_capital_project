from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from victor_ai_bot.fioa.config import FIOAConfig
from victor_ai_bot.fioa.runtime import FIOARuntime


class _ExplodingRegistry:
    def set_suspended(self, agent_id: str, suspended: bool, *, reason: str) -> None:
        raise RuntimeError(f"registry down for {agent_id}:{suspended}:{reason}")


class _ExplodingSuperstructure:
    def __init__(self):
        self.registry = _ExplodingRegistry()


class _SuccessfulBankroll:
    def success_rate_pct(self) -> float:
        return 95.0


class _SizingRuntime:
    def __init__(self):
        self._bankroll = _SuccessfulBankroll()
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(base_borrow_amount="100"),
            safety=SimpleNamespace(max_borrow_amount="500"),
        )

    def set_settings(self, **kwargs):
        raise RuntimeError(f"settings unavailable:{kwargs}")


class _AutonomyRuntime:
    def set_settings(self, **kwargs):
        raise RuntimeError(f"auto-trading update failed:{kwargs}")

    def superstructure_force_safe_mode(self, *, ttl_s: float, reason: str) -> None:
        raise RuntimeError(f"safe-mode propagation failed:{ttl_s}:{reason}")


class _MissingMetricsRuntime:
    def __init__(self):
        self.cfg = SimpleNamespace(
            execution=SimpleNamespace(max_pending_txs="x"),
            safety=SimpleNamespace(max_borrow_amount="0"),
        )
        self.metrics = object()
        self.rpc_manager = SimpleNamespace(snapshot=lambda: (_ for _ in ()).throw(RuntimeError("rpc down")))
        self._pending = object()



def test_fioa_runtime_registry_sync_failure_is_explicitly_reported(tmp_path: Path):
    runtime = FIOARuntime(
        cfg=FIOAConfig(enabled=True),
        chain="eth",
        data_dir=str(tmp_path),
        superstructure=_ExplodingSuperstructure(),
    )

    runtime.restrict_agent("agent-1", reason="policy")
    state = runtime.state()
    assert state["restricted"]["agent-1"]["reason"] == "policy"
    assert state["runtime"]["registry_sync"]["ok"] is False
    assert state["runtime"]["registry_sync"]["last_error_code"] == "registry_suspend_failed"

    runtime.resume_agent("agent-1")
    report = runtime.governance_report(limit_audit=10)
    assert report["runtime"]["registry_sync"]["ok"] is False
    assert report["runtime"]["registry_sync"]["last_error_code"] == "registry_resume_failed"



def test_fioa_runtime_sizing_failure_is_explicitly_reported(tmp_path: Path):
    cfg = FIOAConfig(enabled=True)
    cfg.enable_dynamic_sizing = True
    runtime = FIOARuntime(cfg=cfg, chain="eth", data_dir=str(tmp_path))

    runtime._rebalance_capital_allocation(_SizingRuntime())

    state = runtime.state()["runtime"]["sizing"]
    assert state["ok"] is False
    assert state["last_error_code"] == "sizing_update_failed"
    assert state["last_old_base"] == 100
    assert state["last_new_base"] > 100



def test_fioa_runtime_autonomy_and_stress_failures_are_explicitly_reported(tmp_path: Path):
    runtime = FIOARuntime(cfg=FIOAConfig(enabled=True), chain="eth", data_dir=str(tmp_path))

    runtime._limit_agent_autonomy(_AutonomyRuntime(), reason="stress")
    state = runtime.state()["runtime"]
    assert state["settings_update"]["ok"] is False
    assert state["settings_update"]["last_error_code"] == "settings_superstructure_safe_mode_failed"

    stress = runtime._calculate_system_stress(_MissingMetricsRuntime())
    assert 0.0 <= stress <= 1.0
    state = runtime.state()["runtime"]
    assert state["stress_inputs"]["ok"] is False
    assert state["stress_inputs"]["last_error_code"] == "stress_fail_streak_unavailable"
