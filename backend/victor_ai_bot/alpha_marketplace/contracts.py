from __future__ import annotations

from typing import Dict


def submission_contract() -> Dict[str, str]:
    return {'mode': 'internal_only', 'defaultStage': 'sandbox', 'reviewRequired': 'yes', 'enabledByDefault': 'no'}
