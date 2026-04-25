from __future__ import annotations

from typing import Any, Dict, List

from .fund_stage import default_fund_stages


def operator_permissions(*, stage: str) -> Dict[str, Any]:
    pol = default_fund_stages().get(str(stage), default_fund_stages()["internal_capital"])
    scope = str(pol.operator_scope)
    permissions: List[str] = ["view_fund_summary", "view_risk_summary"]
    if scope in {"core_ops", "ops_plus_pm", "fund_ops", "segmented"}:
        permissions += ["promote_candidates", "tune_controls"]
    if scope in {"fund_ops", "segmented"}:
        permissions += ["approve_capital_budgets", "approve_internal_prime", "view_sensitive_alpha"]
    return {"operatorScope": scope, "permissions": permissions}
