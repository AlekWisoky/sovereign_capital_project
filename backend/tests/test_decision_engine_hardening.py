from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import victor_ai_bot.aqe as aqe_module
import victor_ai_bot.decision_engine as decision_module
from victor_ai_bot.decision_engine import DecisionEngine


class _Leg:
    def __init__(self, dex: str, amount_in: int):
        self.dex = dex
        self.amount_in = amount_in


class _Route:
    def __init__(self, legs):
        self.legs = legs


class _Opp:
    def __init__(
        self,
        *,
        opp_id: str,
        amount_in: int,
        profit_after: int,
        gas_cost: int,
        exec_ready: bool = True,
        meta_profit_after: int | None = None,
        capital_required_wei: int | None = None,
        strategy_family: str = "flashloan_atomic",
        profitability: dict | None = None,
        post_mutation_revalidation: dict | None = None,
    ):
        self.id = opp_id
        self.route_id = f"r_{opp_id}"
        self.can_execute = True
        self.route = _Route([_Leg("univ3", amount_in), _Leg("balancer", amount_in)])
        self.meta = {
            "safety": {
                "profit_after_costs_wei": int(profit_after),
                "gas_cost_wei": int(gas_cost),
                "flashloan_fee_wei": 0,
                "exec_ready": bool(exec_ready),
            },
            "overlay": {"score_multiplier": 1.0},
            "strategy_family": str(strategy_family),
        }
        if meta_profit_after is not None:
            self.meta["profit_after_costs"] = int(meta_profit_after)
        if capital_required_wei is not None:
            self.meta["capital_required_wei"] = int(capital_required_wei)
        if profitability is not None:
            self.meta["profitability"] = dict(profitability)
        if post_mutation_revalidation is not None:
            self.meta["post_mutation_revalidation"] = dict(post_mutation_revalidation)


class _FakeSmmaeConfig:
    def __init__(self, *, mixer: str, explore_prob: float):
        self.mixer = mixer
        self.explore_prob = explore_prob


class _FakeSmmaeAction:
    gas_mode = "fast"
    size_mult = 0.5
    borrow_mult = 1.0

    def key(self) -> str:
        return "fake_smmae"


class _FakeSmmaeEngine:
    def __init__(self, *, cfg, data_dir: str):
        self.cfg = cfg
        self.data_dir = data_dir
        self.last_info = {}
        self.last_reward = {}

    def choose_action(self, *, state, state_key):
        return _FakeSmmaeAction(), {"state_key": str(state_key), "route_id": state.get("route_id")}


class _FailingSmmaeObserver:
    cfg = SimpleNamespace(mixer="vdn")
    last_info = {}
    last_reward = {}

    def observe_trade_result(self, **kwargs):
        raise RuntimeError("observer unavailable")


class _FailingReliability:
    def observe(self, *, row):
        raise RuntimeError("reliability unavailable")


class _FailingXai:
    audit = SimpleNamespace(
        log=lambda expl: (_ for _ in ()).throw(RuntimeError("audit unavailable"))
    )

    def build(self, **kwargs):
        raise RuntimeError("xai unavailable")


class _Cfg(SimpleNamespace):
    pass


def _build_cfg(*, brain_mode: str = "auto") -> _Cfg:
    cfg = _Cfg()
    cfg.execution = SimpleNamespace(
        brain_mode=brain_mode,
        trade_cooldown_blocks=0,
        max_pending_txs=1,
        min_p_success=0.70,
        max_submit_per_block=1,
        gas_mode="standard",
        gas_presets=None,
    )
    cfg.safety = SimpleNamespace(max_borrow_amount="0")
    return cfg


def test_decision_engine_has_no_broad_exception_handlers():
    source = Path(decision_module.__file__).read_text(encoding="utf-8")
    assert "except Exception" not in source
    assert "\n        except:\n" not in source


def test_decision_engine_smmae_mode_uses_self_data_dir(monkeypatch, tmp_path):
    created = {}

    class _CapturingSmmaeEngine(_FakeSmmaeEngine):
        def __init__(self, *, cfg, data_dir: str):
            super().__init__(cfg=cfg, data_dir=data_dir)
            created["data_dir"] = data_dir

    monkeypatch.setattr(aqe_module, "SMMAEConfig", _FakeSmmaeConfig)
    monkeypatch.setattr(aqe_module, "SMMAEEngine", _CapturingSmmaeEngine)

    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="smmae_auto")
    decision = eng.annotate_and_decide(
        [_Opp(opp_id="1", amount_in=10**18, profit_after=10**15, gas_cost=2 * 10**14)],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="smmae_auto"),
    )

    assert created["data_dir"] == str(tmp_path)
    assert decision.action == "trade"
    assert decision.gas_mode == "fast"


def test_on_trade_result_contains_optional_observer_failures(monkeypatch, tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    eng._smmae = _FailingSmmaeObserver()
    monkeypatch.setattr(
        decision_module, "reliability_tracker", lambda **kwargs: _FailingReliability()
    )
    monkeypatch.setattr(decision_module, "xai_engine", lambda **kwargs: _FailingXai())

    eng.on_trade_result(
        route_id="route-1",
        rl_state="bucket",
        rl_action_index=0,
        amount_in_wei=10**18,
        expected_after_costs_wei=10**15,
        realized_after_gas_wei=9 * 10**14,
        ok=True,
        tx_hash="0xabc",
        extra={"mode": "auto", "brain": {}, "aqe_debug": {}},
    )

    assert eng._route_stats["route-1"]["trials"] == 1
    assert eng._last_reward_trace["ok"] is True


def test_on_trade_result_propagates_unexpected_programmer_bug(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    eng.rl.update = lambda *args, **kwargs: (_ for _ in ()).throw(ZeroDivisionError("bad update"))

    with pytest.raises(ZeroDivisionError):
        eng.on_trade_result(
            route_id="route-1",
            rl_state="bucket",
            rl_action_index=0,
            amount_in_wei=10**18,
            expected_after_costs_wei=10**15,
            realized_after_gas_wei=9 * 10**14,
            ok=True,
            tx_hash="0xabc",
            extra={"mode": "auto", "brain": {}, "aqe_debug": {}},
        )


def test_decision_engine_treats_route_invalid_exec_ready_opp_as_not_executable(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    opp = _Opp(opp_id="1", amount_in=10**18, profit_after=10**15, gas_cost=2 * 10**14)
    opp.meta["execution_route_plan"] = {
        "executable": False,
        "route_invalid_causes": ["leg:0:venue-a:invalid"],
    }

    decision = eng.annotate_and_decide(
        [opp],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
    )

    assert decision.action == "skip"
    assert opp.meta["brain"]["reason"] == "not_executable"


def test_decision_engine_prefers_route_ready_opp_over_higher_ev_route_invalid_opp(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    invalid = _Opp(opp_id="invalid", amount_in=10**18, profit_after=2 * 10**15, gas_cost=2 * 10**14)
    invalid.meta["execution_route_plan"] = {
        "executable": False,
        "route_invalid_causes": ["leg:0:venue-a:invalid"],
    }
    valid = _Opp(opp_id="valid", amount_in=10**18, profit_after=8 * 10**14, gas_cost=2 * 10**14)

    decision = eng.annotate_and_decide(
        [invalid, valid],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
    )

    assert decision.action == "trade"
    assert decision.opp_id == "valid"


def test_decision_engine_treats_profit_after_costs_mismatch_as_not_executable(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    opp = _Opp(
        opp_id="1",
        amount_in=10**18,
        profit_after=10**15,
        meta_profit_after=2 * 10**15,
        gas_cost=2 * 10**14,
    )

    decision = eng.annotate_and_decide(
        [opp],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
    )

    assert decision.action == "skip"
    assert opp.meta["brain"]["reason"] == "not_executable"


def test_decision_engine_treats_stale_canonical_profitability_as_not_executable(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    opp = _Opp(
        opp_id="stale",
        amount_in=10**18,
        profit_after=10**15,
        gas_cost=2 * 10**14,
        profitability={
            "stage": "search",
            "source": "scan",
            "reason": "profitability_metadata_stale",
            "revalidated": False,
            "stale": True,
            "valid": False,
            "authoritative": False,
            "profit_after_costs_wei": str(10**15),
        },
        post_mutation_revalidation={
            "reason_code": "route_mutated",
            "profitability": {
                "stage": "post_mutation_submission_gate",
                "source": "execution",
                "reason": "route_mutated",
                "revalidated": False,
                "stale": True,
                "valid": False,
                "authoritative": False,
                "profit_after_costs_wei": str(10**15),
            },
        },
    )

    decision = eng.annotate_and_decide(
        [opp],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
    )

    assert decision.action == "skip"
    assert opp.meta["brain"]["reason"] == "not_executable"


def test_decision_engine_treats_non_positive_after_costs_as_not_executable(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    opp = _Opp(opp_id="1", amount_in=10**18, profit_after=0, gas_cost=2 * 10**14)

    decision = eng.annotate_and_decide(
        [opp],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
    )

    assert decision.action == "skip"
    assert opp.meta["brain"]["reason"] == "not_executable"


def test_decision_engine_respects_total_capital_budget(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    heavy = _Opp(
        opp_id="heavy",
        amount_in=10**18,
        profit_after=2 * 10**15,
        gas_cost=2 * 10**14,
        capital_required_wei=2_000,
    )
    fit = _Opp(
        opp_id="fit",
        amount_in=10**18,
        profit_after=12 * 10**14,
        gas_cost=2 * 10**14,
        capital_required_wei=900,
    )

    decision = eng.annotate_and_decide(
        [heavy, fit],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
        capital_budget_remaining_wei=1_000,
    )

    assert decision.action == "trade"
    assert decision.opp_id == "fit"


def test_decision_engine_respects_family_capital_budget(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    flash_over = _Opp(
        opp_id="flash-over",
        amount_in=10**18,
        profit_after=2 * 10**15,
        gas_cost=2 * 10**14,
        capital_required_wei=2_000,
        strategy_family="flashloan_atomic",
    )
    funding_fit = _Opp(
        opp_id="funding-fit",
        amount_in=10**18,
        profit_after=11 * 10**14,
        gas_cost=2 * 10**14,
        capital_required_wei=900,
        strategy_family="funding_arb",
    )

    decision = eng.annotate_and_decide(
        [flash_over, funding_fit],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
        family_capital_remaining_wei={"flashloan_atomic": 1_000, "funding_arb": 1_000},
    )

    assert decision.action == "trade"
    assert decision.opp_id == "funding-fit"


def test_decision_engine_treats_capital_required_usd_as_budget_scale_wei(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    usd_heavy = _Opp(
        opp_id="usd-heavy",
        amount_in=10**18,
        profit_after=2 * 10**15,
        gas_cost=2 * 10**14,
        strategy_family="cross_cex_dex",
    )
    usd_heavy.capital_required_usd = 1_500.0
    fit = _Opp(
        opp_id="fit",
        amount_in=10**18,
        profit_after=12 * 10**14,
        gas_cost=2 * 10**14,
        capital_required_wei=900 * 10**18,
        strategy_family="cross_cex_dex",
    )

    decision = eng.annotate_and_decide(
        [usd_heavy, fit],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
        capital_budget_remaining_wei=1_000 * 10**18,
        family_capital_remaining_wei={"cex_dex_arb": 1_000 * 10**18},
    )

    assert decision.action == "trade"
    assert decision.opp_id == "fit"


def test_decision_engine_blocks_amount_in_only_capital_when_budget_truth_is_active(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    amount_only = _Opp(
        opp_id="amount-only",
        amount_in=5 * 10**18,
        profit_after=3 * 10**15,
        gas_cost=2 * 10**14,
        strategy_family="flashloan_atomic",
    )
    fit = _Opp(
        opp_id="fit",
        amount_in=10**18,
        profit_after=12 * 10**14,
        gas_cost=2 * 10**14,
        capital_required_wei=900 * 10**18,
        strategy_family="flashloan_atomic",
    )

    decision = eng.annotate_and_decide(
        [amount_only, fit],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
        capital_budget_remaining_wei=1_000 * 10**18,
        family_capital_remaining_wei={"flashloan_atomic": 1_000 * 10**18},
    )

    assert decision.action == "trade"
    assert decision.opp_id == "fit"


def test_decision_engine_coerces_stringified_capital_budgets_fail_closed(tmp_path):
    eng = DecisionEngine(chain_name="test", data_dir=str(tmp_path), brain_mode="auto")
    heavy = _Opp(
        opp_id="heavy",
        amount_in=10**18,
        profit_after=2 * 10**15,
        gas_cost=2 * 10**14,
        capital_required_wei=2_000,
        strategy_family="flashloan_atomic",
    )
    fit = _Opp(
        opp_id="fit",
        amount_in=10**18,
        profit_after=12 * 10**14,
        gas_cost=2 * 10**14,
        capital_required_wei=900,
        strategy_family="flashloan_atomic",
    )

    decision = eng.annotate_and_decide(
        [heavy, fit],
        current_block=123,
        pending_txs=0,
        auto_enabled=True,
        cfg=_build_cfg(brain_mode="auto"),
        capital_budget_remaining_wei="1e3",
        family_capital_remaining_wei={"flashloan_atomic": "9e2", "funding_arb": "bad"},
    )

    assert decision.action == "trade"
    assert decision.opp_id == "fit"
