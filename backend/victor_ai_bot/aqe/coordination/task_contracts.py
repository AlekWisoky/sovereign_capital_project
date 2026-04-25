from __future__ import annotations

"""Explicit agent task contracts.

Goal:
- Make agent coupling explicit (what inputs they expect / what outputs they publish).
- Provide lightweight SLAs and validation telemetry.

This is an additive observability/coordination layer; it does not change core
execution semantics.
"""

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class TaskContract:
    task: str
    domain: str
    version: str = "1"
    inputs_required: List[str] = field(default_factory=list)
    inputs_optional: List[str] = field(default_factory=list)
    outputs_required: List[str] = field(default_factory=lambda: ["signal", "confidence", "info", "reasoning"])
    sla_ms: int = 40
    refresh_s: float = 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return {
            "task": d.get("task"),
            "domain": d.get("domain"),
            "version": d.get("version"),
            "inputs_required": list(d.get("inputs_required") or []),
            "inputs_optional": list(d.get("inputs_optional") or []),
            "outputs_required": list(d.get("outputs_required") or []),
            "sla_ms": int(d.get("sla_ms") or 0),
            "refresh_s": float(d.get("refresh_s") or 0.0),
            "description": str(d.get("description") or ""),
        }

    def validate_inputs(self, state: Dict[str, Any]) -> Dict[str, Any]:
        missing = [k for k in (self.inputs_required or []) if k not in (state or {})]
        return {"ok": (len(missing) == 0), "missing": missing}

    def validate_outputs(self, out: Dict[str, Any]) -> Dict[str, Any]:
        missing = [k for k in (self.outputs_required or []) if k not in (out or {})]
        return {"ok": (len(missing) == 0), "missing": missing}



def contract_for_agent(agent_name: str) -> TaskContract:
    n = str(agent_name or "").strip()
    low = n.lower()
    common_required = ["local"]
    common_optional = ["S_global", "C_t", "mev", "funding", "spread", "treasury", "cex", "dex", "wallets", "liq", "sent"]

    if "portfolio manager" in low:
        return TaskContract(
            task=n,
            domain="portfolio",
            inputs_required=["agent_outputs"],
            inputs_optional=["regime", "treasury"],
            outputs_required=["signal", "confidence", "info", "reasoning", "contrib", "weights_used"],
            sla_ms=35,
            refresh_s=1.0,
            description="Aggregates specialist views into a portfolio-level execution bias without bypassing risk controls.",
        )
    if "risk" in low:
        return TaskContract(
            task=n,
            domain="risk",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["positions", "limits", "rel"],
            sla_ms=35,
            refresh_s=1.0,
            description="Risk envelope + circuit breaker signals; must never propose execution directly.",
        )
    if "sentiment" in low:
        return TaskContract(
            task=n,
            domain="sentiment",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["news", "social"],
            sla_ms=55,
            refresh_s=5.0,
            description="Regime-aware sentiment tilt; influences scoring only.",
        )
    if "technical" in low:
        return TaskContract(
            task=n,
            domain="technicals",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["orderbooks", "ohlcv"],
            sla_ms=45,
            refresh_s=1.0,
            description="Microstructure/volatility features and timing signals.",
        )
    if "fundamental" in low:
        return TaskContract(
            task=n,
            domain="fundamentals",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["inventory", "balances", "wallets"],
            sla_ms=60,
            refresh_s=10.0,
            description="Capital efficiency + structural edge estimates.",
        )
    if "valuation" in low or "graham" in low or "buffett" in low or "munger" in low:
        return TaskContract(
            task=n,
            domain="valuation_quality",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["opportunities", "rel"],
            sla_ms=40,
            refresh_s=1.0,
            description="Risk-adjusted opportunity valuation & execution quality scoring.",
        )
    if "fisher" in low:
        return TaskContract(
            task=n,
            domain="growth_scuttlebutt",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["wallets", "funding"],
            sla_ms=45,
            refresh_s=2.0,
            description="Acceleration and scuttlebutt-style confirmation of opportunity strengthening.",
        )
    if "druckenmiller" in low:
        return TaskContract(
            task=n,
            domain="macro",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["funding", "rel", "mev"],
            sla_ms=45,
            refresh_s=1.0,
            description="Macro and asymmetry detector for regime-conditioned risk sizing.",
        )
    if "ackman" in low:
        return TaskContract(
            task=n,
            domain="event_driven",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["liq", "wallets", "mev"],
            sla_ms=45,
            refresh_s=1.0,
            description="Catalyst and anomaly detector for bold but bounded event-driven positioning.",
        )
    if "cathie" in low or "wood" in low:
        return TaskContract(
            task=n,
            domain="growth_innovation",
            inputs_required=list(common_required),
            inputs_optional=list(common_optional) + ["dex", "cex", "mev"],
            sla_ms=45,
            refresh_s=1.0,
            description="Innovation/growth opportunity density detector.",
        )

    return TaskContract(
        task=n or "Agent",
        domain="generic",
        inputs_required=list(common_required),
        inputs_optional=list(common_optional),
        sla_ms=60,
        refresh_s=2.0,
        description="Generic agent contract (fallback).",
    )
