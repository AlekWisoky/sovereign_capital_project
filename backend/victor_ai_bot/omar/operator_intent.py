"""Canonical OMAR-facing operator-intent compatibility surface.

The authority remains ``victor_ai_bot.operator_intent``. This module keeps the
historical OMAR snapshot call shape while delegating all authority to the
canonical resolver.
"""

from __future__ import annotations

from typing import Any

from ..operator_intent import intent_fingerprint, resolve_operator_intent


def snapshot_operator_intent(
    runtime: Any,
    opportunity: Any = None,
    decision: Any = None,
) -> tuple[dict[str, Any], str]:
    """Return the canonical intent snapshot and fingerprint.

    ``opportunity`` and ``decision`` are retained as compatibility inputs. The
    operator intent itself is resolved only from canonical runtime controls,
    wealth-goal state, and runtime recommendation state; decision persistence
    remains the responsibility of the decision-identity layer.
    """
    intent = resolve_operator_intent(runtime)
    return intent, intent_fingerprint(intent)


__all__ = ["intent_fingerprint", "resolve_operator_intent", "snapshot_operator_intent"]
