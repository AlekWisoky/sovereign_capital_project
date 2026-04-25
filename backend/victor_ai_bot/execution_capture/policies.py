from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCapturePolicy:
    min_confidence: float = 0.55
    min_expected_realized_value_usd: float = 0.20
    min_success_probability: float = 0.45
    min_freshness_probability: float = 0.35
    allow_public_lane: bool = True

    def should_drop(
        self,
        *,
        success_probability: float,
        freshness_probability: float,
        expected_realized_value: float,
    ) -> str:
        if success_probability < float(self.min_success_probability):
            return "low_success_probability"
        if freshness_probability < float(self.min_freshness_probability):
            return "stale_or_decayed_edge"
        if expected_realized_value < float(self.min_expected_realized_value_usd):
            return "expected_realized_value_below_threshold"
        return ""
