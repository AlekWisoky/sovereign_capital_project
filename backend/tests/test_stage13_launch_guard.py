from __future__ import annotations

from types import SimpleNamespace

from victor_ai_bot.api_facades.launch_facade import guard_launch_mutation
from victor_ai_bot.fund_os.health_states import HealthState


class _Runtime:
    def __init__(self, *, paused: bool = False, allocations_frozen: bool = False):
        self._launch_rollout = SimpleNamespace(
            profile=SimpleNamespace(
                rollout_order=["flash_arb", "funding_arb"],
                family_states={
                    "flash_arb": HealthState.LIVE.value,
                    "funding_arb": HealthState.QUARANTINED.value,
                },
            )
        )
        self._cc = SimpleNamespace(
            controls=SimpleNamespace(paused=paused, allocations_frozen=allocations_frozen)
        )


def test_launch_guard_denies_enable_when_command_center_paused():
    outcome = guard_launch_mutation(
        runtime=_Runtime(paused=True), family="flash_arb", action="enable_next"
    )
    assert outcome.allowed is False
    assert outcome.reason_code == "command_center_paused"


def test_launch_guard_denies_unknown_or_quarantined_families():
    unknown = guard_launch_mutation(runtime=_Runtime(), family="unknown", action="pause_family")
    quarantined = guard_launch_mutation(
        runtime=_Runtime(), family="funding_arb", action="enable_next"
    )
    assert unknown.reason_code == "unknown_family"
    assert quarantined.reason_code == "family_quarantined"
    assert quarantined.review_required is True
