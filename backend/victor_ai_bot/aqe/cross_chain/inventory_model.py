from __future__ import annotations

from typing import Dict


def chain_inventory_gate(*, inventory_by_chain: Dict[str, float], src_chain: str, dst_chain: str, capital_required_usd: float) -> Dict[str, float | bool]:
    src = float((inventory_by_chain or {}).get(src_chain) or 0.0)
    dst = float((inventory_by_chain or {}).get(dst_chain) or 0.0)
    prepositioned = min(src, dst)
    required = float(capital_required_usd)
    ok = prepositioned >= required * 0.35 and src >= required * 0.50
    return {
        'ok': bool(ok),
        'src_inventory_usd': round(src, 6),
        'dst_inventory_usd': round(dst, 6),
        'prepositioned_usd': round(prepositioned, 6),
    }
