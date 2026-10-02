from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.runtime_services.runtime_primary_scan_facade import RuntimePrimaryScanFacade


def test_provider_comparison_disables_adaptive_size_ladder():
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=0),
        flags=SimpleNamespace(),
    )
    runtime._rpc_provider_comparison = True

    amounts = runtime._adaptive_scan_amounts(1_000)

    assert amounts == [1_000]


def test_selected_provider_can_run_full_adaptive_size_ladder_after_comparison():
    runtime = RuntimePrimaryScanFacade()
    runtime.cfg = SimpleNamespace(
        safety=SimpleNamespace(max_borrow_amount=100_000),
        flags=SimpleNamespace(),
    )
    runtime._rpc_provider_comparison = False

    amounts = runtime._adaptive_scan_amounts(1_000)

    assert amounts[0] == 1_000
    assert len(amounts) > 1
    assert max(amounts) <= 100_000
