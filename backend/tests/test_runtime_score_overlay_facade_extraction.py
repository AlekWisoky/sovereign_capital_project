from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_score_overlay_facade import RuntimeScoreOverlayFacade

EXTRACTED_METHODS = {
    '_score_overlay_priorities',
    '_score_overlay_consensus',
    '_apply_score_overlays',
}


class _BrokenOpp:
    def __init__(self):
        self.meta = {'existing': True}

    @property
    def route(self):
        raise RuntimeError('boom')


class _Runtime(RuntimeScoreOverlayFacade):
    def __init__(self):
        self._consensus_last = {}


def _opp(*, legs=2, meta=None):
    return SimpleNamespace(
        route=SimpleNamespace(legs=[object()] * legs),
        meta=dict(meta or {}),
    )


def test_runtime_bundle_inherits_extracted_score_overlay_facade():
    assert issubclass(RuntimeBundle, RuntimeScoreOverlayFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_score_overlay_facade_preserves_overlay_annotations():
    runtime = _Runtime()
    runtime._consensus_last = {'consensus_score': 0.77, 'allow': True}
    opp_three_leg = _opp(legs=3)
    opp_two_leg = _opp(legs=2)

    runtime._apply_score_overlays(
        opps=[opp_three_leg, opp_two_leg],
        behave_state={
            'strategy_priority_matrix': {
                'dex_flash_3leg': 0.9,
                'dex_flash_2leg': 0.2,
            }
        },
        treasury_state={'aggressiveness': {'aggressiveness_multiplier': 1.4}},
        regime_label='risk_on',
        basefee_gwei=18.5,
        prio_gwei=2.25,
        mev_risk=0.35,
    )

    three_leg_overlay = opp_three_leg.meta['overlay']
    two_leg_overlay = opp_two_leg.meta['overlay']

    assert three_leg_overlay['score_multiplier'] == 1.5
    assert two_leg_overlay['score_multiplier'] > 1.0
    assert three_leg_overlay['regime_label'] == 'risk_on'
    assert three_leg_overlay['basefee_gwei'] == 18.5
    assert three_leg_overlay['priority_gwei'] == 2.25
    assert three_leg_overlay['mev_risk'] == 0.35
    assert three_leg_overlay['consensus_score'] == 0.77
    assert three_leg_overlay['consensus_allow'] is True


def test_runtime_score_overlay_facade_is_best_effort_per_opportunity():
    runtime = _Runtime()
    runtime._consensus_last = {'consensus_score': 0.25, 'allow': False}
    good = _opp(legs=2, meta={'overlay': {'existing': 'kept'}})
    bad = _BrokenOpp()

    runtime._apply_score_overlays(
        opps=[bad, good],
        behave_state={'strategy_priority_matrix': {'dex_flash_2leg': 0.3}},
        treasury_state={'aggressiveness': {'aggressiveness_multiplier': 1.1}},
        regime_label='balanced',
        basefee_gwei=12.0,
        prio_gwei=1.0,
        mev_risk=0.1,
    )

    assert bad.meta == {'existing': True}
    assert good.meta['overlay']['existing'] == 'kept'
    assert good.meta['overlay']['consensus_allow'] is False
    assert good.meta['overlay']['score_multiplier'] > 1.0


def test_runtime_score_overlay_facade_outer_failure_is_operator_safe():
    runtime = _Runtime()
    opp = _opp(legs=2)

    runtime._apply_score_overlays(
        opps=[opp],
        behave_state={'strategy_priority_matrix': {'dex_flash_2leg': 0.9}},
        treasury_state={'aggressiveness': object()},
        regime_label='unknown',
        basefee_gwei=0.0,
        prio_gwei=0.0,
        mev_risk=0.0,
    )

    assert opp.meta == {}
