from __future__ import annotations

import asyncio
from typing import Optional


_SAFE_OVERLAY_EXCEPTIONS = (
    AttributeError,
    KeyError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)


class RuntimeOverlayFacade:
    """Operator overlay and governance compatibility facade.

    This isolates superstructure, governance, FIOA, and narrative overlay
    compatibility methods away from RuntimeBundle's orchestration loop while
    preserving the existing public method surface.
    """

    # -------------------------
    # Phase 14+: Superstructure
    # -------------------------
    def superstructure_state(self) -> dict:
        return self._auxiliary_state_service.superstructure_state(self)

    def superstructure_pause(self, agent_id: str) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            return bool(
                self._super.registry.set_suspended(str(agent_id), True, reason="human_pause")
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def superstructure_resume(self, agent_id: str) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            return bool(
                self._super.registry.set_suspended(str(agent_id), False, reason="human_resume")
            )
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def superstructure_command_state(self) -> dict:
        return self._auxiliary_state_service.superstructure_command_state(self)

    def superstructure_set_directive(self, directive: dict, *, ttl_s: float = 6 * 3600.0) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            self._super.set_directive(dict(directive or {}), ttl_s=float(ttl_s or 0.0))
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def superstructure_set_risk_multiplier(self, m: float) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            cmd = getattr(self._super, "command", None)
            if cmd is None:
                return False
            cmd.set_risk_multiplier(float(m))
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def superstructure_set_exploration_cap(self, cap: float) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            cmd = getattr(self._super, "command", None)
            if cmd is None:
                return False
            cmd.set_exploration_cap(float(cap))
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def superstructure_approve(self, proposal_id: str, *, ttl_s: float = 600.0) -> bool:
        if getattr(self, "_super", None) is None:
            return False
        try:
            cmd = getattr(self._super, "command", None)
            if cmd is None:
                return False
            cmd.approve(str(proposal_id), ttl_s=float(ttl_s or 0.0))
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def superstructure_force_safe_mode(self, *, ttl_s: float = 120.0, reason: str = "") -> bool:
        if getattr(self, "_super", None) is None:
            return False

        try:
            self._super.force_safe_mode(ttl_s=float(ttl_s or 0.0), reason=str(reason or ""))
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    # -------------------------
    # Phase 19: GMAO Governance
    # -------------------------
    def governance_state(self) -> dict:
        return self._auxiliary_state_service.governance_state(self)

    def governance_health(self) -> dict:
        return self._auxiliary_state_service.governance_health(self)

    # -------------------------
    # Phase 20: FIOA (FIU-inspired Operational Independence)
    # -------------------------
    def fioa_state(self) -> dict:
        return self._auxiliary_state_service.fioa_state(self)

    def fioa_audit_tail(self, limit: int = 200) -> dict:
        return self._auxiliary_state_service.fioa_audit_tail(self, limit=int(limit))

    def fioa_restrict_agent(self, agent_id: str, reason: str = "") -> bool:
        if getattr(self, "_fioa", None) is None:
            return False
        try:
            self._fioa.restrict_agent(str(agent_id), reason=str(reason or ""))
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def fioa_resume_agent(self, agent_id: str) -> bool:
        if getattr(self, "_fioa", None) is None:
            return False
        try:
            return bool(self._fioa.resume_agent(str(agent_id)))
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def fioa_set_safe_mode(self, on: bool, *, ttl_s: float = 120.0, reason: str = "") -> bool:
        if getattr(self, "_fioa", None) is None:
            return False

        try:
            self._fioa._set_safe_mode(bool(on), ttl_s=float(ttl_s or 0.0), reason=str(reason or ""))
            if on:
                self.set_settings(auto_trading=False)
            return True
        except _SAFE_OVERLAY_EXCEPTIONS:
            return False

    def fioa_governance_report(self, limit_audit: int = 200) -> dict:
        return self._auxiliary_state_service.fioa_governance_report(
            self, limit_audit=int(limit_audit)
        )

    # -------------------------
    # Phase 21: LLM-INL (Interactive Narrative Layer)
    # -------------------------
    def narrative_state(self) -> dict:
        return self._auxiliary_state_service.narrative_state(self)

    def narrative_history(self, limit: int = 100) -> dict:
        return self._auxiliary_state_service.narrative_history(self, limit=int(limit))

    def narrative_report(self, limit: int = 100) -> dict:
        return self._auxiliary_state_service.narrative_report(self, limit=int(limit))

    def narrative_set_level(self, level: str) -> dict:
        return self._auxiliary_state_service.narrative_set_level(self, str(level))

    async def narrative_query(
        self, agent_id: str, query_text: str, *, data_level: str = "INTERNAL_STRATEGY"
    ) -> dict:
        return await self._auxiliary_state_service.narrative_query(
            self,
            agent_id=str(agent_id),
            query_text=str(query_text),
            data_level=str(data_level),
        )

    async def narrative_insights(self) -> dict:
        return await self._auxiliary_state_service.narrative_insights(self)

    def narrative_subscribe(self) -> Optional[asyncio.Queue]:
        if getattr(self, "_inl", None) is None:
            return None
        try:
            return self._inl.subscribe()
        except AttributeError:
            return None

    def narrative_unsubscribe(self, q: asyncio.Queue) -> None:
        if getattr(self, "_inl", None) is None:
            return
        try:
            self._inl.unsubscribe(q)
        except _SAFE_OVERLAY_EXCEPTIONS:
            return
