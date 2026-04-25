from __future__ import annotations

from typing import Any, Dict, List, Tuple

from victor_ai_bot.runtime_services.treasury_governance_truth import treasury_governance_view


def _runtime_bucket() -> Dict[str, Any]:
    return {"ok": True, "issues": [], "degraded": False}


def _init_status() -> Dict[str, Any]:
    return {
        "executive": _runtime_bucket(),
        "risk": _runtime_bucket(),
        "agent": _runtime_bucket(),
        "governance": _runtime_bucket(),
        "degraded": False,
    }


def _mark_status(status: Dict[str, Any], bucket: str, code: str) -> None:
    row = status.setdefault(bucket, _runtime_bucket())
    issues = list(row.get("issues") or [])
    issues.append(str(code))
    row["issues"] = issues[-20:]
    row["ok"] = False
    row["degraded"] = True
    status["degraded"] = True


def _coerce_float(
    value: Any, default: float, *, status: Dict[str, Any], bucket: str, code: str
) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            _mark_status(status, bucket, code)
            return float(default)
    if value is None:
        return float(default)
    _mark_status(status, bucket, code)
    return float(default)


def _coerce_int(value: Any, default: int, *, status: Dict[str, Any], bucket: str, code: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            _mark_status(status, bucket, code)
            return int(default)
    if value is None:
        return int(default)
    _mark_status(status, bucket, code)
    return int(default)


def _coerce_ts(value: Any, *, status: Dict[str, Any], bucket: str, code: str) -> int:
    return _coerce_int(value, 0, status=status, bucket=bucket, code=code)


def _coerce_mapping(
    value: Any, *, status: Dict[str, Any], bucket: str, code: str
) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value in (None, ""):
        return {}
    _mark_status(status, bucket, code)
    return {}


def _coerce_list(value: Any, *, status: Dict[str, Any], bucket: str, code: str) -> List[Any]:
    if isinstance(value, list):
        return list(value)
    if value is None:
        return []
    _mark_status(status, bucket, code)
    return []


def build_executive_overview_with_status(
    *, ts: int, pnl: Dict[str, Any], treasury: Dict[str, Any], income: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status()
    goal = _coerce_mapping(
        (treasury or {}).get("goal"),
        status=status,
        bucket="executive",
        code="executive_goal_invalid",
    )
    target = _coerce_float(
        goal.get("target_return_pct"),
        0.0,
        status=status,
        bucket="executive",
        code="executive_target_return_invalid",
    )
    realized = _coerce_int(
        (pnl or {}).get("realized_pnl_wei"),
        0,
        status=status,
        bucket="executive",
        code="executive_realized_invalid",
    )
    net = _coerce_int(
        (pnl or {}).get("net_pnl_wei"),
        0,
        status=status,
        bucket="executive",
        code="executive_net_invalid",
    )
    win_rate = _coerce_float(
        (pnl or {}).get("win_rate"),
        0.0,
        status=status,
        bucket="executive",
        code="executive_win_rate_invalid",
    )
    trades = _coerce_int(
        (pnl or {}).get("trades"),
        0,
        status=status,
        bucket="executive",
        code="executive_trades_invalid",
    )

    inv = _coerce_mapping(
        (
            _coerce_mapping(
                (treasury or {}).get("inventory_balancer"),
                status=status,
                bucket="executive",
                code="executive_inventory_balancer_invalid",
            )
        ).get("targets"),
        status=status,
        bucket="executive",
        code="executive_inventory_targets_invalid",
    )
    ag = _coerce_mapping(
        (treasury or {}).get("aggressiveness"),
        status=status,
        bucket="executive",
        code="executive_aggressiveness_invalid",
    )
    governance = treasury_governance_view(dict(treasury or {}))
    borrow_cap = _coerce_float(
        governance.get("effective_borrow_mult_target_cap"),
        1.0,
        status=status,
        bucket="executive",
        code="executive_borrow_cap_invalid",
    )
    income_map = _coerce_mapping(
        income or {}, status=status, bucket="executive", code="executive_income_invalid"
    )

    dashboard = {
        "type": "EXECUTIVE_OVERVIEW",
        "timestamp": _coerce_ts(ts, status=status, bucket="executive", code="executive_ts_invalid"),
        "kpis": {
            "net_pnl_wei": str(net),
            "realized_pnl_wei": str(realized),
            "target_return_pct": float(target),
            "win_rate": float(win_rate),
            "trades": int(trades),
        },
        "capital_allocation_map": dict(inv),
        "aggressiveness": {
            "level": str(
                governance.get("effective_aggressiveness_level")
                or ag.get("aggressiveness_level")
                or "LOW"
            ),
            "borrow_cap_mult": float(borrow_cap),
        },
        "income_streams": dict(income_map),
    }
    return dashboard, status


def build_risk_control_panel_with_status(
    *, ts: int, market: Dict[str, Any], governance: Dict[str, Any], circuit_breaker: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status()
    market_map = _coerce_mapping(
        market or {}, status=status, bucket="risk", code="risk_market_invalid"
    )
    governance_map = _coerce_mapping(
        governance or {}, status=status, bucket="risk", code="risk_governance_invalid"
    )
    threat = _coerce_mapping(
        governance_map.get("threat"), status=status, bucket="risk", code="risk_threat_invalid"
    )
    breaker = _coerce_mapping(
        circuit_breaker or {}, status=status, bucket="risk", code="risk_circuit_breaker_invalid"
    )
    dashboard = {
        "type": "RISK_CONTROL_PANEL",
        "timestamp": _coerce_ts(ts, status=status, bucket="risk", code="risk_ts_invalid"),
        "real_time": {
            "volatility": _coerce_float(
                market_map.get("volatility_proxy"),
                0.0,
                status=status,
                bucket="risk",
                code="risk_volatility_invalid",
            ),
            "basefee_gwei": _coerce_float(
                market_map.get("basefee_gwei"),
                0.0,
                status=status,
                bucket="risk",
                code="risk_basefee_invalid",
            ),
            "pending_rate": _coerce_float(
                market_map.get("pending_rate"),
                0.0,
                status=status,
                bucket="risk",
                code="risk_pending_rate_invalid",
            ),
        },
        "threat_monitor": dict(threat),
        "circuit_breaker": dict(breaker),
    }
    return dashboard, status


def build_agent_performance_view_with_status(
    *, ts: int, agent_perf: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status()
    ap = _coerce_mapping(agent_perf or {}, status=status, bucket="agent", code="agent_perf_invalid")
    agents = _coerce_list(
        ap.get("agents"), status=status, bucket="agent", code="agent_list_invalid"
    )
    global_map = _coerce_mapping(
        ap.get("global"), status=status, bucket="agent", code="agent_global_invalid"
    )
    dashboard = {
        "type": "AGENT_PERFORMANCE_VIEW",
        "timestamp": _coerce_ts(ts, status=status, bucket="agent", code="agent_ts_invalid"),
        "agents": agents,
        "global": dict(global_map),
        "notes": (
            ["Scores are normalized; higher is better."]
            if ap
            else ["Agent performance unavailable"]
        ),
    }
    return dashboard, status


def build_governance_audit_view_with_status(
    *, ts: int, governance: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    status = _init_status()
    g = _coerce_mapping(
        governance or {}, status=status, bucket="governance", code="governance_payload_invalid"
    )
    pdr_tail = _coerce_list(
        g.get("pdr_tail"), status=status, bucket="governance", code="governance_pdr_tail_invalid"
    )
    override_log = _coerce_list(
        g.get("override_log"),
        status=status,
        bucket="governance",
        code="governance_override_log_invalid",
    )
    compliance = None
    if "compliance_score" in g:
        compliance = _coerce_float(
            g.get("compliance_score"),
            0.0,
            status=status,
            bucket="governance",
            code="governance_compliance_invalid",
        )
    dashboard = {
        "type": "GOVERNANCE_AUDIT_VIEW",
        "timestamp": _coerce_ts(
            ts, status=status, bucket="governance", code="governance_ts_invalid"
        ),
        "pdr_timeline": pdr_tail,
        "compliance_score": compliance,
        "override_log": override_log,
    }
    return dashboard, status


def build_executive_overview(
    *, ts: int, pnl: Dict[str, Any], treasury: Dict[str, Any], income: Dict[str, Any]
) -> Dict[str, Any]:
    dashboard, _ = build_executive_overview_with_status(
        ts=ts, pnl=pnl, treasury=treasury, income=income
    )
    return dashboard


def build_risk_control_panel(
    *, ts: int, market: Dict[str, Any], governance: Dict[str, Any], circuit_breaker: Dict[str, Any]
) -> Dict[str, Any]:
    dashboard, _ = build_risk_control_panel_with_status(
        ts=ts, market=market, governance=governance, circuit_breaker=circuit_breaker
    )
    return dashboard


def build_agent_performance_view(*, ts: int, agent_perf: Dict[str, Any]) -> Dict[str, Any]:
    dashboard, _ = build_agent_performance_view_with_status(ts=ts, agent_perf=agent_perf)
    return dashboard


def build_governance_audit_view(*, ts: int, governance: Dict[str, Any]) -> Dict[str, Any]:
    dashboard, _ = build_governance_audit_view_with_status(ts=ts, governance=governance)
    return dashboard


def build_dashboards_with_status(
    *,
    ts: int,
    pnl: Dict[str, Any],
    treasury: Dict[str, Any],
    income: Dict[str, Any],
    market: Dict[str, Any],
    governance: Dict[str, Any],
    circuit_breaker: Dict[str, Any],
    agent_perf: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    executive, executive_status = build_executive_overview_with_status(
        ts=ts, pnl=pnl, treasury=treasury, income=income
    )
    risk, risk_status = build_risk_control_panel_with_status(
        ts=ts, market=market, governance=governance, circuit_breaker=circuit_breaker
    )
    agent, agent_status = build_agent_performance_view_with_status(ts=ts, agent_perf=agent_perf)
    governance_view, governance_status = build_governance_audit_view_with_status(
        ts=ts, governance=governance
    )
    status = {
        "EXECUTIVE_OVERVIEW": executive_status,
        "RISK_CONTROL_PANEL": risk_status,
        "AGENT_PERFORMANCE_VIEW": agent_status,
        "GOVERNANCE_AUDIT_VIEW": governance_status,
    }
    return {
        "EXECUTIVE_OVERVIEW": executive,
        "RISK_CONTROL_PANEL": risk,
        "AGENT_PERFORMANCE_VIEW": agent,
        "GOVERNANCE_AUDIT_VIEW": governance_view,
    }, status


def build_dashboards(
    *,
    ts: int,
    pnl: Dict[str, Any],
    treasury: Dict[str, Any],
    income: Dict[str, Any],
    market: Dict[str, Any],
    governance: Dict[str, Any],
    circuit_breaker: Dict[str, Any],
    agent_perf: Dict[str, Any],
) -> Dict[str, Any]:
    dashboards, _ = build_dashboards_with_status(
        ts=ts,
        pnl=pnl,
        treasury=treasury,
        income=income,
        market=market,
        governance=governance,
        circuit_breaker=circuit_breaker,
        agent_perf=agent_perf,
    )
    return dashboards
