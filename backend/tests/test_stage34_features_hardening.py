from types import SimpleNamespace

import pytest

from victor_ai_bot.features import build_features


class _BoomMeta:
    @property
    def meta(self):
        raise RuntimeError("meta_bug")


class _BadLegs:
    @property
    def legs(self):
        raise RuntimeError("legs_bug")


class _BadInt:
    def __str__(self):
        raise RuntimeError("int_bug")



def _opp(*, amount_in='100', dex='univ3', meta=None):
    leg = SimpleNamespace(amount_in=amount_in, dex=dex)
    return SimpleNamespace(route=SimpleNamespace(legs=[leg]), meta=meta if meta is not None else {})



def test_build_features_expected_meta_shape_failures_degrade_safely():
    opp = _opp(meta='not-a-dict')
    fv = build_features(opp)
    assert fv.profit_after_costs_wei == 0
    assert fv.gas_cost_wei == 0
    assert fv.flash_fee_wei == 0
    assert fv.has_univ3 == 1



def test_build_features_expected_leg_shape_failures_degrade_safely():
    opp = SimpleNamespace(route=SimpleNamespace(legs=[object()]), meta={})
    fv = build_features(opp)
    assert fv.legs == 1
    assert fv.has_univ3 == 0
    assert fv.has_curve == 0
    assert fv.has_balancer == 0



def test_build_features_unexpected_meta_bug_is_not_swallowed():
    with pytest.raises(RuntimeError, match='meta_bug'):
        build_features(_BoomMeta())



def test_build_features_unexpected_leg_bug_is_not_swallowed():
    opp = SimpleNamespace(route=_BadLegs(), meta={})
    with pytest.raises(RuntimeError, match='legs_bug'):
        build_features(opp)



def test_build_features_unexpected_int_bug_is_not_swallowed():
    opp = _opp(amount_in=_BadInt(), meta={"safety": {"profit_after_costs_wei": '5'}})
    with pytest.raises(RuntimeError, match='int_bug'):
        build_features(opp)



def test_build_features_uses_verified_meta_profit_after_costs_when_safety_missing():
    opp = _opp(meta={"profit_after_costs": "7", "safety": {"gas_cost_wei": "2", "flashloan_fee_wei": "1"}})
    fv = build_features(opp)
    assert fv.profit_after_costs_wei == 7
    assert fv.gas_cost_wei == 2
    assert fv.flash_fee_wei == 1


def test_build_features_zeros_mismatched_profit_after_costs_truth():
    opp = _opp(meta={"profit_after_costs": "7", "safety": {"profit_after_costs_wei": "9"}})
    fv = build_features(opp)
    assert fv.profit_after_costs_wei == 0
