from __future__ import annotations

from typing import Any, Dict, List

from ..jsonsafe import to_json_safe


class RuntimeReplayFacade:
    """Replay/export compatibility facade.

    This isolates replay snapshot/export helpers away from RuntimeBundle's
    orchestration loop while preserving the existing compatibility surface.
    These methods are non-hot-path helpers used to assemble replay bundles and
    operator-visible replay context.
    """

    def _controls_for_replay(self) -> Dict[str, Any]:
        svc = getattr(self, "_replay_service", None)
        return to_json_safe(svc.controls_for_replay(self)) if svc is not None else {}

    def _wealth_goal_for_replay(self) -> Dict[str, Any]:
        svc = getattr(self, "_replay_service", None)
        return to_json_safe(svc.wealth_goal_for_replay(self)) if svc is not None else {}

    def _runtime_context_for_replay(self) -> Dict[str, Any]:
        svc = getattr(self, "_replay_service", None)
        return to_json_safe(svc.runtime_context_for_replay(self)) if svc is not None else {}

    def _top_opportunities_for_replay(self) -> List[Dict[str, Any]]:
        svc = getattr(self, "_replay_service", None)
        return to_json_safe(svc.top_opportunities_for_replay(self)) if svc is not None else []

    def _replay_export_enabled(self) -> bool:
        svc = getattr(self, "_replay_service", None)
        return bool(svc.replay_export_enabled(self)) if svc is not None else False

    def _create_replay_bundle(
        self,
        *,
        opportunity_id: str,
        route_id: str,
        mode: str,
        rl_state: str,
        rl_action: int,
        latency_ms: int,
        plan: Dict[str, Any],
        dry_run: bool,
        ok: bool,
        attempted: bool,
        submitted: bool,
        reason: str,
        tx_hash: str = "",
        audit_hash: str = "",
        block_number: int = 0,
        status: str = "draft",
    ) -> str:
        svc = getattr(self, "_replay_service", None)
        if svc is None:
            return ""
        return str(
            svc.create_bundle(
                self,
                opportunity_id=opportunity_id,
                route_id=route_id,
                mode=mode,
                rl_state=rl_state,
                rl_action=rl_action,
                latency_ms=latency_ms,
                plan=plan,
                dry_run=dry_run,
                ok=ok,
                attempted=attempted,
                submitted=submitted,
                reason=reason,
                tx_hash=tx_hash,
                audit_hash=audit_hash,
                block_number=block_number,
                status=status,
            )
            or ""
        )
