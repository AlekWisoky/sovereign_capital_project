from __future__ import annotations

from typing import Dict

from .contracts import FundLayerContract


def default_layer_contracts() -> Dict[str, FundLayerContract]:
    return {
        "research": FundLayerContract(
            "research",
            "Research Layer",
            "Idea creation, sandbox experiments, promotion evidence, hybrid human+AI thesis management.",
            ["research_ops"],
            ["theses", "candidate metadata", "review notes"],
            ["candidates", "promotion decisions", "throughput metrics"],
            "sandbox_first",
        ),
        "strategy": FundLayerContract(
            "strategy",
            "Strategy Layer",
            "Family definitions, strategy scorecards, interactions, lifecycle memory.",
            ["portfolio_research"],
            ["family metadata", "regime bindings", "interaction scores"],
            ["family scorecards", "strategy health"],
            "family_and_lifecycle_gated",
        ),
        "execution": FundLayerContract(
            "execution",
            "Execution Layer",
            "Capture scoring, lane routing, realism-aware execution decisions, telemetry feedback.",
            ["execution_research"],
            ["normalized opportunities", "route priors", "telemetry feedback"],
            ["execution decisions", "execution telemetry"],
            "fail_closed_capture_gate",
        ),
        "capital": FundLayerContract(
            "capital",
            "Capital Layer",
            "Buckets, allocations, drawdown contraction, crowding controls, fund stage policy.",
            ["treasury_pm"],
            ["capital metrics", "fund stage policy", "risk controls"],
            ["capital plans", "risk-adjusted weights"],
            "reserve_and_stage_disciplined",
        ),
        "risk": FundLayerContract(
            "risk",
            "Risk Layer",
            "Portfolio risk, concentration, stage controls, degraded states and risk reason codes.",
            ["risk_committee"],
            ["capital state", "covariance penalties", "engine state"],
            ["risk scores", "contraction controls"],
            "explicit_reason_codes",
        ),
        "operator": FundLayerContract(
            "operator",
            "Operator Layer",
            "Fund summaries, admin surfaces, command-center visibility, auditability.",
            ["operators"],
            ["runtime state", "fund summary inputs", "audit logs"],
            ["fund summaries", "operator alerts"],
            "capability_scoped",
        ),
    }
