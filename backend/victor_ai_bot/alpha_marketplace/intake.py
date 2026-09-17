from __future__ import annotations

from typing import Any

from ..aqe.meta.types import StrategyCandidate


def candidate_to_submission(candidate: StrategyCandidate, *, contributor: str = "aqe_meta") -> dict[str, Any]:
    """Adapt one existing AQE meta candidate into the marketplace intake model."""
    return {
        "submissionId": str(candidate.id),
        "title": str(candidate.description),
        "contributor": str(contributor),
        "family": str(candidate.strategy_family),
        "thesis": str(candidate.description),
        "origin": "ai",
        "strategyId": str(candidate.id),
        "parentStrategyIds": list(candidate.parent_ids),
        "generatingEngine": "aqe_meta",
        "agentId": "aqe_meta",
        "expectedEconomics": {"score": float(candidate.score), "successProbability": float(candidate.meta_success_probability)},
        "evidence": {
            "stressReport": dict(candidate.stress_report),
            "regime": str(candidate.regime),
            "regimeTags": list(candidate.regime_tags),
            "featureTags": list(candidate.feature_tags),
            "diversityBonus": float(candidate.diversity_bonus),
            "correlationPenalty": float(candidate.correlation_penalty),
            "noveltyScore": float(candidate.novelty_score),
        },
        "settingsPatch": dict(candidate.settings_patch),
        "safetyPatch": dict(candidate.safety_patch),
        "structurePatch": dict(candidate.structure_patch),
        "mutationHistory": list(candidate.mutation_history),
        "reviewState": "pending",
        "stage": "sandbox",
        "governanceStatus": "pending",
        "capitalSleeveStatus": "unfunded",
        "promotionReason": "",
    }
