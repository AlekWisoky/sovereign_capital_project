from types import SimpleNamespace

from victor_ai_bot.runtime_services.auxiliary_state_service import CapitalTruthSnapshot
from victor_ai_bot.runtime_services.capital_truth_read_context import _build_base_context


class _Auxiliary:
    def __init__(self):
        self.snapshot = CapitalTruthSnapshot(
            capital_summary={"ok": True, "navUsd": 12.0, "reason_code": "ok"},
            capital_contract={"contractVersion": "canonical_capital_summary_v1"},
            capital_policy={"enforced": True},
            capital_economic_model={"modelVersion": "capital_economic_model_v1"},
            authority={"ok": True},
        )

    def capital_truth(self, runtime):
        return self.snapshot


class _ExplodingStateSummary:
    def capital_truth_state(self, runtime):
        raise AssertionError("read-context dependency must not re-enter state summary")


def test_capital_truth_read_context_uses_canonical_snapshot_without_state_summary_reentry():
    runtime = SimpleNamespace()
    auxiliary = _Auxiliary()

    base = _build_base_context(
        runtime,
        auxiliary_state=auxiliary,
        state_summary=_ExplodingStateSummary(),
    )

    assert base.capital_truth is auxiliary.snapshot
    assert base.capital_truth_state == auxiliary.snapshot.capital_summary
