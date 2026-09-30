from __future__ import annotations

import pytest

from victor_ai_bot import gas_model


class _BadMapping(dict):
    def get(self, key, default=None):
        raise RuntimeError('unexpected get bug')


class _BadLeg(dict):
    def get(self, key, default=None):
        raise RuntimeError('unexpected leg bug')


class _BadSequence:
    def __iter__(self):
        raise RuntimeError('unexpected iter bug')


def test_estimate_route_gas_units_degrades_for_expected_shape_failures() -> None:
    meta = {'venues': None, 'leg1': object()}
    assert gas_model.estimate_route_gas_units(meta) == (
        gas_model.DEFAULT_FLASH_OVERHEAD + gas_model.DEFAULT_EXEC_OVERHEAD
    )


def test_estimate_route_gas_units_uses_univ3_estimate_when_valid() -> None:
    meta = {'venues': ['univ3'], 'leg1': {'gas_estimate': '65000'}}
    assert gas_model.estimate_route_gas_units(meta) == (
        gas_model.DEFAULT_FLASH_OVERHEAD + gas_model.DEFAULT_EXEC_OVERHEAD + 65000
    )


def test_estimate_route_gas_units_falls_back_for_bad_univ3_estimate() -> None:
    meta = {'venues': ['univ3'], 'leg1': {'gas_estimate': object()}}
    assert gas_model.estimate_route_gas_units(meta) == (
        gas_model.DEFAULT_FLASH_OVERHEAD
        + gas_model.DEFAULT_EXEC_OVERHEAD
        + gas_model.LEG_GAS_HEURISTICS['univ3']
    )


def test_estimate_route_gas_units_does_not_swallow_unexpected_meta_bug() -> None:
    with pytest.raises(RuntimeError, match='unexpected get bug'):
        gas_model.estimate_route_gas_units(_BadMapping())


def test_estimate_route_gas_units_does_not_swallow_unexpected_leg_bug() -> None:
    meta = {'venues': ['univ3'], 'leg1': _BadLeg()}
    with pytest.raises(RuntimeError, match='unexpected leg bug'):
        gas_model.estimate_route_gas_units(meta)


def test_estimate_route_gas_units_does_not_swallow_unexpected_venues_bug() -> None:
    meta = {'venues': _BadSequence()}
    with pytest.raises(RuntimeError, match='unexpected iter bug'):
        gas_model.estimate_route_gas_units(meta)



def test_estimate_gas_cost_uses_observed_price_for_expected_cost() -> None:
    cfg = type("Cfg", (), {
        "execution": type("Execution", (), {
            "gas_mode": "standard",
            "gas_presets": type("Presets", (), {"standard_max_fee_gwei": 25})(),
        })(),
    })()
    units = 500_000
    assert gas_model.estimate_gas_cost_wei_from_cfg(
        cfg, units, observed_gas_price_wei=1_000_000_000
    ) == units * 1_000_000_000
    assert gas_model.estimate_gas_cost_wei_from_cfg(cfg, units) == units * 25_000_000_000


def test_estimate_gas_cost_falls_back_when_observed_price_is_unavailable() -> None:
    cfg = type("Cfg", (), {
        "execution": type("Execution", (), {
            "gas_mode": "standard",
            "gas_presets": type("Presets", (), {"standard_max_fee_gwei": 25})(),
        })(),
    })()
    assert gas_model.estimate_gas_cost_wei_from_cfg(
        cfg, 500_000, observed_gas_price_wei=0
    ) == 500_000 * 25_000_000_000
