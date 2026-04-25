from __future__ import annotations

import os
from typing import List

from ..gas import suggest_gas
from ..models import Opportunity
from ..rpc import JsonRpcClient
from ..safety import check_profit_and_repay

_SAFE_CAN_EXECUTE_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeCanExecuteFacade:
    """Execution-readiness annotation compatibility facade."""

    async def _annotate_can_execute(self, rpc: JsonRpcClient, opps: List[Opportunity]) -> None:
        """Populate Opportunity.can_execute for top opportunities."""
        topn = int(os.environ.get("VICTOR_CAN_EXECUTE_TOPN", "10"))
        if topn <= 0 or not opps:
            return

        max_fee, prio = await suggest_gas(
            rpc, mode=self.cfg.execution.gas_mode, presets=self.cfg.execution.gas_presets
        )
        gas_limit = int(self.cfg.execution.gas_limit)
        gas_cost = int(max_fee) * int(gas_limit)

        executor_addr = str(getattr(self.cfg.execution, "executor_address", "") or "")
        has_executor = bool(executor_addr)
        has_univ3_router = bool(getattr(self.cfg.chain, "univ3_swap_router", "") or "")
        has_balancer_vault = bool(getattr(self.cfg.chain, "balancer_vault", "") or "")

        key_env = str(
            getattr(self.cfg.execution, "private_key_env", "VICTOR_PRIVATE_KEY")
            or "VICTOR_PRIVATE_KEY"
        )
        signing_ready = bool(os.environ.get(key_env, "").strip())

        for o in opps[:topn]:
            try:
                amount_in = int(o.route.legs[0].amount_in)
            except _SAFE_CAN_EXECUTE_EXCEPTIONS:
                amount_in = 0
            try:
                amount_out = int(o.min_outs[-1])
            except _SAFE_CAN_EXECUTE_EXCEPTIONS:
                amount_out = 0

            if amount_in <= 0 or amount_out <= 0:
                o.can_execute = False
                o.meta["safety"] = {
                    "ok": False,
                    "reason": "invalid_amounts",
                    "exec_ready": False,
                }
                continue

            sr = check_profit_and_repay(
                amount_in_wei=amount_in,
                amount_out_wei=amount_out,
                min_profit_abs_wei=int(self.cfg.safety.minProfitAbs),
                min_profit_bps=int(self.cfg.safety.minProfitBps),
                flashloan_fee_bps=int(self.cfg.execution.flashloan_fee_bps),
                gas_cost_wei=gas_cost,
            )

            missing: list[str] = []
            for leg in o.route.legs:
                if leg.dex == "univ3" and not has_univ3_router:
                    missing.append("univ3_swap_router")
                if leg.dex == "balancer" and not has_balancer_vault:
                    missing.append("balancer_vault")

            route_ready = bool(has_executor and not missing)
            exec_ready = bool(
                route_ready
                and (bool(getattr(self.cfg.execution, "dry_run", True)) or signing_ready)
            )

            o.can_execute = bool(sr.ok)
            o.meta["safety"] = {
                "ok": bool(sr.ok),
                "reason": ("ok" if sr.ok else sr.reason),
                "is_safe": bool(sr.ok),
                "exec_ready": bool(exec_ready),
                "route_ready": bool(route_ready),
                "has_executor": bool(has_executor),
                "executor_address": (executor_addr if has_executor else ""),
                "signing_ready": bool(signing_ready),
                "missing": missing,
                "amount_out_final_wei": str(amount_out),
                "flashloan_fee_wei": str(sr.flashloan_fee_wei),
                "gas_limit": int(gas_limit),
                "max_fee_wei": str(int(max_fee)),
                "priority_fee_wei": str(int(prio)),
                "gas_cost_wei": str(int(gas_cost)),
                "profit_after_costs_wei": str(sr.profit_after_costs_wei),
            }
