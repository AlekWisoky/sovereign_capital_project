from __future__ import annotations

from pathlib import Path

import pytest

import victor_ai_bot.aqe.core.smmae_engine as smmae_module
from victor_ai_bot.aqe.agents.base import AgentOutput
from victor_ai_bot.aqe.core.smmae_engine import SMMAEConfig, SMMAEEngine


class _SimpleAgent:
    def __init__(self, *, raise_on_update: Exception | None = None):
        self.name = "simple"
        self._raise_on_update = raise_on_update

    def act(self, *, state):
        action_key = smmae_module.actions_from_rl()[0].key()
        return AgentOutput(
            pi_team={action_key: 1.0},
            pi_self={action_key: 1.0},
            alpha=0.1,
            q_values={action_key: 1.0},
            confidence=0.9,
            info={},
        )

    def update(self, *, reward: float, features_used):
        if self._raise_on_update is not None:
            raise self._raise_on_update


class _DummyKDS:
    enabled = False

    def tick(self, *, state):
        return None

    def state(self):
        return {}

    def observe(self, *, hypothesis_id: str, ok: bool, r_total: float):
        return None


class _DummyRag:
    def __init__(self, *, attach_error: Exception | None = None, record_error: Exception | None = None):
        self._last_state = {}
        self._attach_error = attach_error
        self._record_error = record_error

    def attach_context(self, *, state):
        if self._attach_error is not None:
            raise self._attach_error
        state["Historical_Context"] = {"attached": True}

    def record_outcome(self, **kwargs):
        if self._record_error is not None:
            raise self._record_error
        return None


def _build_engine(*, agent: _SimpleAgent | None = None) -> SMMAEEngine:
    engine = SMMAEEngine(
        cfg=SMMAEConfig(intrinsic_enabled=False, adaptive_enabled=False, harmony_enabled=False),
        agents=[agent or _SimpleAgent()],
        data_dir="backend/data",
    )
    engine._kds = lambda *, chain: _DummyKDS()  # type: ignore[method-assign]
    engine.rag_ctx = _DummyRag()
    return engine


def test_smmae_choose_action_contains_safe_optional_failures(monkeypatch):
    engine = _build_engine()
    engine.rag_ctx = _DummyRag(attach_error=RuntimeError("rag unavailable"))
    engine.portfolio.aggregate = lambda agent_outputs: (_ for _ in ()).throw(RuntimeError("portfolio unavailable"))
    monkeypatch.setattr(smmae_module.BUS, "snapshot", lambda: (_ for _ in ()).throw(RuntimeError("bus unavailable")))

    action, debug = engine.choose_action(state={"S_global": {}}, state_key="safe-fallback")

    assert action.key() == debug["chosen_action"]
    assert debug["portfolio"] == {}
    assert debug["kds"]["enabled"] is False


def test_smmae_choose_action_propagates_unexpected_programmer_bug():
    engine = _build_engine()
    engine.rag_ctx = _DummyRag(attach_error=ZeroDivisionError("unexpected bug"))

    with pytest.raises(ZeroDivisionError):
        engine.choose_action(state={"S_global": {}}, state_key="unexpected-bug")


def test_smmae_observe_trade_result_propagates_unexpected_agent_bug(monkeypatch):
    agent = _SimpleAgent(raise_on_update=ZeroDivisionError("bad update"))
    engine = _build_engine(agent=agent)
    monkeypatch.setattr(smmae_module.BUS, "snapshot", lambda: {})

    engine.intrinsic = type("_DummyIntrinsic", (), {
        "intrinsic": staticmethod(lambda **kwargs: {"r_intrinsic": 0.0, "components": {}}),
        "combine": staticmethod(lambda *, r_team, r_intrinsic: float(r_team) + float(r_intrinsic)),
    })()
    engine.choose_action(state={"S_global": {}}, state_key="reward")

    with pytest.raises(ZeroDivisionError):
        engine.observe_trade_result(state_key="reward", action_key=engine._last_chosen_action, r_team=1.0, ok=True)


def test_smmae_engine_has_no_broad_exception_handlers():
    source = Path(smmae_module.__file__).read_text(encoding="utf-8")
    assert "except Exception" not in source
    assert "\n        except:\n" not in source
