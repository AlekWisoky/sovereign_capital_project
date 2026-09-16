from __future__ import annotations

from typing import Dict


def submission_contract() -> Dict[str, object]:
    return {
        'mode': 'internal_only',
        'defaultStage': 'sandbox',
        'reviewRequired': 'yes',
        'enabledByDefault': 'no',
        'promotionLadder': ['sandbox', 'paper', 'shadow', 'capped_live', 'live'],
        'executionAuthority': 'canonical_lifecycle_only',
        'strategyIdentityField': 'strategyId',
        'decisionIdentityField': 'decision_id',
        'evidenceRequiredForPromotion': True,
        'capitalSleeveDefault': 'unfunded',
    }
