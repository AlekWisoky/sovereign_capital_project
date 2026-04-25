from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_legacy import RuntimeBundle
from victor_ai_bot.runtime_services.runtime_treasury_overlay_facade import RuntimeTreasuryOverlayFacade

EXTRACTED_METHODS = {
    '_treasury_overlay_guidance',
    '_apply_treasury_borrow_overlay',
}


class _Runtime(RuntimeTreasuryOverlayFacade):
    pass


def _decision(*, action='trade', borrow_mult=1.0, p_success=0.9):
    return SimpleNamespace(action=action, borrow_mult=borrow_mult, p_success=p_success)


def test_runtime_bundle_inherits_extracted_treasury_overlay_facade():
    assert issubclass(RuntimeBundle, RuntimeTreasuryOverlayFacade)
    for name in EXTRACTED_METHODS:
        assert name not in RuntimeBundle.__dict__
        assert callable(getattr(RuntimeBundle, name))


def test_runtime_treasury_overlay_facade_preserves_borrow_scaling():
    runtime = _Runtime()
    decision = _decision(borrow_mult=1.0, p_success=0.92)

    runtime._apply_treasury_borrow_overlay(
        decision=decision,
        treasury_state={
            'borrow_mult_target_cap': 2.0,
            'aggressiveness': {
                'aggressiveness_level': 'HIGH',
                'urgency_factor': 1.5,
            },
        },
        regime_label='risk_on',
    )

    assert decision.borrow_mult == 1.4000000000000001


def test_runtime_treasury_overlay_facade_respects_gate_conditions():
    runtime = _Runtime()
    low_prob = _decision(borrow_mult=1.0, p_success=0.84)
    unknown_regime = _decision(borrow_mult=1.0, p_success=0.95)
    no_trade = _decision(action='skip', borrow_mult=1.0, p_success=0.99)

    runtime._apply_treasury_borrow_overlay(
        decision=low_prob,
        treasury_state={'borrow_mult_target_cap': 3.0, 'aggressiveness': {'aggressiveness_level': 'MAXIMUM'}},
        regime_label='risk_on',
    )
    runtime._apply_treasury_borrow_overlay(
        decision=unknown_regime,
        treasury_state={'borrow_mult_target_cap': 3.0, 'aggressiveness': {'aggressiveness_level': 'MAXIMUM'}},
        regime_label='unknown',
    )
    runtime._apply_treasury_borrow_overlay(
        decision=no_trade,
        treasury_state={'borrow_mult_target_cap': 3.0, 'aggressiveness': {'aggressiveness_level': 'MAXIMUM'}},
        regime_label='risk_on',
    )

    assert low_prob.borrow_mult == 1.0
    assert unknown_regime.borrow_mult == 1.0
    assert no_trade.borrow_mult == 1.0


def test_runtime_treasury_overlay_facade_is_operator_safe_on_bad_state():
    runtime = _Runtime()
    decision = _decision(borrow_mult=1.1, p_success=0.95)

    runtime._apply_treasury_borrow_overlay(
        decision=decision,
        treasury_state={'borrow_mult_target_cap': object(), 'aggressiveness': object()},
        regime_label='risk_on',
    )

    assert decision.borrow_mult == 1.1
