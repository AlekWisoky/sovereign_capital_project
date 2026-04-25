from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
import asyncio, os, time

try:
    from eth_account import Account  # type: ignore
except ImportError:  # pragma: no cover
    Account = None  # type: ignore
from .rpc import JsonRpcClient
from .gas import suggest_gas
from .safety import check_profit_and_repay
from .profitability_state import (
    build_profitability_state,
    build_terminal_profitability_authority,
    has_profitability_contract,
    post_mutation_revalidation_view,
    profitability_state_view,
    refresh_post_mutation_revalidation_contract,
    revalidate_profitability_state,
    assess_post_mutation_profitability_continuity,
)
from .calldata_builder import build_execute_calldata
from .abi_utils import extract_revert_data, decode_revert_data
from .arb_engine import requote_opportunity
from .cache import PerBlockCache
from .aqe.mev.evaluator import evaluate_adversarial_execution
from .execution_capture.route_execution_plan import apply_execution_route_plan
from .domain_errors import ExecutionError, RouteUnavailableError, SettlementRiskError
from .latency_profiler import LatencySpan
from .outcomes import ExecutionOutcome


@dataclass
class ExecResult:
    ok: bool
    dry_run: bool
    reason: str
    tx_hash: str = ""
    plan: Dict[str, Any] | None = None
    # Additive runtime semantics (not part of API contract; only used internally).
    attempted: bool = False
    submitted: bool = False


_SAFE_PROFILER_EXCEPTIONS = (AttributeError, TypeError, ValueError)
_SAFE_ROUTE_PLAN_EXCEPTIONS = (
    AttributeError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    ExecutionError,
    RouteUnavailableError,
    SettlementRiskError,
)
_SAFE_OPTIONAL_INTEGRATION_EXCEPTIONS = (
    AttributeError,
    IndexError,
    KeyError,
    RuntimeError,
    TypeError,
    ValueError,
)
_SAFE_OPTIONAL_RPC_EXCEPTIONS = (
    asyncio.TimeoutError,
    OSError,
    RuntimeError,
    ValueError,
)


def _mark_profiler(profiler: LatencySpan | None, stage: str) -> LatencySpan | None:
    if profiler is None:
        return None
    try:
        profiler.mark(stage)
        return profiler
    except _SAFE_PROFILER_EXCEPTIONS:
        return None


def _profiler_stages_ms(profiler: LatencySpan | None) -> Dict[str, float] | None:
    if profiler is None:
        return None
    try:
        return profiler.stages_ms()
    except _SAFE_PROFILER_EXCEPTIONS:
        return None


def _addr_from_key_hex(key_hex: str) -> str:
    if Account is None:
        raise RuntimeError("eth_account not installed")
    acct = Account.from_key(key_hex)
    return acct.address


def _int(s: str) -> int:
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def _execution_profitability_plan(
    *, sr: Any, amount_in: int, amount_out: int, reason: str
) -> Dict[str, Any]:
    return build_profitability_state(
        stage="execution_preflight_gate",
        source="execution",
        reason=str(reason or getattr(sr, "reason", "unknown")),
        revalidated=True,
        stale=False,
        valid=bool(getattr(sr, "ok", False)),
        gross_profit_wei=int(amount_out) - int(amount_in),
        profit_after_costs_wei=int(getattr(sr, "profit_after_costs_wei", 0) or 0),
        gas_cost_wei=int(getattr(sr, "gas_cost_wei", 0) or 0),
        flashloan_fee_wei=int(getattr(sr, "flashloan_fee_wei", 0) or 0),
        amount_in_wei=int(amount_in),
        amount_out_wei=int(amount_out),
    )


def _execution_terminal_authority(profitability_plan: Dict[str, Any]) -> Dict[str, Any]:
    return build_terminal_profitability_authority(profitability_plan, source="execution_plan")


def _execution_route_plan_already_applied(opp: Any, route_plan: Dict[str, Any]) -> bool:
    meta = getattr(opp, "meta", None)
    if not isinstance(meta, dict):
        return False
    if not bool(meta.get("execution_route_plan_applied")):
        return False
    applied_plan = meta.get("execution_route_plan")
    if not isinstance(applied_plan, dict):
        return False
    return applied_plan == route_plan


async def simulate_call(
    rpc: JsonRpcClient, *, to: str, data: str, from_addr: str, block_tag: str
) -> Tuple[bool, str]:
    r = await rpc.eth_call(to, data, block=block_tag, from_addr=from_addr)
    if r.ok:
        return True, "ok"
    rev = extract_revert_data(r.error)
    if rev:
        d = decode_revert_data(rev)
        if d.kind == "Error" and d.message:
            return False, f"simulation_revert:{d.message}"
        if d.kind == "Panic":
            return False, f"simulation_panic:{d.message}"
        if d.kind == "Custom" and d.selector:
            return False, f"simulation_custom_error:{d.selector}"
    return False, f"simulation_failed:{r.error}"


async def try_execute_opportunity(
    rpc_read: JsonRpcClient,
    rpc_send: JsonRpcClient,
    cfg,
    opp: Any,
    current_block: int,
    last_submitted_block: int,
    *,
    cache: PerBlockCache | None = None,
    decision: Any | None = None,
    force_dry_run: bool = False,
    mev_guard: Any | None = None,
    profiler: LatencySpan | None = None,
) -> ExecResult:
    # Observability-only stage profiling. MUST NOT affect decisions.
    profiler = _mark_profiler(profiler, "enter")
    effective_dry_run = bool(cfg.execution.dry_run or force_dry_run)
    decision_send_mode = (
        str(getattr(decision, "send_mode", "") or "") if decision is not None else ""
    )
    send_mode = decision_send_mode or str(getattr(cfg.execution, "send_mode", "public") or "public")
    # Enforce 1 tx per block
    if cfg.execution.max_submit_per_block >= 1 and last_submitted_block == current_block:
        return ExecResult(False, effective_dry_run, "throttled_one_tx_per_block")

    # Optional action overrides (RL / decision engine): size_mult and borrow_mult.
    size_mult = 1.0
    borrow_mult = 1.0
    try:
        if decision is not None:
            size_mult = float(getattr(decision, "size_mult", 1.0) or 1.0)
            borrow_mult = float(getattr(decision, "borrow_mult", 1.0) or 1.0)
        else:
            bm = (
                opp.meta.get("brain") if isinstance(getattr(opp, "meta", None), dict) else {}
            ) or {}
            size_mult = float(bm.get("size_mult") or 1.0)
            borrow_mult = float(bm.get("borrow_mult") or 1.0)
    except (AttributeError, TypeError, ValueError):
        size_mult = 1.0
        borrow_mult = 1.0

    # Amounts (base scanned amount)
    amount_in_base = int(getattr(opp.route.legs[0], "amount_in", "0") or "0")
    amount_in = int(amount_in_base)

    # Apply notional scaling. Upsizing requires re-quoting; we only do that for attempted trades.
    notional_mult = max(0.10, float(size_mult) * float(borrow_mult))
    if notional_mult != 1.0 and amount_in_base > 0:
        target = int(max(1, int(amount_in_base * notional_mult)))
        # Enforce max borrow cap (if configured)
        try:
            cap = int(getattr(cfg.safety, "max_borrow_amount", "0") or "0")
        except (AttributeError, TypeError, ValueError):
            cap = 0
        if cap > 0:
            target = min(target, cap)

        # Re-quote route for the target amount to keep min_outs consistent.
        if cache is not None:
            try:
                # Work on a copy to avoid mutating the shared state snapshot.
                opp = opp.copy(deep=True)
            except (AttributeError, TypeError, ValueError):
                pass
            rq = await requote_opportunity(
                rpc_read,
                cfg,
                cache,
                opp,
                new_amount_in=target,
                slippage_bps=int(cfg.safety.slippage_bps),
            )
            if rq is None:
                return ExecResult(False, effective_dry_run, "requote_failed", attempted=False)
            amount_in = target
        else:
            # Without a cache, stay conservative: do not upsize.
            amount_in = amount_in_base
    # Apply execution-grade route plan before calldata building. This is the deepest
    # safe in-architecture SOR mutation for the current atomic executor path.
    try:
        route_plan = (
            ((getattr(decision, "metadata", {}) or {}).get("execution_route_plan"))
            if decision is not None and isinstance(getattr(decision, "metadata", None), dict)
            else None
        )
        if isinstance(route_plan, dict) and not _execution_route_plan_already_applied(
            opp, route_plan
        ):
            opp = apply_execution_route_plan(opp=opp, plan=route_plan)
    except _SAFE_ROUTE_PLAN_EXCEPTIONS:
        return ExecResult(False, effective_dry_run, "route_plan_not_executable", attempted=False)

    # Safety MUST use the final slippage-aware min_out.
    try:
        amount_out = int(str(opp.min_outs[-1]))
    except (AttributeError, IndexError, TypeError, ValueError):
        amount_out = 0
    if amount_in <= 0 or amount_out <= 0:
        return ExecResult(False, effective_dry_run, "invalid_amounts")

    route_id = str(getattr(opp, "route_id", "") or "")

    post_mutation_contract = post_mutation_revalidation_view(opp)
    if post_mutation_contract and has_profitability_contract(opp):
        continuity = assess_post_mutation_profitability_continuity(
            opp,
            cfg,
            route_context=(route_plan if isinstance(route_plan, dict) else None),
            existing_continuity=(
                dict(post_mutation_contract.get("continuity") or {})
                if isinstance(post_mutation_contract, dict)
                else {}
            ),
        )
        if isinstance(getattr(opp, "meta", None), dict):
            opp.meta["profitability_continuity"] = dict(continuity)
        if not bool(continuity.get("valid", False)):
            post_mutation_contract = refresh_post_mutation_revalidation_contract(
                opp,
                cfg,
                stage="post_mutation_submission_gate",
                source="execution",
                route_context=(route_plan if isinstance(route_plan, dict) else None),
            )
    if not post_mutation_contract and has_profitability_contract(opp):
        post_mutation_contract = refresh_post_mutation_revalidation_contract(
            opp,
            cfg,
            stage="post_mutation_submission_gate",
            source="execution",
            route_context=(route_plan if isinstance(route_plan, dict) else None),
        )
    gate_profitability = (
        dict(post_mutation_contract.get("profitability") or {}) if post_mutation_contract else {}
    ) or profitability_state_view(opp)
    gate_reason = str(
        (
            post_mutation_contract.get("reason_code")
            if isinstance(post_mutation_contract, dict)
            else ""
        )
        or gate_profitability.get("reason")
        or ""
    )
    if (
        post_mutation_contract
        and gate_reason != "gas_cost_unavailable"
        and (
            (not bool(gate_profitability.get("authoritative", False)))
            or (not bool(gate_profitability.get("valid", False)))
        )
    ):
        return ExecResult(
            False,
            effective_dry_run,
            f"profitability_contract:{str(gate_reason or 'unavailable')}",
            attempted=False,
            plan={
                "amount_in": str(amount_in),
                "amount_out": str(amount_out),
                "profitability": dict(gate_profitability),
                "postMutationRevalidation": dict(post_mutation_contract),
                "route_id": route_id,
            },
        )
    if (
        (not post_mutation_contract)
        and has_profitability_contract(opp)
        and (
            (not bool(gate_profitability.get("authoritative", False)))
            or (not bool(gate_profitability.get("valid", False)))
        )
    ):
        revalidate_profitability_state(
            opp, cfg, stage="execution_preflight_gate", source="execution"
        )
        gate_profitability = profitability_state_view(opp)
        if str(gate_profitability.get("reason") or "") != "gas_cost_unavailable" and (
            (not bool(gate_profitability.get("authoritative", False)))
            or (not bool(gate_profitability.get("valid", False)))
        ):
            return ExecResult(
                False,
                effective_dry_run,
                f"profitability_contract:{str(gate_profitability.get('reason') or 'unavailable')}",
                attempted=False,
                plan={
                    "amount_in": str(amount_in),
                    "amount_out": str(amount_out),
                    "profitability": dict(gate_profitability),
                    "route_id": route_id,
                },
            )

    # Gas quote (EIP-1559-aware; bigint-safe conversions happen at API boundary).
    max_fee, prio = await suggest_gas(
        rpc_read, mode=cfg.execution.gas_mode, presets=cfg.execution.gas_presets
    )
    profiler = _mark_profiler(profiler, "gas")
    gas_limit_cfg = int(cfg.execution.gas_limit)

    # Determine sender used for simulation/estimateGas.
    key_hex = os.environ.get(cfg.execution.private_key_env, "").strip()
    from_addr = ""
    if key_hex and Account is not None:
        try:
            from_addr = _addr_from_key_hex(key_hex)
        except (RuntimeError, ValueError):
            from_addr = ""
    if not from_addr:
        from_addr = str(getattr(cfg.execution, "from_address", "") or "")

    executor = str(getattr(cfg.execution, "executor_address", "") or "")
    profit_to = str(getattr(cfg.execution, "profit_to", "") or "") or from_addr

    # Build calldata if executor is configured.
    calldata = "0x"
    if executor and profit_to:
        # On-chain minProfit uses configured thresholds (does not include gas).
        min_abs = int(cfg.safety.minProfitAbs)
        min_bps = int(cfg.safety.minProfitBps)
        min_profit_onchain = max(min_abs, amount_in * min_bps // 10_000)
        deadline = int(time.time()) + int(getattr(cfg.execution, "deadline_seconds", 30))
        legs = []
        for leg in opp.route.legs:
            legs.append(
                {
                    "dex": leg.dex,
                    "venue": leg.venue,
                    "token_in": leg.token_in,
                    "token_out": leg.token_out,
                    "min_out": int(str(leg.min_out)),
                    "aux": leg.data or "0x",
                }
            )
        provider_hint = str(
            (
                ((getattr(decision, "metadata", {}) or {}).get("provider_hint"))
                if decision is not None and isinstance(getattr(decision, "metadata", None), dict)
                else ""
            )
            or getattr(cfg.execution, "flash_provider", "aave")
            or "aave"
        )
        calldata, rid = build_execute_calldata(
            provider=provider_hint,
            borrow_token=opp.route.legs[0].token_in,
            amount_borrow=amount_in,
            min_profit=min_profit_onchain,
            profit_to=profit_to,
            deadline=deadline,
            legs=legs,
        )
        if not route_id:
            route_id = rid
    elif executor and not profit_to:
        # Cannot simulate/estimateGas without a sender/profit destination.
        calldata = "0x"

    profiler = _mark_profiler(profiler, "calldata")

    # estimateGas gate (if enabled and we can build a real tx). When simulation is also required,
    # run the current-block simulation in parallel to reduce hot-path latency.
    gas_limit = gas_limit_cfg
    est_gas_pre: int | None = None
    parallel_simulation: Tuple[bool, str] | None = None
    tx_for_est = None
    if executor and calldata != "0x" and from_addr:
        tx_for_est = {
            "to": executor,
            "from": from_addr,
            "data": calldata,
            "value": hex(0),
        }
    if tx_for_est is not None and cfg.safety.require_estimate_gas and cfg.safety.require_simulation:
        tag0 = hex(int(current_block))
        est, sim = await asyncio.gather(
            rpc_read.estimate_gas(tx_for_est),
            simulate_call(
                rpc_read, to=executor, data=calldata, from_addr=from_addr, block_tag=tag0
            ),
        )
        parallel_simulation = sim
        if est is None:
            return ExecResult(False, effective_dry_run, "estimateGas_failed_abort", attempted=False)
        mult = float(os.environ.get("VICTOR_GAS_SAFETY_MULT", "1.20"))
        gas_limit = int(max(gas_limit_cfg, int(est * mult)))
        est_gas_pre = int(est)
    elif tx_for_est is not None and cfg.safety.require_estimate_gas:
        est = await rpc_read.estimate_gas(tx_for_est)
        if est is None:
            return ExecResult(False, effective_dry_run, "estimateGas_failed_abort", attempted=False)
        mult = float(os.environ.get("VICTOR_GAS_SAFETY_MULT", "1.20"))
        gas_limit = int(max(gas_limit_cfg, int(est * mult)))
        est_gas_pre = int(est)

    profiler = _mark_profiler(profiler, "estimate")

    gas_cost = max_fee * gas_limit

    # Safety rails (CRITICAL RULE #1: repay + gas + thresholds)
    min_abs = int(cfg.safety.minProfitAbs)
    min_bps = int(cfg.safety.minProfitBps)
    fee_bps = int(cfg.execution.flashloan_fee_bps)
    sr = check_profit_and_repay(
        amount_in_wei=amount_in,
        amount_out_wei=amount_out,
        min_profit_abs_wei=min_abs,
        min_profit_bps=min_bps,
        flashloan_fee_bps=fee_bps,
        gas_cost_wei=gas_cost,
    )
    profitability_plan = _execution_profitability_plan(
        sr=sr, amount_in=amount_in, amount_out=amount_out, reason=getattr(sr, "reason", "unknown")
    )
    terminal_authority = _execution_terminal_authority(profitability_plan)
    if not sr.ok:
        return ExecResult(
            False,
            effective_dry_run,
            f"safety:{sr.reason}",
            attempted=False,
            plan={
                "amount_in": str(amount_in),
                "amount_out": str(amount_out),
                "size_mult": float(size_mult),
                "borrow_mult": float(borrow_mult),
                "flashloan_fee": str(sr.flashloan_fee_wei),
                "gas_cost": str(sr.gas_cost_wei),
                "profit_after_costs": str(sr.profit_after_costs_wei),
                "profitability": profitability_plan,
                "terminalProfitabilityAuthority": terminal_authority,
                "postMutationRevalidation": dict(post_mutation_contract or {}),
                "max_fee": str(max_fee),
                "priority_fee": str(prio),
                "gas_limit": gas_limit,
                "route_id": route_id,
                "executor": executor,
                "calldata": (calldata if (send_mode == "public") else "0x"),
            },
        )

    profiler = _mark_profiler(profiler, "safety")

    # Optional Phase 6: MEV guardrail (defensive-first).
    mev_info: Dict[str, Any] = {}
    try:
        if mev_guard is not None:
            d = mev_guard.assess(opp=opp, send_mode=str(send_mode))
            mev_info = {
                "allow": bool(getattr(d, "allow", True)),
                "risk": float(getattr(d, "risk", 0.0)),
                "reason": str(getattr(d, "reason", "")),
                "suggested_send_mode": str(getattr(d, "suggested_send_mode", "")),
                "meta": dict(getattr(d, "meta", {}) or {}),
            }
            # Hard safety rail: refuse public send in high-risk mempool when configured.
            if (not effective_dry_run) and (not mev_info.get("allow", True)):
                return ExecResult(
                    False,
                    False,
                    str(mev_info.get("reason") or "mev_guard_block"),
                    attempted=False,
                    plan={
                        "amount_in": str(amount_in),
                        "amount_out": str(amount_out),
                        "profit_after_costs": str(sr.profit_after_costs_wei),
                        "gas_cost": str(sr.gas_cost_wei),
                        "route_id": route_id,
                        "mev_guard": mev_info,
                    },
                )
    except _SAFE_OPTIONAL_INTEGRATION_EXCEPTIONS:
        mev_info = {}

    # Optional Phase 6b: Adversarial MEV + slippage-aware EV filter.
    # This is a planning guardrail to reduce negative-EV attempts under
    # contention. It does NOT replace on-chain profit assertions.
    adv_info: Dict[str, Any] = {}
    try:
        if bool(getattr(cfg.safety, "mev_adversarial_eval_enabled", True)):
            # p_success from decision engine (if present)
            p_base = 0.75
            if isinstance(getattr(opp, "meta", None), dict):
                brain = opp.meta.get("brain") if isinstance(opp.meta.get("brain"), dict) else {}
                if isinstance(brain, dict) and ("p_success" in brain):
                    p_base = float(brain.get("p_success") or p_base)

            # Expected out (non-slippage haircutted) from meta outN / outs list
            expected_out = 0
            if isinstance(getattr(opp, "meta", None), dict):
                try:
                    nlegs = len(getattr(getattr(opp, "route", None), "legs", []) or [])
                    k = f"out{int(nlegs)}"
                    v = opp.meta.get(k)
                    if (
                        v is None
                        and isinstance(opp.meta.get("outs"), list)
                        and opp.meta.get("outs")
                    ):
                        v = opp.meta.get("outs")[-1]
                    if v is not None:
                        expected_out = int(v)
                except _SAFE_OPTIONAL_INTEGRATION_EXCEPTIONS:
                    expected_out = 0

            # Min out is enforced in calldata (already computed)
            min_out = int(amount_out)

            # MEV risk adjusted by send mode (private reduces public mempool exposure)
            risk = float(mev_info.get("risk", 0.0) or 0.0)
            if str(send_mode) == "private":
                risk = float(risk) * 0.35

            adv = evaluate_adversarial_execution(
                amount_in_wei=int(amount_in),
                min_amount_out_wei=int(min_out),
                expected_amount_out_wei=int(expected_out),
                flashloan_fee_wei=int(sr.flashloan_fee_wei),
                gas_cost_wei=int(sr.gas_cost_wei),
                p_success_base=float(p_base),
                mev_risk=float(risk),
                mev_fail_prob_scale=float(getattr(cfg.safety, "mev_fail_prob_scale", 0.55) or 0.55),
                gas_premium_mult=float(getattr(cfg.safety, "mev_gas_premium_mult", 0.35) or 0.35),
            )
            adv_info = {
                "ok": bool(adv.ok),
                "expected_value_wei": str(int(adv.expected_value_wei)),
                "score": float(adv.score),
                "meta": dict(adv.meta or {}),
            }

            # Gate only for live execution (not dry runs)
            if (
                (not effective_dry_run)
                and bool(getattr(cfg.safety, "require_adversarial_ev_positive", True))
                and (not bool(adv.ok))
            ):
                return ExecResult(
                    False,
                    False,
                    "adversarial_ev_negative",
                    attempted=False,
                    plan={
                        "amount_in": str(amount_in),
                        "amount_out": str(amount_out),
                        "profit_after_costs": str(sr.profit_after_costs_wei),
                        "gas_cost": str(sr.gas_cost_wei),
                        "route_id": route_id,
                        "mev_guard": mev_info,
                        "mev_adversarial": adv_info,
                    },
                )
    except _SAFE_OPTIONAL_INTEGRATION_EXCEPTIONS:
        adv_info = {}

    # If dry_run, stop here (safe default). If executor is configured, we treat this
    # as a would-execute attempt.
    if effective_dry_run:
        return ExecResult(
            True,
            True,
            ("dry_run_ok" if executor else "dry_run_ok_no_executor"),
            attempted=bool(executor),
            plan={
                "amount_in": str(amount_in),
                "amount_out": str(amount_out),
                "size_mult": float(size_mult),
                "borrow_mult": float(borrow_mult),
                "flashloan_fee": str(sr.flashloan_fee_wei),
                "gas_cost": str(sr.gas_cost_wei),
                "profit_after_costs": str(sr.profit_after_costs_wei),
                "profitability": profitability_plan,
                "terminalProfitabilityAuthority": terminal_authority,
                "postMutationRevalidation": dict(post_mutation_contract or {}),
                "slippage_model": (
                    opp.meta.get("slippage_model")
                    if isinstance(getattr(opp, "meta", None), dict)
                    else {}
                ),
                "gas_mode": cfg.execution.gas_mode,
                "send_mode": send_mode,
                "mev_guard": mev_info,
                "mev_adversarial": adv_info,
                "route_id": route_id,
                "executor": executor,
                "note": "Set execution.dry_run=false and provide signing key + deployed executor_address to actually send.",
                "current_block": int(current_block),
                "slippage_bps": int(getattr(cfg.safety, "slippage_bps", 50) or 50),
                "deadline_seconds": int(getattr(cfg.execution, "deadline_seconds", 30) or 30),
            },
        )

    # Live execution requires key + executor address (safe default)
    if not key_hex:
        return ExecResult(False, False, "missing_private_key_env", attempted=False)
    if not executor:
        return ExecResult(False, False, "missing_executor_address", attempted=False)
    if Account is None:
        return ExecResult(False, False, "missing_eth_account_dependency", attempted=False)

    acct = Account.from_key(key_hex)
    from_addr = acct.address

    # Build calldata must be available now.
    if calldata == "0x":
        return ExecResult(False, False, "missing_calldata", attempted=False)

    simulation_info: Dict[str, Any] = {}
    if cfg.safety.require_simulation:
        simulation_details: Dict[str, Any] = {}
        tag0 = hex(int(current_block))
        if parallel_simulation is not None:
            ok0, reason0 = parallel_simulation
        else:
            ok0, reason0 = await simulate_call(
                rpc_read, to=executor, data=calldata, from_addr=from_addr, block_tag=tag0
            )
        simulation_details["block_current"] = {
            "tag": str(tag0),
            "ok": bool(ok0),
            "reason": str(reason0),
        }
        if not ok0:
            simulation_info = simulation_details
            return ExecResult(
                False,
                False,
                reason0,
                attempted=True,
                plan={"simulation": simulation_info, "route_id": route_id},
            )

        # Optional previous blocks (detect instability across short horizons)
        try:
            prev_n = int(getattr(cfg.safety, "simulation_prev_blocks", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            prev_n = 0
        if prev_n > 0:
            bn = int(current_block)
            for i in range(1, max(0, prev_n) + 1):
                if bn <= 0:
                    break
                tag = hex(max(0, bn - i))
                ok_i, rs_i = await simulate_call(
                    rpc_read, to=executor, data=calldata, from_addr=from_addr, block_tag=tag
                )
                simulation_details[f"block_prev_{i}"] = {
                    "tag": str(tag),
                    "ok": bool(ok_i),
                    "reason": str(rs_i),
                }
                if (not ok_i) and (not bool(getattr(cfg.safety, "simulation_soft_fail", True))):
                    simulation_info = simulation_details
                    return ExecResult(
                        False,
                        False,
                        rs_i,
                        attempted=True,
                        plan={"simulation": simulation_info, "route_id": route_id},
                    )

        # Optional pending simulation (node support varies)
        if bool(getattr(cfg.safety, "simulation_try_pending", False)):
            try:
                okp, rsp = await simulate_call(
                    rpc_read, to=executor, data=calldata, from_addr=from_addr, block_tag="pending"
                )
                simulation_details["pending"] = {
                    "tag": "pending",
                    "ok": bool(okp),
                    "reason": str(rsp),
                }
                if (not okp) and (not bool(getattr(cfg.safety, "simulation_soft_fail", True))):
                    simulation_info = simulation_details
                    return ExecResult(
                        False,
                        False,
                        rsp,
                        attempted=True,
                        plan={"simulation": simulation_info, "route_id": route_id},
                    )
            except _SAFE_OPTIONAL_RPC_EXCEPTIONS as e:
                simulation_details["pending"] = {"tag": "pending", "ok": False, "reason": str(e)}

        simulation_info = simulation_details

    profiler = _mark_profiler(profiler, "simulate")

    tx: Dict[str, Any] = {
        "to": executor,
        "from": from_addr,
        "data": calldata,
        "value": hex(0),
        "chainId": cfg.chain.chain_id,
    }

    # Gas estimate is required when configured, otherwise use configured gas_limit.
    if cfg.safety.require_estimate_gas:
        est2 = est_gas_pre
        if est2 is None:
            est2 = await rpc_read.estimate_gas(tx)
        if est2 is None:
            return ExecResult(False, False, "estimateGas_failed_abort", attempted=True)
        mult = float(os.environ.get("VICTOR_GAS_SAFETY_MULT", "1.20"))
        gas_limit = max(gas_limit, int(int(est2) * mult))

    nonce = await rpc_read.get_nonce(from_addr)
    if nonce is None:
        return ExecResult(False, False, "nonce_fetch_failed")

    # EIP-1559 tx fields
    tx2 = {
        "to": executor,
        "nonce": nonce,
        "data": bytes.fromhex(calldata[2:]) if calldata.startswith("0x") else b"",
        "value": 0,
        "gas": gas_limit,
        "maxFeePerGas": max_fee,
        "maxPriorityFeePerGas": prio,
        "chainId": cfg.chain.chain_id,
        "type": 2,
    }
    signed = Account.sign_transaction(tx2, key_hex)
    raw = "0x" + signed.raw_transaction.hex()

    profiler = _mark_profiler(profiler, "sign")

    # Send modes
    if send_mode == "private":
        r = await rpc_send.send_private_tx(raw, max_block_number=current_block + 2)
    else:
        r = await rpc_send.send_raw_tx(raw)

    profiler = _mark_profiler(profiler, "send")

    if not r.ok or not isinstance(r.result, str):
        failure_plan: Dict[str, Any] = {
            "route_id": route_id,
            "simulation": simulation_info,
            "mev_guard": mev_info,
            "mev_adversarial": adv_info,
        }
        latency_stages = _profiler_stages_ms(profiler)
        if latency_stages is not None:
            failure_plan["latency_stages_ms"] = latency_stages
        return ExecResult(False, False, f"send_failed:{r.error}", attempted=True, plan=failure_plan)

    send_plan: Dict[str, Any] = {
        "tx_hash": r.result,
        "profit_after_costs": str(sr.profit_after_costs_wei),
        "profitability": profitability_plan,
        "terminalProfitabilityAuthority": terminal_authority,
        "postMutationRevalidation": dict(post_mutation_contract or {}),
        "slippage_model": (
            opp.meta.get("slippage_model") if isinstance(getattr(opp, "meta", None), dict) else {}
        ),
        "amount_in": str(amount_in),
        "size_mult": float(size_mult),
        "borrow_mult": float(borrow_mult),
        "gas_limit": gas_limit,
        "max_fee": str(max_fee),
        "priority_fee": str(prio),
        "send_mode": send_mode,
        "simulation": simulation_info,
        "mev_guard": mev_info,
        "mev_adversarial": adv_info,
        "route_id": route_id,
        "current_block": int(current_block),
        "slippage_bps": int(getattr(cfg.safety, "slippage_bps", 50) or 50),
        "deadline_seconds": int(getattr(cfg.execution, "deadline_seconds", 30) or 30),
    }
    latency_stages = _profiler_stages_ms(profiler)
    if latency_stages is not None:
        send_plan["latency_stages_ms"] = latency_stages

    return ExecResult(
        True, False, "sent", tx_hash=r.result, attempted=True, submitted=True, plan=send_plan
    )


def execution_outcome_from_result(result: ExecResult) -> ExecutionOutcome:
    reason = str(getattr(result, "reason", "") or "unknown")
    degraded = ""
    retryable = False
    status = "accepted" if bool(result.ok) else "failed"
    if reason in {"throttled_one_tx_per_block", "requote_failed", "nonce_fetch_failed"}:
        status = "dropped"
        retryable = True
    if reason in {
        "estimateGas_failed_abort",
        "missing_calldata",
        "simulation_failed",
    } or reason.startswith("simulation_"):
        degraded = "observe_only"
        retryable = False
    if reason in {
        "adversarial_ev_negative",
        "missing_private_key_env",
        "missing_executor_address",
        "missing_eth_account_dependency",
    }:
        status = "degraded"
        degraded = "private_only" if reason == "adversarial_ev_negative" else "disabled"
    if reason == "invalid_amounts":
        raise SettlementRiskError("invalid_amounts", reason_code="invalid_amounts")
    if reason == "requote_failed":
        raise RouteUnavailableError("requote_failed", reason_code="route_unavailable")
    return ExecutionOutcome(
        status=status,
        reason_code=reason,
        retryable=retryable,
        degraded_mode=degraded,
        tx_hash=str(getattr(result, "tx_hash", "") or ""),
        details=dict(getattr(result, "plan", None) or {}),
    )
