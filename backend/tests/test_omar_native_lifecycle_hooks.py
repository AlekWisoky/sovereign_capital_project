from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.omar.native_hooks import decision_hook, execution_hook, settlement_hook


class _Omar:
    enabled = True

    def __init__(self):
        self.outcomes = []

    def observe_outcome(self, **kwargs):
        self.outcomes.append(kwargs)


def _runtime(omar=None):
    return SimpleNamespace(
        cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")),
        _omar=omar,
    )


def test_decision_hook_creates_identity_without_omar():
    runtime = _runtime()
    opp = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    decision = SimpleNamespace(metadata={})

    decision_hook(runtime, opp, decision, current_block=123)

    assert opp.meta["brain"]["canonical_decision_id"]
    assert opp.meta["brain"]["correlation_id"]
    assert decision.metadata["canonical_decision_id"] == opp.meta["brain"]["canonical_decision_id"]
    assert decision.metadata["correlation_id"] == opp.meta["brain"]["correlation_id"]


def test_execution_hook_carries_exact_identity_to_result():
    runtime = _runtime()
    opp = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision = SimpleNamespace(metadata={})
    result = SimpleNamespace(plan={})

    decision_hook(runtime, opp, decision, current_block=456)
    execution_hook(runtime, opp, decision, result, bn=456, latency_ms=17, mode="auto")

    lineage = opp.meta["canonical_lineage"]
    assert result.plan["canonical_decision_id"] == lineage["decision_id"]
    assert result.plan["correlation_id"] == lineage["correlation_id"]
    assert result.plan["latency_ms"] == 17
    assert result.plan["execution_mode"] == "auto"


def test_settlement_hook_trains_only_from_matching_settled_outcome():
    omar = _Omar()
    runtime = _runtime(omar)
    opp = SimpleNamespace(id="opp-3", route_id="route-3", meta={})
    decision = SimpleNamespace(metadata={})
    decision_hook(runtime, opp, decision, current_block=789)
    lineage = opp.meta["canonical_lineage"]

    settlement_hook(runtime, opp, {"status": "submitted", **lineage})
    assert omar.outcomes == []

    settlement_hook(runtime, opp, {"status": "settled", "decision_id": "wrong", **lineage})
    assert omar.outcomes == []

    settlement_hook(
        runtime,
        opp,
        {
            "status": "settled",
            "decision_id": lineage["decision_id"],
            "correlation_id": lineage["correlation_id"],
            "ok": True,
            "realized_net_usd": 1.25,
            "expected_net_usd": 1.0,
            "amount_in_wei": 100,
            "gas_cost_usd": 0.05,
            "slippage_bps": 2.0,
            "latency_ms": 31,
            "route_id": "route-3",
            "tx_hash": "0xabc",
            "truth_verified": True,
        },
    )
    assert len(omar.outcomes) == 1
    assert omar.outcomes[0]["decision_id"] == lineage["decision_id"]
    assert omar.outcomes[0]["metadata"]["canonical_lineage"] == lineage
