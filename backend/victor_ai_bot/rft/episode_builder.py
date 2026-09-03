from __future__ import annotations

import json
import os
from collections import deque
from typing import Any, Dict, Iterable, List, Tuple

from ..capital_demand import CapitalDemand, capital_demand_from_mapping
from ..version import __version__ as BACKEND_BUILDER_VERSION
from .ids import make_episode_id
from .replay.bundle import list_replay_bundles, load_replay_bundle
from .schema import (
    BreakerState,
    EpisodeContext,
    EpisodeRecord,
    LastOutcome,
    LatencyProfile,
    ProposalConstraints,
    ProposalMode,
    ProposalOutput,
    ReferenceAction,
    RiskCaps,
    TopOpportunity,
)

_SAFE_CAST_EXCEPTIONS = (TypeError, ValueError, OverflowError)


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(str(x))
    except _SAFE_CAST_EXCEPTIONS:
        return int(default)


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except _SAFE_CAST_EXCEPTIONS:
        return float(default)


def _opp_after_costs_wei(opp: Dict[str, Any]) -> int:
    if not isinstance(opp, dict):
        return 0
    return max(0, _safe_int(opp.get("expected_profit_after_costs_wei"), 0))


def _opp_profit_rank_key(opp: Dict[str, Any]) -> Tuple[int, int, int, str]:
    if not isinstance(opp, dict):
        return (0, 0, 0, "")
    after_costs = _opp_after_costs_wei(opp)
    after_gas = max(0, _safe_int(opp.get("expected_profit_after_gas_usd_micro"), 0))
    expected = max(0, _safe_int(opp.get("expected_profit_usd_micro"), 0))
    oid = str(opp.get("route_id") or opp.get("opportunity_id") or "")
    return (1 if after_costs > 0 else 0, after_costs, after_gas, oid)


def _best_ranked_opportunity(opps: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [o for o in list(opps or []) if isinstance(o, dict)]
    if not candidates:
        return {}
    return max(candidates, key=_opp_profit_rank_key)


def _risk_caps_from_bundle(bundle: Dict[str, Any]) -> RiskCaps:
    runtime = (bundle.get("runtime") or {}) if isinstance(bundle.get("runtime"), dict) else {}
    risk = (runtime.get("risk") or {}) if isinstance(runtime.get("risk"), dict) else {}
    caps = (risk.get("caps") or {}) if isinstance(risk.get("caps"), dict) else {}
    return RiskCaps(
        max_daily_loss_pct_bps=int(round(_safe_float(caps.get("maxDailyLossPct"), 3.0) * 100)),
        max_exposure_pct_bps=int(round(_safe_float(caps.get("maxExposurePct"), 80.0) * 100)),
        sandbox_cap_pct_bps=int(round(_safe_float(caps.get("sandboxCapPct"), 10.0) * 100)),
        probation_cap_pct_bps=int(round(_safe_float(caps.get("probationCapPct"), 2.5) * 100)),
    )


def _breaker_state_from_bundle(bundle: Dict[str, Any]) -> BreakerState:
    runtime = (bundle.get("runtime") or {}) if isinstance(bundle.get("runtime"), dict) else {}
    risk = (runtime.get("risk") or {}) if isinstance(runtime.get("risk"), dict) else {}
    breakers = (risk.get("breakers") or {}) if isinstance(risk.get("breakers"), dict) else {}
    return BreakerState(
        drawdown_breaker=bool(breakers.get("drawdownBreaker", False)),
        gas_anomaly_breaker=bool(breakers.get("gasAnomalyBreaker", False)),
        drift_breaker=bool(breakers.get("driftBreaker", False)),
        rpc_degraded=bool(runtime.get("rpcDegraded", False)),
    )


def _latency_from_bundle(bundle: Dict[str, Any]) -> LatencyProfile:
    runtime = (bundle.get("runtime") or {}) if isinstance(bundle.get("runtime"), dict) else {}
    obs = (
        (runtime.get("observability") or {})
        if isinstance(runtime.get("observability"), dict)
        else {}
    )
    reward = (
        (bundle.get("reward_trace") or {}) if isinstance(bundle.get("reward_trace"), dict) else {}
    )
    return LatencyProfile(
        loop_ms_p50=_safe_int(obs.get("loopMsP50")),
        loop_ms_p90=_safe_int(obs.get("loopMsP90")),
        loop_ms_p99=_safe_int(obs.get("loopMsP99")),
        exec_ms_p50=_safe_int(obs.get("execLatencyMsP50")),
        exec_ms_p90=_safe_int(obs.get("execLatencyMsP90")),
        exec_ms_p99=_safe_int(obs.get("execLatencyMsP99")),
        submit_to_receipt_ms_p50=_safe_int(
            reward.get("submit_to_receipt_ms") or obs.get("submitToReceiptMsP50")
        ),
        submit_to_receipt_ms_p90=_safe_int(obs.get("submitToReceiptMsP90")),
        submit_to_receipt_ms_p99=_safe_int(obs.get("submitToReceiptMsP99")),
    )


def _capital_demand_from_bundle(bundle: Dict[str, Any]) -> CapitalDemand:
    raw_execution = bundle.get("execution")
    execution: Dict[str, Any] = (
        dict(raw_execution) if isinstance(raw_execution, dict) else {}
    )
    demand = bundle.get("capital_demand") or bundle.get("capitalDemand")
    payload: Dict[str, Any] = {
        "capital_demand": demand,
        "capitalAdmission": bundle.get("capitalAdmission") or execution.get("capitalAdmission"),
        "wealth_goal": bundle.get("wealth_goal") or bundle.get("wealthGoal"),
        "deployed_usd_micro": execution.get("deployed_usd_micro")
        or execution.get("deployedUsdMicro"),
        "deployedNotionalUsd": execution.get("deployedNotionalUsd"),
        "authority_source": execution.get("authority_source") or execution.get("authoritySource"),
        "capital_source": execution.get("capital_source") or execution.get("capitalSource"),
        "goal_posture": execution.get("goal_posture") or execution.get("goalPosture"),
    }
    if isinstance(demand, dict):
        payload.update(demand)
    return capital_demand_from_mapping(payload)


def _reference_action(bundle: Dict[str, Any]) -> ReferenceAction:
    raw_execution = bundle.get("execution")
    execution: Dict[str, Any] = (
        dict(raw_execution) if isinstance(raw_execution, dict) else {}
    )
    opps = list(bundle.get("opportunities") or [])
    primary = _best_ranked_opportunity(opps)
    reason_bits = [
        f"mode:{str(execution.get('send_mode') or execution.get('mode') or '')}",
        f"status:{str(bundle.get('status') or '')}",
    ]
    if _opp_after_costs_wei(primary) > 0:
        reason_bits.append("after_costs_positive")
    if str(bundle.get("status") or "") in {"settled", "dry_run"}:
        if _opp_after_costs_wei(primary) <= 0:
            return ReferenceAction(quality="none")
        return ReferenceAction(
            proposal=ProposalOutput(
                opportunity_id=str(
                    primary.get("opportunity_id") or bundle.get("opportunity_id") or ""
                ),
                strategy_id=str(primary.get("strategy_id") or "flashloan_atomic"),
                notional_usd_micro=max(
                    0,
                    int(
                        primary.get("expected_profit_after_gas_usd_micro")
                        or primary.get("expected_profit_usd_micro")
                        or 0
                    )
                    * 200,
                ),
                send_mode=(
                    str(execution.get("send_mode") or "protected_rpc")
                    if str(execution.get("send_mode") or "protected_rpc")
                    in {"protected_rpc", "public", "txdata"}
                    else "protected_rpc"
                ),
                why=reason_bits,
                constraints=ProposalConstraints(
                    max_slippage_bps=int(execution.get("slippage_bps") or 50),
                    deadline_seconds=int(execution.get("deadline_seconds") or 30),
                ),
                mode=ProposalMode(
                    sandbox_only=bool((bundle.get("controls") or {}).get("sandbox_only", False)),
                    defensive=bool((bundle.get("controls") or {}).get("defensive_mode", False)),
                    probation=False,
                ),
                backend_builder_version=BACKEND_BUILDER_VERSION,
            ),
            quality="best_known",
        )
    return ReferenceAction(quality="none")


def build_episodes(data_dir: str, *, limit: int = 0, top_k: int = 20) -> List[EpisodeRecord]:
    paths = list_replay_bundles(data_dir)
    episodes: List[EpisodeRecord] = []
    last_outcomes: deque[LastOutcome] = deque(maxlen=8)
    for path in sorted(paths):
        with open(path, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        opps = list(bundle.get("opportunities") or [])
        opps_sorted = sorted(
            [TopOpportunity.model_validate(o) for o in opps],
            key=lambda x: (
                -max(0, _safe_int(x.expected_profit_after_costs_wei, 0)),
                -int(x.expected_profit_after_gas_usd_micro or x.expected_profit_usd_micro or 0),
                str(x.route_id or x.opportunity_id),
            ),
        )[: max(1, int(top_k or 20))]
        ctx = EpisodeContext(
            episode_id=make_episode_id(
                chain_id=int(bundle.get("chain_id") or 0),
                block_number=int(bundle.get("block_number") or 0),
                opportunity_id=str(bundle.get("opportunity_id") or ""),
                route_id=str(bundle.get("route_id") or ""),
                decision_id=str(bundle.get("decision_id") or ""),
            ),
            replay_event_id=str(bundle.get("event_id") or ""),
            decision_id=str(bundle.get("decision_id") or ""),
            chain=str(bundle.get("chain") or ""),
            chain_id=int(bundle.get("chain_id") or 0),
            block_number=int(bundle.get("block_number") or 0),
            opportunity_id=str(bundle.get("opportunity_id") or ""),
            route_id=str(bundle.get("route_id") or ""),
            v1_focus="flashloan_atomic",
            regime_state=str(
                (
                    (
                        (bundle.get("runtime") or {})
                        if isinstance(bundle.get("runtime"), dict)
                        else {}
                    ).get("regime", {})
                    or {}
                ).get("current")
                or "unknown"
            ),
            risk_state=(
                "defensive"
                if bool((bundle.get("controls") or {}).get("defensive_mode", False))
                else "normal"
            ),
            risk_caps=_risk_caps_from_bundle(bundle),
            breakers=_breaker_state_from_bundle(bundle),
            latency=_latency_from_bundle(bundle),
            last_outcomes=list(last_outcomes),
            top_opportunities=opps_sorted,
            controls=dict(bundle.get("controls") or {}),
            wealth_goal=dict(bundle.get("wealth_goal") or {}),
            capital_demand=_capital_demand_from_bundle(bundle),
            reward_trace=dict(bundle.get("reward_trace") or {}),
            execution_summary=dict(bundle.get("execution") or {}),
        )
        rec = EpisodeRecord(context=ctx, reference=_reference_action(bundle))
        episodes.append(rec)
        reward = (
            (bundle.get("reward_trace") or {})
            if isinstance(bundle.get("reward_trace"), dict)
            else {}
        )
        last_outcomes.append(
            LastOutcome(
                event_id=str(bundle.get("event_id") or ""),
                ok=bool(reward.get("ok", bundle.get("status") in {"dry_run", "settled"})),
                reward_scaled_ppm=int(reward.get("reward_scaled_ppm") or 0),
                realized_after_gas_usd_micro=int(
                    (
                        (
                            (bundle.get("decoded_receipt") or {})
                            if isinstance(bundle.get("decoded_receipt"), dict)
                            else {}
                        ).get("realized_profit_after_gas_usd_micro")
                        or 0
                    )
                ),
            )
        )
        if limit and len(episodes) >= int(limit):
            break
    return episodes


def export_episodes_jsonl(
    data_dir: str, out_path: str, *, limit: int = 0, top_k: int = 20
) -> Dict[str, Any]:
    eps = build_episodes(data_dir, limit=limit, top_k=top_k)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in eps:
            f.write(rec.model_dump_json() + "\n")
    return {"ok": True, "count": len(eps), "path": out_path}
