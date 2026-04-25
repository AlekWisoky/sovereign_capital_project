from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Set, Tuple

# Canonical roles (from the prompt)
ROLE_EXECUTIVE_VIEW = "EXECUTIVE_VIEW"
ROLE_RISK_MANAGER = "RISK_MANAGER"
ROLE_STRATEGY_OPERATOR = "STRATEGY_OPERATOR"
ROLE_AUDITOR = "AUDITOR"
ROLE_ADMIN = "ADMIN"

# Permissions (string actions)
PERM_VIEW_DASHBOARDS = "view_dashboards"
PERM_GENERATE_SUMMARY = "generate_summaries"
PERM_VIEW_RISK = "view_risk_panel"
PERM_TRIGGER_SIM = "trigger_simulation"
PERM_PROPOSE_ADJUSTMENTS = "propose_strategy_adjustments"
PERM_VIEW_PDR = "view_policy_decision_records"
PERM_EXPORT_GOV = "export_governance_reports"
PERM_MODIFY_TARGETS = "modify_profit_targets"
PERM_ADJUST_THRESHOLDS = "adjust_risk_thresholds"
PERM_ASK_ANALYTICS = "ask_analytics"

ROLE_PERMS: Dict[str, Set[str]] = {
    ROLE_EXECUTIVE_VIEW: {PERM_VIEW_DASHBOARDS, PERM_GENERATE_SUMMARY, PERM_ASK_ANALYTICS},
    ROLE_RISK_MANAGER: {PERM_VIEW_DASHBOARDS, PERM_VIEW_RISK, PERM_TRIGGER_SIM, PERM_ASK_ANALYTICS},
    ROLE_STRATEGY_OPERATOR: {PERM_VIEW_DASHBOARDS, PERM_PROPOSE_ADJUSTMENTS, PERM_ASK_ANALYTICS},
    ROLE_AUDITOR: {PERM_VIEW_DASHBOARDS, PERM_VIEW_PDR, PERM_EXPORT_GOV, PERM_ASK_ANALYTICS},
    ROLE_ADMIN: {
        PERM_VIEW_DASHBOARDS,
        PERM_GENERATE_SUMMARY,
        PERM_VIEW_RISK,
        PERM_TRIGGER_SIM,
        PERM_PROPOSE_ADJUSTMENTS,
        PERM_VIEW_PDR,
        PERM_EXPORT_GOV,
        PERM_MODIFY_TARGETS,
        PERM_ADJUST_THRESHOLDS,
        PERM_ASK_ANALYTICS,
    },
}


def normalize_role(role: str) -> str:
    r = str(role or "").strip().upper()
    if not r:
        return ROLE_EXECUTIVE_VIEW
    if r in ROLE_PERMS:
        return r
    return ROLE_EXECUTIVE_VIEW


def has_permission(role: str, perm: str) -> bool:
    rr = normalize_role(role)
    return str(perm) in (ROLE_PERMS.get(rr) or set())
