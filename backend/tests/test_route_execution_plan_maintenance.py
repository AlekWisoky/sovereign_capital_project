from types import SimpleNamespace

from victor_ai_bot.execution_capture.route_execution_plan import (
    build_execution_route_plan,
    apply_execution_route_plan,
)


class Leg:
    def __init__(self, venue: str, min_out: str = "100"):
        self.venue = venue
        self.min_out = min_out


class Route:
    def __init__(self, legs):
        self.legs = legs


class Opp:
    def __init__(self):
        self.route = Route([Leg("uni"), Leg("curve")])
        self.min_outs = ["100", "100"]
        self.expected_profit_raw = "1000"
        self.meta = {}

    def copy(self, deep: bool = False):
        other = Opp()
        other.route = Route([Leg(l.venue, l.min_out) for l in self.route.legs])
        other.min_outs = list(self.min_outs)
        other.expected_profit_raw = self.expected_profit_raw
        other.meta = dict(self.meta)
        return other


def test_route_plan_runtime_marks_invalid_scalars_and_missing_leg_mutations():
    opp = Opp()
    decision = SimpleNamespace(
        metadata={
            "route_plan": {
                "split": [
                    {"venue": "uni", "share": "bad", "size_mult": "oops", "venue_quality": "bad"},
                    {"venue": "curve", "share": 1.0, "size_mult": 1.0, "venue_quality": 0.7},
                ],
                "selected_venues": ["uni", "curve"],
            },
            "flashloan_resilience": {
                "reserve_distortion": "bad",
                "leg_states": [{"venue": "uni", "distortion": "bad"}],
            },
        }
    )
    plan = build_execution_route_plan(opp=opp, decision=decision)
    assert plan["runtime"]["degraded"] is True
    assert plan["runtime"]["input"]["ok"] is False

    broken_plan = dict(plan)
    broken_plan["leg_plan"] = list(plan["leg_plan"]) + [
        {"index": 99, "viability": "bad", "action": "execute"}
    ]
    broken_plan["mutation_factor"] = "bad"
    broken_plan["reserve_distortion"] = "bad"
    mutated = apply_execution_route_plan(opp=opp, plan=broken_plan)
    rt = mutated.meta["execution_route_runtime"]
    assert rt["degraded"] is True
    assert rt["legs"]["ok"] is False
    assert rt["mutation"]["ok"] is False


def test_route_plan_uses_profit_runtime_when_expected_profit_invalid():
    opp = Opp()
    opp.expected_profit_raw = "not-an-int"
    decision = SimpleNamespace(metadata={"route_plan": {}, "flashloan_resilience": {}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    mutated = apply_execution_route_plan(opp=opp, plan=plan)
    rt = mutated.meta["execution_route_runtime"]
    assert rt["profit"]["ok"] is False
    assert rt["profit"]["code"] == "plan_expected_profit_invalid"


def test_route_plan_scales_after_cost_profit_fields_with_viability():
    opp = Opp()
    opp.meta = {"profit_after_costs": "500", "safety": {"profit_after_costs_wei": "500"}}
    decision = SimpleNamespace(metadata={"route_plan": {}, "flashloan_resilience": {}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    degraded_plan = dict(plan)
    degraded_plan["leg_plan"] = [dict(row, viability=0.5) for row in plan["leg_plan"]]
    degraded_plan["mutation_factor"] = 1.0
    degraded_plan["reserve_distortion"] = 0.0
    mutated = apply_execution_route_plan(opp=opp, plan=degraded_plan)
    assert mutated.expected_profit_raw == "500"
    assert mutated.meta["profit_after_costs"] == "250"
    assert mutated.meta["safety"]["profit_after_costs_wei"] == "250"


def test_route_plan_marks_invalid_after_cost_profit_without_crashing():
    opp = Opp()
    opp.meta = {"profit_after_costs": "bad"}
    decision = SimpleNamespace(metadata={"route_plan": {}, "flashloan_resilience": {}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    mutated = apply_execution_route_plan(opp=opp, plan=plan)
    rt = mutated.meta["execution_route_runtime"]
    assert rt["profit"]["ok"] is False
    assert rt["profit"]["code"] == "plan_profit_after_costs_invalid"


def test_route_plan_marks_mismatched_after_cost_profit_truth_without_normalizing_it_away():
    opp = Opp()
    opp.meta = {"profit_after_costs": "500", "safety": {"profit_after_costs_wei": "300"}}
    decision = SimpleNamespace(metadata={"route_plan": {}, "flashloan_resilience": {}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    mutated = apply_execution_route_plan(opp=opp, plan=plan)
    rt = mutated.meta["execution_route_runtime"]
    assert rt["profit"]["ok"] is False
    assert rt["profit"]["code"] == "plan_profit_after_costs_mismatch"
    assert mutated.meta["profit_after_costs"] == "500"
    assert mutated.meta["safety"]["profit_after_costs_wei"] == "300"


def test_route_plan_marks_application_state_for_single_canonical_use():
    opp = Opp()
    decision = SimpleNamespace(metadata={"route_plan": {}, "flashloan_resilience": {}})
    plan = build_execution_route_plan(opp=opp, decision=decision)
    mutated = apply_execution_route_plan(opp=opp, plan=plan)
    assert mutated.meta["execution_route_plan_applied"] is True
    assert mutated.meta["execution_route_plan"] == plan
