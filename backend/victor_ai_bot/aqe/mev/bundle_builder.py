from __future__ import annotations

from typing import Any, Dict


def build_bundle_candidate(*, opportunity_id: str, relay_hint: str, expected_profit_usd: float, leg_count: int = 1) -> Dict[str, Any]:
    return {
        'bundle_id': f'bundle:{opportunity_id}',
        'relay_hint': str(relay_hint or 'private_relay'),
        'expected_profit_usd': float(expected_profit_usd),
        'leg_count': int(leg_count),
        'privacy': 'private',
    }
