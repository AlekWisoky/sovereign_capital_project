from __future__ import annotations

from victor_ai_bot.decision_engine import DecisionEngine
from victor_ai_bot.determinism import stable_hash_int
from victor_ai_bot.rl_policy import RlPolicy


class _Leg:
    def __init__(self, dex: str, amount_in: int):
        self.dex = dex
        self.amount_in = amount_in


class _Route:
    def __init__(self, legs):
        self.legs = legs


class _Opp:
    def __init__(self, *, opp_id: str, amount_in: int, profit_after: int, gas_cost: int, legs: int = 2):
        self.id = opp_id
        self.route_id = f"r_{opp_id}"
        self.can_execute = True
        self.route = _Route([_Leg("univ3", amount_in) for _ in range(legs)])
        self.meta = {
            "safety": {
                "profit_after_costs_wei": int(profit_after),
                "gas_cost_wei": int(gas_cost),
                "flashloan_fee_wei": 0,
            },
            "overlay": {"score_multiplier": 1.0},
        }


def test_stable_hash_int_is_stable():
    assert stable_hash_int("abc") == stable_hash_int("abc")
    assert stable_hash_int("abc") != stable_hash_int("abcd")


def test_rl_policy_is_deterministic_for_same_seed():
    pol = RlPolicy(path="/tmp/test_rl.json")
    s = "state_key"
    a1 = pol.select(s, seed="42")
    a2 = pol.select(s, seed="42")
    assert a1 == a2


def test_decision_engine_is_deterministic_for_same_inputs():
    eng = DecisionEngine(chain_name="test", data_dir="/tmp", brain_mode="auto")
    # Minimal cfg namespace expected by DecisionEngine
    cfg = type("Cfg", (), {})()
    cfg.execution = type("Exec", (), {"brain_mode": "auto", "min_p_success": 0.70, "route_cooldown_blocks": 0, "max_global_trades_per_block": 1})()
    cfg.safety = type("Saf", (), {"slippage_bps": 35})()
    opps1 = [_Opp(opp_id="1", amount_in=10**18, profit_after=10**15, gas_cost=2 * 10**14)]
    opps2 = [_Opp(opp_id="1", amount_in=10**18, profit_after=10**15, gas_cost=2 * 10**14)]
    d1 = eng.annotate_and_decide(opps1, current_block=123, pending_txs=0, auto_enabled=True, cfg=cfg)
    d2 = eng.annotate_and_decide(opps2, current_block=123, pending_txs=0, auto_enabled=True, cfg=cfg)
    assert d1.action == d2.action
    assert d1.opp_id == d2.opp_id
    assert d1.ev_wei == d2.ev_wei


class _BrokenMapping:
    def keys(self):
        raise TypeError("boom")


def test_stable_dict_hash_is_order_independent():
    from victor_ai_bot.determinism import stable_dict_hash

    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert stable_dict_hash(left, seed="s") == stable_dict_hash(right, seed="s")


def test_stable_dict_hash_falls_back_for_non_mapping_like_inputs():
    from victor_ai_bot.determinism import stable_dict_hash

    value = ["not", "a", "dict"]

    assert stable_dict_hash(value, seed="s") == stable_dict_hash(value, seed="s")


def test_stable_dict_hash_falls_back_for_broken_mapping():
    from victor_ai_bot.determinism import stable_dict_hash

    value = _BrokenMapping()

    assert stable_dict_hash(value, seed="s") == stable_dict_hash(value, seed="s")
