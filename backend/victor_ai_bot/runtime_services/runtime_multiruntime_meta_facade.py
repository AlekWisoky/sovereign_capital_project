from __future__ import annotations

from .control_state import unavailable_state


class RuntimeMultiruntimeMetaFacade:
    """Meta-evolution compatibility helpers for MultiRuntimeBundle.

    These methods are non-hot-path operator/control helpers and do not belong
    inside the runtime monolith's top-level multichain shell.
    """

    @staticmethod
    def _meta_disabled_state() -> dict:
        payload = unavailable_state("meta_unavailable", extra={"enabled": False})
        payload["ok"] = True
        payload["reason"] = "unavailable"
        return payload

    @staticmethod
    def _meta_action_unavailable(**extra) -> dict:
        return unavailable_state("meta_unavailable", include_error=True, extra=extra or None)

    @staticmethod
    def _meta_failed(error: str, exc: Exception, *, extra: dict | None = None) -> dict:
        payload = {
            "ok": False,
            "status": "degraded",
            "reason_code": error,
            "error": f"{error}:{exc}",
        }
        if extra:
            payload.update(dict(extra))
        return payload

    def meta_state(self) -> dict:
        if getattr(self, "_meta", None) is None:
            return self._meta_disabled_state()
        try:
            return self._meta.state()
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            return self._meta_failed("meta_state_failed", e)

    def meta_start(self) -> bool:
        if getattr(self, "_meta", None) is None:
            return False
        try:
            self._meta.start()
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    async def meta_stop(self) -> bool:
        if getattr(self, "_meta", None) is None:
            return False
        try:
            await self._meta.stop()
            return True
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

    def meta_generate(self) -> dict:
        if getattr(self, "_meta", None) is None:
            return self._meta_action_unavailable(candidates=[])
        try:
            cands = self._meta.generate(self)
            return {"ok": True, "candidates": cands}
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            return self._meta_failed("meta_generate_failed", e, extra={"candidates": []})

    def meta_apply(self, cand_id: str) -> dict:
        if getattr(self, "_meta", None) is None:
            return self._meta_action_unavailable(id=str(cand_id or ""))
        try:
            return self._meta.apply_candidate(self, cand_id)
        except (AttributeError, RuntimeError, TypeError, ValueError) as e:
            return self._meta_failed("meta_apply_failed", e, extra={"id": str(cand_id or "")})
