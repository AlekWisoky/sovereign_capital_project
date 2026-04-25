from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from victor_ai_bot.runtime_services.state_summary_service import StateSummaryService
from victor_ai_bot.runtime_subsystems.replay_store import ReplayBundleStore


def _store(tmp_path: Path) -> ReplayBundleStore:
    return ReplayBundleStore(data_dir=str(tmp_path), chain="ethereum", chain_id=1)


def test_replay_store_create_bundle_degrades_cleanly_on_write_failure(tmp_path: Path):
    store = _store(tmp_path)
    with patch.object(store, "_atomic_write_json", side_effect=OSError("disk full")):
        out = store.create_bundle(
            block_number=123,
            opportunity_id="opp-1",
            route_id="route-1",
            mode="auto",
            rl_state="s0",
            rl_action=1,
            runtime={},
            controls={},
            wealth_goal={},
            opportunities=[],
            execution={},
            tx_hash="0xabc",
            status="draft",
        )
    assert out is None
    state = store.state()
    assert state["degraded"] is True
    assert state["bundleStorage"]["last_error_code"] == "bundle_write_failed"


def test_replay_store_invalid_tx_index_is_explicitly_reported(tmp_path: Path):
    store = _store(tmp_path)
    tx_index_path = Path(tmp_path) / "rft" / "replay" / "ethereum" / "tx_index.json"
    tx_index_path.write_text("{not-json", encoding="utf-8")
    assert store.load_by_tx_hash("0xdead") is None
    state = store.state()
    assert state["degraded"] is True
    assert state["txIndex"]["last_error_code"] == "tx_index_invalid"


def test_state_summary_service_surfaces_replay_storage_state(tmp_path: Path):
    store = _store(tmp_path)
    with patch.object(store, "_atomic_write_json", side_effect=OSError("disk full")):
        store.create_bundle(
            block_number=123,
            opportunity_id="opp-1",
            route_id="route-1",
            mode="auto",
            rl_state="s0",
            rl_action=1,
            runtime={},
            controls={},
            wealth_goal={},
            opportunities=[],
            execution={},
            tx_hash="0xabc",
            status="draft",
        )

    runtime = SimpleNamespace(
        _telemetry_service=SimpleNamespace(
            service_health=lambda runtime: {"execution": {"ok": True}}
        ),
        _replay_service=object(),
        _replay=store,
    )
    payload = StateSummaryService().service_health(runtime)
    assert payload["replay"]["ok"] is True
    assert payload["replay"]["status"] == "degraded"
    assert payload["replay"]["degraded"] is True
    assert payload["replay"]["reason_code"] == "bundle_write_failed"
    assert payload["replay"]["storage"]["bundleStorage"]["last_error_code"] == "bundle_write_failed"


def test_replay_store_opportunity_summary_uses_only_after_cost_profit_and_ranks_by_it(
    tmp_path: Path,
):
    gross_only = SimpleNamespace(
        id="opp-gross",
        route_id="route-gross",
        strategy="flashloan_atomic",
        expected_profit_raw="9000",
        expected_profit_usd="9000",
        meta={"brain": {"reason": "gross_only"}},
        route=SimpleNamespace(legs=[]),
    )
    verified = SimpleNamespace(
        id="opp-net",
        route_id="route-net",
        strategy="flashloan_atomic",
        expected_profit_raw="100",
        expected_profit_usd="100",
        meta={
            "brain": {"reason": "net_after_costs"},
            "safety": {"profit_after_costs_wei": "250", "profit_after_costs_usd_micro": 12},
        },
        route=SimpleNamespace(legs=[]),
    )

    items = ReplayBundleStore.summarize_opportunities([gross_only, verified], limit=2)

    assert [item["opportunity_id"] for item in items] == ["opp-net", "opp-gross"]
    assert items[0]["expected_profit_after_costs_wei"] == "250"
    assert items[0]["expected_profit_after_gas_usd_micro"] == 12
    assert items[1]["expected_profit_after_costs_wei"] == "0"
    assert "profit_after_costs_unavailable" in items[1]["why"]



def test_replay_store_opportunity_summary_marks_mismatched_after_cost_profit_unverified(tmp_path: Path):
    mismatch = SimpleNamespace(
        id="opp-mismatch",
        route_id="route-mismatch",
        strategy="flashloan_atomic",
        expected_profit_raw="9999",
        expected_profit_usd="9999",
        meta={
            "brain": {"reason": "mismatch"},
            "profit_after_costs": "900",
            "safety": {"profit_after_costs_wei": "50", "profit_after_costs_usd_micro": 77},
        },
        route=SimpleNamespace(legs=[]),
    )
    verified = SimpleNamespace(
        id="opp-net",
        route_id="route-net",
        strategy="flashloan_atomic",
        expected_profit_raw="100",
        expected_profit_usd="100",
        meta={
            "brain": {"reason": "net_after_costs"},
            "safety": {"profit_after_costs_wei": "250", "profit_after_costs_usd_micro": 12},
        },
        route=SimpleNamespace(legs=[]),
    )

    items = ReplayBundleStore.summarize_opportunities([mismatch, verified], limit=2)

    assert [item["opportunity_id"] for item in items] == ["opp-net", "opp-mismatch"]
    assert items[1]["expected_profit_after_costs_wei"] == "0"
    assert "profit_after_costs_mismatch" in items[1]["why"]


def test_replay_store_opportunity_summary_prefers_route_ready_verified_candidate_over_route_invalid_higher_profit(tmp_path: Path):
    route_invalid = SimpleNamespace(
        id="opp-invalid",
        route_id="route-invalid",
        strategy="flashloan_atomic",
        expected_profit_raw="9999",
        expected_profit_usd="9999",
        meta={
            "brain": {"reason": "route_invalid"},
            "safety": {"profit_after_costs_wei": "900", "profit_after_costs_usd_micro": 90},
            "execution_route_plan": {"executable": False, "route_invalid_causes": ["route_plan_not_executable"]},
        },
        route=SimpleNamespace(legs=[]),
    )
    route_ready = SimpleNamespace(
        id="opp-ready",
        route_id="route-ready",
        strategy="flashloan_atomic",
        expected_profit_raw="100",
        expected_profit_usd="100",
        meta={
            "brain": {"reason": "route_ready"},
            "safety": {"profit_after_costs_wei": "250", "profit_after_costs_usd_micro": 12},
            "execution_route_plan": {"executable": True},
        },
        route=SimpleNamespace(legs=[]),
    )

    items = ReplayBundleStore.summarize_opportunities([route_invalid, route_ready], limit=2)

    assert [item["opportunity_id"] for item in items] == ["opp-ready", "opp-invalid"]
    assert "route_plan_not_executable" in items[1]["why"]


def test_replay_store_opportunity_summary_prefers_route_ready_unverified_fallback_over_route_invalid_unverified_fallback(tmp_path: Path):
    route_invalid = SimpleNamespace(
        id="opp-invalid",
        route_id="route-invalid",
        strategy="flashloan_atomic",
        expected_profit_raw="8000",
        expected_profit_usd="8000",
        meta={
            "brain": {"reason": "invalid_fallback"},
            "execution_route_plan": {"executable": False, "route_invalid_causes": ["route_plan_not_executable"]},
        },
        route=SimpleNamespace(legs=[]),
    )
    route_ready = SimpleNamespace(
        id="opp-ready",
        route_id="route-ready",
        strategy="flashloan_atomic",
        expected_profit_raw="100",
        expected_profit_usd="100",
        meta={"brain": {"reason": "ready_fallback"}, "execution_route_plan": {"executable": True}},
        route=SimpleNamespace(legs=[]),
    )

    items = ReplayBundleStore.summarize_opportunities([route_invalid, route_ready], limit=2)

    assert [item["opportunity_id"] for item in items] == ["opp-ready", "opp-invalid"]
    assert "profit_after_costs_unavailable" in items[0]["why"]
    assert "route_plan_not_executable" in items[1]["why"]
