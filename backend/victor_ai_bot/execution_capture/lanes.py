from __future__ import annotations

from .models import OpportunityEnvelope, CaptureScore, ExecutionLane


def select_lane(
    envelope: OpportunityEnvelope,
    score: CaptureScore,
    *,
    public_mode: bool = False,
    force_send_mode: str = "",
) -> ExecutionLane:
    forced = str(force_send_mode or "").strip().lower()
    if forced == "public":
        return ExecutionLane.PUBLIC
    if forced == "protected_rpc":
        return ExecutionLane.PROTECTED
    if forced == "private":
        return ExecutionLane.PRIVATE

    if score.expected_realized_value <= 0.0:
        return ExecutionLane.DROP
    if public_mode and envelope.mempool_copy_risk >= 0.55:
        return ExecutionLane.DROP
    if score.success_probability < 0.45 or score.freshness_probability < 0.35:
        return ExecutionLane.DROP
    if (
        envelope.mempool_copy_risk >= 0.75
        or envelope.private_send_preference
        or envelope.liquidity_fragility >= 0.75
    ):
        return ExecutionLane.PRIVATE
    if (
        envelope.mempool_copy_risk >= 0.40
        or envelope.slippage_sensitivity >= 0.45
        or envelope.latency_half_life_ms <= 900
    ):
        return ExecutionLane.PROTECTED
    return ExecutionLane.PUBLIC
