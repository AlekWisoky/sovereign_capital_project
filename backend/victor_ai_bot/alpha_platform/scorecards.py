from __future__ import annotations

from typing import Any, Dict

from .fund_families import default_fund_families


def build_alpha_scorecards(*, family_scorecards: Dict[str, Any], engine_state: Dict[str, Any]) -> Dict[str, Any]:
    fams = list((family_scorecards or {}).get('families') or [])
    eng_items = list((engine_state or {}).get('summary', {}).get('engines') or [])
    family_by_name = {str(x.get('family')): dict(x) for x in fams if isinstance(x, dict)}
    fund_fams = default_fund_families()
    engines = []
    for item in eng_items:
        family = str(item.get('family') or item.get('engine') or '')
        score = dict(family_by_name.get(family) or {})
        fam_meta = fund_fams.get(family)
        engines.append({
            'engine': item.get('engine') or family,
            'family': family,
            'status': item.get('status') or 'unknown',
            'incomeStream': fam_meta.income_stream if fam_meta else '',
            'alphaType': fam_meta.alpha_type if fam_meta else '',
            'capacityCurve': fam_meta.capacity_curve if fam_meta else '',
            'realizedPnlUsd': float(score.get('realizedPnlUsd') or 0.0),
            'stability': float(score.get('stability') or 0.0),
            'gasEfficiency': float(score.get('gasEfficiency') or 0.0),
            'regimeDependence': dict(score.get('regimeDependence') or {}),
        })
    return {'engines': engines}
