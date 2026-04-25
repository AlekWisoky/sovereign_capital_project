from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Dict, List, Tuple

from .base import AgentOutput
from .investment_agents import default_agent_set
from ..coordination.task_contracts import contract_for_agent
from ..portfolio.manager import PortfolioManager
from victor_ai_bot.agents import classify_health, mandate_for

_SAFE_AGENT_EXCEPTIONS = (
    AttributeError,
    LookupError,
    OSError,
    OverflowError,
    RuntimeError,
    TypeError,
    ValueError,
    ZeroDivisionError,
)
_SAFE_MAPPING_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_FLOAT_EXCEPTIONS = (TypeError, ValueError, OverflowError)


def _status(ok: bool, code: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ok": bool(ok), "code": str(code)}
    payload.update(extra)
    return payload


def _merge_status(parts: Dict[str, Dict[str, Any]], key: str, status: Dict[str, Any]) -> None:
    parts[str(key)] = dict(status)


def _runtime_snapshot(parts: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    payload = {str(k): dict(v) for k, v in parts.items()}
    payload["degraded"] = any(not bool(v.get("ok", False)) for v in payload.values())
    return payload


def _coerce_float(value: Any, default: float, *, code: str) -> Tuple[float, Dict[str, Any]]:
    try:
        return float(value if value is not None else default), _status(True, f"{code}_ok")
    except _SAFE_FLOAT_EXCEPTIONS:
        return float(default), _status(False, f"{code}_invalid")


def _coerce_mapping(value: Any, *, code: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if isinstance(value, dict):
        return dict(value), _status(True, f"{code}_ok")
    try:
        coerced = dict(value or {})
        return coerced, _status(False, f"{code}_coerced")
    except _SAFE_MAPPING_EXCEPTIONS:
        return {}, _status(False, f"{code}_invalid")


@dataclass
class AgentHubState:
    signals: Dict[str, float]
    confidences: Dict[str, float]
    outputs: Dict[str, Dict[str, Any]]
    contracts: Dict[str, Dict[str, Any]] | None = None
    health: Dict[str, Dict[str, Any]] | None = None
    mandates: Dict[str, Dict[str, Any]] | None = None
    portfolio_manager: Dict[str, Any] | None = None
    runtime: Dict[str, Any] | None = None


class AgentHub:
    """Runs the deterministic specialist agent roster and a portfolio overlay.

    This is additive: agents publish scored opinions; execution remains governed
    elsewhere by capture/risk/treasury controls.
    """

    def __init__(self, *, data_dir: str = "backend/data"):
        self.data_dir = str(data_dir or "backend/data")
        self.agents = default_agent_set(data_dir=self.data_dir)
        self.portfolio_manager = PortfolioManager()

    def step(self, *, state: Dict[str, Any]) -> AgentHubState:
        sig: Dict[str, float] = {}
        conf: Dict[str, float] = {}
        outs: Dict[str, Dict[str, Any]] = {}
        contracts: Dict[str, Dict[str, Any]] = {}
        health: Dict[str, Dict[str, Any]] = {}
        mandates: Dict[str, Dict[str, Any]] = {}
        agent_outputs: List[AgentOutput] = []
        hub_runtime: Dict[str, Dict[str, Any]] = {
            "agents": _status(True, "agents_ok"),
            "portfolio_manager": _status(True, "portfolio_manager_ok"),
        }

        for a in list(self.agents):
            name = str(getattr(a, "name", a.__class__.__name__))
            c = contract_for_agent(name)
            mandate = mandate_for(name)
            mandates[name] = mandate.to_dict()
            runtime_parts: Dict[str, Dict[str, Any]] = {
                "act": _status(True, "act_idle"),
                "signal": _status(True, "signal_idle"),
                "confidence": _status(True, "confidence_idle"),
                "info": _status(True, "info_idle"),
                "reasoning": _status(True, "reasoning_idle"),
            }
            try:
                t0 = time.perf_counter()
                o = a.act(state=dict(state or {}))
                dur_ms = float((time.perf_counter() - t0) * 1000.0)
                _merge_status(runtime_parts, "act", _status(True, "act_ok", duration_ms=round(dur_ms, 3)))

                signal, signal_status = _coerce_float(getattr(o, "signal", 0.0), 0.0, code="signal")
                confidence, confidence_status = _coerce_float(
                    getattr(o, "confidence", 0.0), 0.0, code="confidence"
                )
                info_map, info_status = _coerce_mapping(getattr(o, "info", {}), code="info")
                reasoning_map, reasoning_status = _coerce_mapping(
                    getattr(o, "reasoning", {}), code="reasoning"
                )
                info_map.setdefault("name", name)
                _merge_status(runtime_parts, "signal", signal_status)
                _merge_status(runtime_parts, "confidence", confidence_status)
                _merge_status(runtime_parts, "info", info_status)
                _merge_status(runtime_parts, "reasoning", reasoning_status)
                runtime_state = _runtime_snapshot(runtime_parts)

                sanitized = AgentOutput(
                    pi_team={},
                    pi_self={},
                    alpha=0.0,
                    q_values={},
                    confidence=float(confidence),
                    info={"name": name},
                    signal=float(signal),
                    reasoning=dict(reasoning_map),
                )
                agent_outputs.append(sanitized)

                sig[name] = float(signal)
                conf[name] = float(confidence)
                h = classify_health(duration_ms=dur_ms, ttl_ms=int(mandate.ttl_ms), ok=True, age_ms=0)
                health[name] = h.to_dict()

                out_obj = {
                    "signal": float(signal),
                    "confidence": float(confidence),
                    "estimated_value_contribution": round(float(signal) * float(confidence), 6),
                    "info": dict(info_map),
                    "reasoning": dict(reasoning_map),
                    "reasoning_codes": list(mandate.reasoning_codes),
                    "ttl_ms": int(mandate.ttl_ms),
                    "health": h.to_dict(),
                    "mandate": mandate.to_dict(),
                    "runtime": runtime_state,
                }
                out_obj["info"]["runtime"] = dict(runtime_state)
                out_obj["reasoning"]["runtime"] = dict(runtime_state)
                vin = c.validate_inputs(state or {})
                vout = c.validate_outputs(out_obj)
                out_obj["task_contract"] = c.to_dict()
                out_obj["contract_validation"] = {"inputs": vin, "outputs": vout}
                out_obj["duration_ms"] = round(dur_ms, 3)
                out_obj["sla_ms"] = int(c.sla_ms)
                out_obj["sla_ok"] = bool(dur_ms <= float(c.sla_ms))

                outs[name] = out_obj
                contracts[name] = c.to_dict()
                if runtime_state.get("degraded"):
                    _merge_status(hub_runtime, "agents", _status(False, "agent_output_degraded", agent=name))
            except _SAFE_AGENT_EXCEPTIONS as e:
                runtime_state = _runtime_snapshot(
                    {
                        "act": _status(False, "act_failed", error=str(e)),
                        "signal": _status(False, "signal_unavailable"),
                        "confidence": _status(False, "confidence_unavailable"),
                        "info": _status(False, "info_unavailable"),
                        "reasoning": _status(False, "reasoning_unavailable"),
                    }
                )
                health[name] = classify_health(
                    duration_ms=float(c.sla_ms),
                    ttl_ms=int(mandate.ttl_ms),
                    ok=False,
                    error=str(e),
                    age_ms=int(mandate.ttl_ms),
                ).to_dict()
                outs[name] = {
                    "signal": 0.0,
                    "confidence": 0.0,
                    "estimated_value_contribution": 0.0,
                    "info": {"name": name, "runtime": dict(runtime_state)},
                    "reasoning": {"error": str(e), "runtime": dict(runtime_state)},
                    "reasoning_codes": list(mandate.reasoning_codes),
                    "ttl_ms": int(mandate.ttl_ms),
                    "health": health[name],
                    "mandate": mandate.to_dict(),
                    "task_contract": c.to_dict(),
                    "contract_validation": {"inputs": c.validate_inputs(state or {}), "outputs": {"ok": False, "missing": []}},
                    "duration_ms": float(c.sla_ms),
                    "sla_ms": int(c.sla_ms),
                    "sla_ok": False,
                    "runtime": runtime_state,
                }
                contracts[name] = c.to_dict()
                _merge_status(hub_runtime, "agents", _status(False, "agent_failed", agent=name, error=str(e)))

        portfolio_summary: Dict[str, Any] | None = None
        try:
            t0 = time.perf_counter()
            agg = self.portfolio_manager.aggregate(agent_outputs)
            dur_ms = float((time.perf_counter() - t0) * 1000.0)
            name = "Portfolio Manager"
            c = contract_for_agent(name)
            mandate = mandate_for(name)
            h = classify_health(duration_ms=dur_ms, ttl_ms=int(mandate.ttl_ms), ok=True, age_ms=0)
            signal, signal_status = _coerce_float(
                (agg.get("portfolio_signal") if isinstance(agg, dict) else 0.0),
                0.0,
                code="portfolio_signal",
            )
            confidence, confidence_status = _coerce_float(
                (agg.get("portfolio_confidence") if isinstance(agg, dict) else 0.0),
                0.0,
                code="portfolio_confidence",
            )
            contrib, contrib_status = _coerce_mapping(
                (agg.get("contrib") if isinstance(agg, dict) else {}), code="portfolio_contrib"
            )
            weights_used, weights_status = _coerce_mapping(
                (agg.get("weights_used") if isinstance(agg, dict) else {}),
                code="portfolio_weights",
            )
            runtime_state = _runtime_snapshot(
                {
                    "aggregate": _status(True, "aggregate_ok", duration_ms=round(dur_ms, 3)),
                    "signal": signal_status,
                    "confidence": confidence_status,
                    "contributors": contrib_status,
                    "weights": weights_status,
                }
            )
            portfolio_summary = {
                "signal": float(signal),
                "confidence": float(confidence),
                "estimated_value_contribution": round(float(signal) * float(confidence), 6),
                "info": {"name": name, "runtime": dict(runtime_state)},
                "reasoning": {"contributors": dict(contrib), "weights_used": dict(weights_used), "runtime": dict(runtime_state)},
                "reasoning_codes": list(mandate.reasoning_codes),
                "ttl_ms": int(mandate.ttl_ms),
                "health": h.to_dict(),
                "mandate": mandate.to_dict(),
                "task_contract": c.to_dict(),
                "contract_validation": {
                    "inputs": c.validate_inputs({"agent_outputs": [getattr(o, 'info', {}) for o in agent_outputs]}),
                    "outputs": {"ok": True, "missing": []},
                },
                "duration_ms": round(dur_ms, 3),
                "sla_ms": int(c.sla_ms),
                "sla_ok": bool(dur_ms <= float(c.sla_ms)),
                "contrib": dict(contrib),
                "weights_used": dict(weights_used),
                "runtime": runtime_state,
            }
            outs[name] = portfolio_summary
            contracts[name] = c.to_dict()
            health[name] = h.to_dict()
            mandates[name] = mandate.to_dict()
            if runtime_state.get("degraded"):
                _merge_status(
                    hub_runtime,
                    "portfolio_manager",
                    _status(False, "portfolio_output_degraded"),
                )
        except _SAFE_AGENT_EXCEPTIONS as e:
            runtime_state = _runtime_snapshot(
                {
                    "aggregate": _status(False, "portfolio_aggregate_failed", error=str(e)),
                    "signal": _status(False, "portfolio_signal_unavailable"),
                    "confidence": _status(False, "portfolio_confidence_unavailable"),
                    "contributors": _status(False, "portfolio_contrib_unavailable"),
                    "weights": _status(False, "portfolio_weights_unavailable"),
                }
            )
            portfolio_summary = {
                "signal": 0.0,
                "confidence": 0.0,
                "estimated_value_contribution": 0.0,
                "info": {"name": "Portfolio Manager", "runtime": dict(runtime_state)},
                "reasoning": {"error": str(e), "runtime": dict(runtime_state)},
                "runtime": runtime_state,
            }
            _merge_status(
                hub_runtime,
                "portfolio_manager",
                _status(False, "portfolio_manager_failed", error=str(e)),
            )

        return AgentHubState(
            signals=sig,
            confidences=conf,
            outputs=outs,
            contracts=contracts,
            health=health,
            mandates=mandates,
            portfolio_manager=portfolio_summary,
            runtime=_runtime_snapshot(hub_runtime),
        )
