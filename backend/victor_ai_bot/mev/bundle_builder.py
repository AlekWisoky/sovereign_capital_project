from __future__ import annotations

from typing import Any, Dict, List


def build_bundle(*, victim_tx_hash: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {'victimTxHash': victim_tx_hash, 'actions': list(actions), 'bundleSize': len(actions) + 1}
