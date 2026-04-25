from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ._route_helpers import attach_summary_contract, degraded_payload, safe_json_route_call

router = APIRouter(tags=["strategies"])


def get_runtime(request: Request):
    return request.app.state.runtime  # type: ignore[attr-defined]


@router.get("/api/strategies/scorecards")
def strategy_scorecards(rt=Depends(get_runtime)):
    return safe_json_route_call(
        lambda: attach_summary_contract(
            rt.strategy_scorecards_state(),
            family="strategy_scorecards",
            read_model="strategy_scorecards_projection_v1",
            runtime=rt,
        ),
        on_error=lambda exc: attach_summary_contract(
            degraded_payload(
                "strategy_scorecards_failed",
                extra={"families": []},
            ),
            family="strategy_scorecards",
            read_model="strategy_scorecards_projection_v1",
            runtime=rt,
        ),
    )
