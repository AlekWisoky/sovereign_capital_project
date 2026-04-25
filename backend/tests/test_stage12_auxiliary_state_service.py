from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.auxiliary_state_service import AuxiliaryStateService
from victor_ai_bot.runtime_services.replay_service import ReplayService


class _FeatureBus:
    def snapshot(self):
        return {"ok": True, "items": [1, 2, 3]}


class _SpreadItem:
    def __init__(self, value: str):
        self.value = value

    def as_dict(self):
        return {"value": self.value}


class _BadSpreadItem:
    def __iter__(self):
        raise TypeError("broken")


class _QuickSight:
    def state(self):
        return {"ok": True, "enabled": True}

    def get_dataset(self, name: str):
        if name == "broken":
            raise RuntimeError("dataset_failed")
        return [{"name": name}]

    def get_dashboards(self):
        return [{"id": "exec"}]

    def ask(self, *, question: str, role: str, token: str):
        return {"ok": True, "question": question, "role": role, "token": token}

    def scenario(self, *, params, role: str, token: str):
        return {"ok": True, "params": params, "role": role, "token": token}


class _ExplodingQuickSight:
    def state(self):
        raise RuntimeError("state_boom")

    def get_dataset(self, name: str):
        del name
        raise RuntimeError("dataset_boom")

    def get_dashboards(self):
        raise RuntimeError("dashboards_boom")

    def ask(self, *, question: str, role: str, token: str):
        del question, role, token
        raise RuntimeError("ask_boom")

    def scenario(self, *, params, role: str, token: str):
        del params, role, token
        raise RuntimeError("scenario_boom")


class _Weighting:
    def snapshot(self):
        return {"weights": {"arb": 0.7}}


class _Runtime:
    def __init__(self):
        self._feature_bus = _FeatureBus()
        self._spread_opps = [_SpreadItem("a"), _BadSpreadItem()]
        self._spread_last = {"edge": 3}
        self._consensus_last = {"winner": "arb"}
        self.cfg = SimpleNamespace(
            chain=SimpleNamespace(name="ethereum"),
            execution=SimpleNamespace(consensus=SimpleNamespace(enabled=True)),
        )
        self._quicksight = _QuickSight()
        self._agent_hub_last = {"mode": "shadow"}
        self._agent_weighting = _Weighting()
        self._eff = SimpleNamespace(snapshot=lambda: {"efficiency_pct": 91.5})
        self._bankroll = SimpleNamespace(
            success_rate_pct=lambda: 84.0,
            state=SimpleNamespace(fail_streak=2),
        )
        self.metrics = SimpleNamespace(
            last_block=123,
            scan_ms=10.5,
            gas_mode="standard",
            send_mode="private",
            basefee_gwei=8.2,
            opportunity_rate=1.3,
            realized_profit_raw="42",
        )
        self._research_candidates = SimpleNamespace(
            items=lambda: [{"candidateId": "c1"}],
            pipeline_counts=lambda: {"sandbox": 1},
            throughput_metrics=lambda: {"researchHitRate": 0.5},
        )
        self._ledger = SimpleNamespace(
            tail=lambda limit=50: [{"asset": "ETH", "amount": 1.0}],
            transactions_tail=lambda limit=50: [{"tx_type": "prime_loan_open"}],
            balances=lambda: {"ETH": 1.0},
        )
        self._ledger_repo = None
        self._internal_prime = SimpleNamespace(snapshot=lambda: {"borrowedUsd": 12.0, "capacityUsd": 100.0, "loanCount": 1})
        self._cio_service = SimpleNamespace(summary=lambda runtime: {"ok": True, "nav": 100})
        self._wealth_goal_service = SimpleNamespace(
            state=lambda runtime: {"state": {"targetUsd": 1000}},
            replay_payload=lambda runtime: {"targetUsd": 1000},
        )


def test_auxiliary_state_service_handles_optional_operator_surfaces():
    runtime = _Runtime()
    svc = AuxiliaryStateService()

    assert svc.unified_state(runtime)["items"] == [1, 2, 3]
    spread = svc.spread_opportunities(runtime)
    assert spread["count"] == 2
    assert spread["opps"] == [{"value": "a"}]
    assert svc.consensus_state(runtime)["cfg"]["enabled"] is True
    assert svc.quicksight_dataset(runtime, "exec")["rows"][0]["name"] == "exec"
    broken = svc.quicksight_dataset(runtime, "broken")
    assert broken["ok"] is False
    assert broken["status"] == "degraded"
    assert broken["reason_code"] == "quicksight_dataset_failed"
    assert broken["error"] == "quicksight_dataset_failed"
    assert broken["dataset"] == "broken"
    assert broken["rows"] == []
    agent = svc.agent_hub_state(runtime, agent_attribution={"agents": []})
    assert agent["weights"]["weights"]["arb"] == 0.7
    metrics = svc.metrics_state(runtime)
    assert metrics["last_block"] == 123
    assert metrics["efficiency_pct"] == 91.5
    assert svc.wealth_goal_state(runtime)["state"]["targetUsd"] == 1000
    assert svc.research_pipeline_state(runtime)["pipelineCounts"]["sandbox"] == 1
    ledger_state = svc.ledger_state(runtime)
    assert ledger_state["balances"]["ETH"] == 1.0
    assert ledger_state["transactions"][0]["tx_type"] == "prime_loan_open"
    assert ledger_state["balanceSource"] == "unknown"
    assert svc.internal_prime_state(runtime)["borrowedUsd"] == 12.0
    assert svc.internal_prime_state(runtime)["capacityUsd"] == 100.0
    assert svc.internal_prime_state(runtime)["loanCount"] == 1
    assert svc.cio_summary_state(runtime)["nav"] == 100
    assert svc.doctrine_state(runtime)["optimizationObjectives"]


def test_replay_service_extracts_wealth_goal_payload_without_runtime_noise():
    runtime = _Runtime()
    svc = ReplayService()

    assert svc.wealth_goal_for_replay(runtime)["targetUsd"] == 1000


def test_auxiliary_state_service_preserves_canonical_unavailable_defaults_for_optional_snapshots():
    runtime = SimpleNamespace()
    svc = AuxiliaryStateService()

    expected = {
        "ok": True,
        "enabled": False,
        "status": "unavailable",
        "reason_code": "unavailable",
        "reason": "unavailable",
    }
    assert svc.unified_state(runtime) == expected
    assert svc.orchestrator_state(runtime) == expected
    assert svc.behaveagent_state(runtime) == expected
    assert svc.treasury_state(runtime) == expected
    assert svc.governance_layer_state(runtime) == expected
    assert svc.blockspace_state(runtime) == expected

    quicksight = svc.quicksight_state(runtime)
    assert quicksight["ok"] is False
    assert quicksight["status"] == "unavailable"
    assert quicksight["reason_code"] == "quicksight_unavailable"
    assert quicksight["reason"] == "quicksight_unavailable"
    assert quicksight["error"] == "quicksight_unavailable"
    assert quicksight["enabled"] is False


def test_auxiliary_state_service_uses_explicit_unavailable_payloads_for_wealth_goal_and_cio():
    runtime = SimpleNamespace(_wealth_goal_service=None, _cio_service=None)
    svc = AuxiliaryStateService()

    wealth = svc.wealth_goal_state(runtime)
    assert wealth["ok"] is False
    assert wealth["status"] == "unavailable"
    assert wealth["reason_code"] == "wealth_goal_service_unavailable"
    assert wealth["state"] == {}
    assert wealth["history"] == []

    cio = svc.cio_summary_state(runtime)
    assert cio == {
        "ok": False,
        "status": "unavailable",
        "reason_code": "cio_service_unavailable",
        "reason": "cio_service_unavailable",
    }


def test_auxiliary_state_service_quicksight_failures_use_deterministic_degraded_payloads():
    runtime = SimpleNamespace(_quicksight=_ExplodingQuickSight())
    svc = AuxiliaryStateService()

    state = svc.quicksight_state(runtime)
    assert state == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_state_failed",
        "reason": "quicksight_state_failed",
        "error": "quicksight_state_failed",
        "enabled": False,
    }

    dataset = svc.quicksight_dataset(runtime, "operators")
    assert dataset == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_dataset_failed",
        "reason": "quicksight_dataset_failed",
        "error": "quicksight_dataset_failed",
        "dataset": "operators",
        "rows": [],
    }

    dashboards = svc.quicksight_dashboards(runtime)
    assert dashboards == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_dashboards_failed",
        "reason": "quicksight_dashboards_failed",
        "error": "quicksight_dashboards_failed",
        "dashboards": [],
    }

    ask = svc.quicksight_ask(runtime, question="status?", role="EXECUTIVE_VIEW", token="tok")
    assert ask == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_ask_failed",
        "reason": "quicksight_ask_failed",
        "error": "quicksight_ask_failed",
    }

    scenario = svc.quicksight_scenario(
        runtime,
        params={"stress": "gas_5x"},
        role="RISK_MANAGER",
        token="tok2",
    )
    assert scenario == {
        "ok": False,
        "status": "degraded",
        "reason_code": "quicksight_scenario_failed",
        "reason": "quicksight_scenario_failed",
        "error": "quicksight_scenario_failed",
    }


def test_auxiliary_internal_prime_state_fails_closed_when_allocator_missing():
    runtime = SimpleNamespace()
    svc = AuxiliaryStateService()

    state = svc.internal_prime_state(runtime)
    assert state["ok"] is False
    assert state["status"] == "unavailable"
    assert state["reason_code"] == "internal_prime_unavailable"
    assert state["stateReady"] is False
    assert state["stateReasonCode"] == "internal_prime_unavailable"
    assert state["borrowedUsd"] == 0.0


def test_auxiliary_internal_prime_state_fails_closed_when_snapshot_raises():
    class _BrokenPrime:
        def snapshot(self):
            raise OSError("prime state offline")

    runtime = SimpleNamespace(_internal_prime=_BrokenPrime())
    svc = AuxiliaryStateService()

    state = svc.internal_prime_state(runtime)
    assert state["ok"] is False
    assert state["status"] == "unavailable"
    assert state["reason_code"] == "internal_prime_state_unavailable"
    assert state["stateReady"] is False
    assert state["stateReasonCode"] == "internal_prime_state_unavailable"
    assert state["loanCount"] == 0
