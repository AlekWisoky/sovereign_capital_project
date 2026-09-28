from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.runtime_services.multiruntime_opportunity_selector import (
    MultiRuntimeOpportunitySelector,
)


def _candidate(
    oid: str,
    profit_usd: int,
    **overrides: object,
) -> SimpleNamespace:
    options = {
        "verified": True,
        "route_ready": True,
        "liquidity_usd": 10_000.0,
        "required_usd": 1_000.0,
        "gate_allowed": True,
        "admission_allowed": True,
        "capital_available": True,
        "flashloan_eligible": True,
    }
    options.update(overrides)
    return SimpleNamespace(
        id=oid,
        route_id=f"route-{oid}",
        strategy="flash_arb",
        can_execute=bool(options["route_ready"]),
        meta={
            "profitability": {
                "stage": "execution_preflight",
                "source": "test",
                "reason": "ok" if options["verified"] else "profitability_contract_invalid",
                "revalidated": bool(options["verified"]),
                "stale": not bool(options["verified"]),
                "valid": bool(options["verified"]),
                "authoritative": bool(options["verified"]),
                "profit_after_costs_wei": str(max(1, profit_usd)),
                "profit_after_costs_usd_micro": int(profit_usd * 1_000_000),
                "expected_profit_usd": float(profit_usd),
            },
            "execution_route_plan": {
                "executable": bool(options["route_ready"]),
                "selected_venues": ["univ3"],
            },
            "execution_route_runtime": {
                "degraded": False,
                "reason_codes": [],
            },
            "execution_capture": {
                "execution_ready": bool(options["route_ready"]),
                "route_capacity_usd": options["liquidity_usd"],
                "capital_required_usd": options["required_usd"],
                "selected_provider": "provider-a",
                "provider_capacity_usd": options["liquidity_usd"],
            },
            "capital_admission": {
                "allowed": bool(options["admission_allowed"]),
                "reason_code": "ok" if options["admission_allowed"] else "capital_admission_blocked",
                "details": {
                    "institutionalSizing": {
                        "valid": True,
                        "sizing": {
                            "execution_allowed": True,
                            "requested_notional_usd": options["required_usd"],
                            "capital_authority_available": bool(options["capital_available"]),
                        },
                    },
                    "flashloanSizing": {
                            "allowed": bool(options["flashloan_eligible"]),
                    },
                },
            },
            "auto_trade_gate": {
                "allowed": bool(options["gate_allowed"]),
                "reason_code": "ok" if options["gate_allowed"] else "telemetry_insufficient",
            },
            "auto_trade_recovery": {
                "ready": bool(options["gate_allowed"]),
                "blocked": not bool(options["gate_allowed"]),
                "reason_code": "ok" if options["gate_allowed"] else "telemetry_insufficient",
            },
        },
    )


class _Runtime:
    def __init__(self, *candidates, gate_allowed=True):
        self._opps = list(candidates)
        self._gate_allowed = gate_allowed

    async def summary(self):
        return {
            "auto_trade_gate": {
                "allowed": self._gate_allowed,
                "reason_code": "ok" if self._gate_allowed else "telemetry_insufficient",
            },
            "auto_trade_recovery": {
                "ready": self._gate_allowed,
                "blocked": not self._gate_allowed,
                "reason_code": "ok" if self._gate_allowed else "telemetry_insufficient",
            },
        }


@pytest.mark.parametrize(
    ("ethereum_profit", "base_profit", "expected_runtime", "expected_id"),
    [
        (30, 20, "ethereum", "eth-best"),
        (10, 40, "base", "base-best"),
    ],
)
@pytest.mark.asyncio
async def test_global_selector_prefers_higher_explicit_usd_after_fee_profit(
    ethereum_profit, base_profit, expected_runtime, expected_id
):
    selector = MultiRuntimeOpportunitySelector()
    out = await selector.select(
        {
            "ethereum": _Runtime(_candidate("eth-best", ethereum_profit)),
            "base": _Runtime(_candidate("base-best", base_profit)),
        }
    )
    assert out["selected_runtime"] == expected_runtime
    assert out["selected_opportunity_id"] == expected_id


@pytest.mark.asyncio
async def test_more_arbitrum_candidates_do_not_win_without_verified_after_fee_truth():
    selector = MultiRuntimeOpportunitySelector()
    out = await selector.select(
        {
            "ethereum": _Runtime(_candidate("eth", 10)),
            "arbitrum": _Runtime(
                _candidate("arb-1", 100, verified=False),
                _candidate("arb-2", 90, verified=False),
                _candidate("arb-3", 80, verified=False),
            ),
        }
    )
    assert out["selected_runtime"] == "ethereum"
    blocked = [x for x in out["candidates"] if x["runtime"] == "arbitrum"]
    assert len(blocked) == 3
    assert all(x["blocking_reason"] == "profitability_contract_invalid" for x in blocked)


@pytest.mark.asyncio
async def test_high_profit_candidate_cannot_win_when_liquidity_is_insufficient():
    selector = MultiRuntimeOpportunitySelector()
    out = await selector.select(
        {
            "ethereum": _Runtime(
                _candidate("eth-high", 100, liquidity_usd=100.0, required_usd=1_000.0)
            ),
            "base": _Runtime(_candidate("base-safe", 20)),
        }
    )
    assert out["selected_runtime"] == "base"
    eth = next(x for x in out["candidates"] if x["opportunity_id"] == "eth-high")
    assert eth["blocking_reason"] == "insufficient_liquidity_capacity"


@pytest.mark.asyncio
async def test_profitable_candidate_cannot_win_when_admission_or_capital_is_blocked():
    selector = MultiRuntimeOpportunitySelector()
    out = await selector.select(
        {
            "ethereum": _Runtime(
                _candidate("eth-blocked", 100, admission_allowed=False)
            ),
            "base": _Runtime(
                _candidate("base-capital-blocked", 90, capital_available=False)
            ),
            "arbitrum": _Runtime(_candidate("arb-ready", 10)),
        }
    )
    assert out["selected_runtime"] == "arbitrum"
    reasons = {
        item["opportunity_id"]: item["blocking_reason"] for item in out["candidates"]
    }
    assert reasons["eth-blocked"] == "capital_admission_blocked"
    assert reasons["base-capital-blocked"] == "capital_authority_unavailable"


@pytest.mark.asyncio
async def test_all_runtime_candidates_blocked_means_no_runtime_selected():
    selector = MultiRuntimeOpportunitySelector()
    out = await selector.select(
        {
            "ethereum": _Runtime(_candidate("eth", 100, gate_allowed=False)),
            "base": _Runtime(_candidate("base", 90, flashloan_eligible=False)),
            "arbitrum": _Runtime(_candidate("arb", 80, route_ready=False)),
        }
    )
    assert out["selected_runtime"] == ""
    assert out["selected_opportunity_id"] == ""
    assert out["selected"] is None


@pytest.mark.asyncio
async def test_raw_wei_is_not_used_as_cross_runtime_profitability_comparator():
    selector = MultiRuntimeOpportunitySelector()
    eth = _candidate("eth", 10)
    base = _candidate("base", 20)
    eth.meta["profitability"]["profit_after_costs_wei"] = "999999999999999999999999999"
    base.meta["profitability"]["profit_after_costs_wei"] = "1"

    out = await selector.select({"ethereum": _Runtime(eth), "base": _Runtime(base)})
    assert out["selected_runtime"] == "base"
    assert out["selected_opportunity_id"] == "base"


@pytest.mark.asyncio
async def test_selector_is_read_only_for_active_chain_and_auto_trade_state():
    selector = MultiRuntimeOpportunitySelector()
    active = "base"
    runtimes = {
        "ethereum": _Runtime(_candidate("eth", 30)),
        "base": _Runtime(_candidate("base", 20)),
        "arbitrum": _Runtime(_candidate("arb", 10)),
    }
    out = await selector.select(runtimes)
    assert out["active_chain_changed"] is False
    assert out["auto_trade_enabled"] is False
    assert out["broadcast_attempted"] is False
    assert active == "base"
