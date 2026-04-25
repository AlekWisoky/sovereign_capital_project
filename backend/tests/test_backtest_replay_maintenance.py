import json
from pathlib import Path

from victor_ai_bot.backtest.replay import replay_jsonl, select_best_trade
from victor_ai_bot.models import Opportunity


def _opp_dict(*, opp_id: str = "opp-1", route_id: str = "route-1", profit: str = "100", p_success: str = "0.5"):
    return {
        "id": opp_id,
        "chain": "base",
        "strategy": "flash_arb",
        "expected_profit_raw": "100",
        "expected_profit_usd": "1.0",
        "route": {
            "legs": [
                {
                    "dex": "univ3",
                    "venue": "uniswap",
                    "token_in": "WETH",
                    "token_out": "USDC",
                    "amount_in": "1000",
                    "min_out": "1100",
                }
            ]
        },
        "min_outs": ["1100"],
        "route_id": route_id,
        "can_execute": True,
        "meta": {
            "safety": {"profit_after_costs_wei": profit},
            "brain": {"p_success": p_success},
            "ts": 123,
            "block": 456,
            "send_mode": "private",
        },
    }


def _opp_model(payload):
    if hasattr(Opportunity, "model_validate"):
        return Opportunity.model_validate(payload)
    return Opportunity.parse_obj(payload)


def _runtime_state():
    return {
        "json": {"count": 0, "code": "", "degraded": False},
        "payload": {"count": 0, "code": "", "degraded": False},
        "opportunity": {"count": 0, "code": "", "degraded": False},
        "selection": {"count": 0, "code": "", "degraded": False},
        "degraded": False,
    }


def test_replay_jsonl_reports_runtime_degradation_and_keeps_valid_trade(tmp_path: Path):
    path = tmp_path / "snapshots.jsonl"
    lines = [
        '{not-json}',
        json.dumps({"opportunities": ["bad", {"id": "missing-fields"}]}),
        json.dumps({"opportunities": [_opp_dict(route_id="route-alpha")], "block": 999, "ts": 111}),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = replay_jsonl(str(path))

    assert report.ticks == 3
    assert report.trades == 1
    assert report.by_route["route-alpha"]["trades"] == 1
    assert report.runtime["degraded"] is True
    assert report.runtime["json"]["code"] == "json_decode_failed"
    assert report.runtime["opportunity"]["count"] >= 2


def test_select_best_trade_uses_top_level_route_id_field():
    opp = _opp_model(_opp_dict(route_id="route-top-level"))
    best = select_best_trade([opp])
    assert best is not None
    assert best.route_id == "route-top-level"
    assert best.expected_profit_wei == 50


def test_select_best_trade_marks_missing_route_id_runtime_state():
    opp = _opp_model(_opp_dict(route_id=""))
    runtime = _runtime_state()
    best = select_best_trade([opp], runtime=runtime)
    assert best is not None
    assert best.route_id == ""
    assert runtime["selection"]["code"] == "selection_route_id_missing"
    assert runtime["degraded"] is True


def test_select_best_trade_skips_route_invalid_candidate_and_prefers_route_ready():
    blocked_payload = _opp_dict(opp_id="opp-blocked", route_id="route-blocked", profit="500")
    blocked_payload["meta"]["execution_route_plan"] = {
        "executable": False,
        "route_invalid_causes": ["route_plan_not_executable"],
    }
    ready_payload = _opp_dict(opp_id="opp-ready", route_id="route-ready", profit="200")
    runtime = _runtime_state()

    best = select_best_trade([_opp_model(blocked_payload), _opp_model(ready_payload)], runtime=runtime)

    assert best is not None
    assert best.opportunity_id == "opp-ready"
    assert runtime["selection"]["code"] == "route_plan_not_executable"
    assert runtime["degraded"] is True


def test_select_best_trade_skips_profit_mismatch_candidate_and_prefers_verified_profit():
    mismatch_payload = _opp_dict(opp_id="opp-mismatch", route_id="route-mismatch", profit="500")
    mismatch_payload["meta"]["profit_after_costs"] = "999"
    verified_payload = _opp_dict(opp_id="opp-verified", route_id="route-verified", profit="200")
    verified_payload["meta"]["profit_after_costs"] = "200"
    runtime = _runtime_state()

    best = select_best_trade([_opp_model(mismatch_payload), _opp_model(verified_payload)], runtime=runtime)

    assert best is not None
    assert best.opportunity_id == "opp-verified"
    assert runtime["selection"]["code"] == "profit_after_costs_mismatch"
    assert runtime["degraded"] is True
