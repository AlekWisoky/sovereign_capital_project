"""Canonical OMAR-facing operator-intent compatibility surface.

The authority remains ``victor_ai_bot.operator_intent``; this module only
provides the OMAR namespace expected by the learning subsystem and tests.
"""

from ..operator_intent import intent_fingerprint, resolve_operator_intent

snapshot_operator_intent = resolve_operator_intent

__all__ = ["intent_fingerprint", "resolve_operator_intent", "snapshot_operator_intent"]
