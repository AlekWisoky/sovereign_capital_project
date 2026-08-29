from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.models import Opportunity, Route, RouteLeg
from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade


def _opp(strategy: str, *, opportunity_id: str) -> Opportunity:
    return Opportunity(
        id=opportunity_id,
        chain="eth",
        strategy=strategy,
        expected_profit_raw="1000000000000000",
        expected_profit_usd="10",
        route=Route(
            legs=[
                RouteLeg(
                    dex="univ3",
                    venue="univ3",
                    token_in="WETH",
                    token_out="USDC",
                    amount_in="1000000000000000",
                    min_out="1",
                )
            ]
        ),
        min_outs=["1"],
        route_id=f"route-{opportunity_id}",
        can_execute=False,
        meta={"strategy_family": strategy},
    )


def _facade(mode: str = "V1_ONLY", active_families=None):
    rt = RuntimeDecisionFacade.__new__(RuntimeDecisionFacade)
    rt._launch_rollout = SimpleNamespace(
        profile=SimpleNamespace(
            mode=mode,
            active_families=list(active_families or ["flash_arb"]),
        )
    )
    return rt


def test_v1_only_allows_only_flash_arb_family():
    rt = _facade()
    flash = _opp("flashloan_atomic", opportunity_id="flash")
    funding = _opp("funding_arb", opportunity_id="funding")

    eligible = rt._apply_rollout_annotations([flash, funding])

    assert [o.id for o in eligible] == ["flash"]
    assert flash.meta["launch_rollout"] == {
        "mode": "V1_ONLY",
        "family": "flash_arb",
        "allowed": True,
        "reason_code": "ok",
    }
    assert funding.meta["launch_rollout"]["allowed"] is False
    assert funding.meta["launch_rollout"]["reason_code"] == "launch_family_not_active"


def test_active_family_mode_controls_runtime_candidate_universe():
    rt = _facade("STAGED_MULTI_STRATEGY", ["funding_arb"])
    flash = _opp("flash_arb", opportunity_id="flash")
    funding = _opp("funding_arb", opportunity_id="funding")

    eligible = rt._apply_rollout_annotations([flash, funding])

    assert [o.id for o in eligible] == ["funding"]


def test_missing_rollout_fails_closed_to_v1():
    rt = RuntimeDecisionFacade.__new__(RuntimeDecisionFacade)
    flash = _opp("flash_arb", opportunity_id="flash")
    funding = _opp("funding_arb", opportunity_id="funding")

    eligible = rt._apply_rollout_annotations([flash, funding])

    assert [o.id for o in eligible] == ["flash"]


def test_unknown_strategy_family_cannot_reach_v1_execution_path():
    rt = _facade()
    unknown = _opp("experimental_unknown", opportunity_id="unknown")

    assert rt._opp_is_rollout_eligible(unknown) is False
