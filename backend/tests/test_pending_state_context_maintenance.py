from types import SimpleNamespace

from victor_ai_bot.execution_capture.pending_state_context import build_pending_state_context


class _BrokenLegs:
    def __iter__(self):
        raise TypeError("bad legs")


class _BrokenRuntime:
    _pending = ["bad"]

    def mev_state(self):
        raise TypeError("bad mev")

    def blockspace_state(self):
        raise ValueError("bad blockspace")


class _TokenOutBoom:
    venue = "uni"
    token_in = "WETH"

    @property
    def token_out(self):
        raise ValueError("bad token_out")


def test_pending_state_context_reports_runtime_degradation_and_preserves_existing_rows():
    opp = SimpleNamespace(route=SimpleNamespace(legs=_BrokenLegs()), meta={"route_family": "flash"})
    ctx = build_pending_state_context(
        runtime=_BrokenRuntime(),
        opp=opp,
        existing=[{"hash": "0x1", "pairs": ["WETH/USDC"], "source": "seed"}],
    )
    assert ctx["summary"]["degraded"] is True
    assert ctx["runtime"]["opp_route"]["code"] == "pending_route_invalid"
    assert ctx["runtime"]["mev_state"]["code"] == "pending_mev_state_failed"
    assert ctx["runtime"]["runtime_pending"]["code"] == "pending_runtime_pending_invalid"
    assert ctx["runtime"]["blockspace"]["code"] == "pending_blockspace_failed"
    assert ctx["rows"][0]["hash"] == "0x1"


def test_pending_state_context_marks_route_token_failure_explicitly():
    opp = SimpleNamespace(
        route=SimpleNamespace(legs=[_TokenOutBoom()]),
        meta={"route_family": "flashloan_atomic"},
    )
    ctx = build_pending_state_context(runtime=SimpleNamespace(), opp=opp, existing=[])
    assert ctx["runtime"]["opp_route"]["code"] == "pending_route_tokens_invalid"
    assert ctx["summary"]["degraded"] is True
