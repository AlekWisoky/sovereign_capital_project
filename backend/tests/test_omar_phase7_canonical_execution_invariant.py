from __future__ import annotations

from types import SimpleNamespace

import pytest

from victor_ai_bot.omar.canonical_execution import (
    CanonicalExecutionInvariantError,
    require_canonical_execution_context,
)
from victor_ai_bot.runtime_core import RuntimeBundle


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(cfg=SimpleNamespace(chain=SimpleNamespace(name="ethereum")))


def test_canonical_execution_requires_trade_decision_and_identity():
    opportunity = SimpleNamespace(id="opp-1", route_id="route-1", meta={})
    with pytest.raises(CanonicalExecutionInvariantError, match="canonical_decision"):
        require_canonical_execution_context(_runtime(), opportunity, None, current_block=10)

    decision = SimpleNamespace(action="trade", metadata={})
    decision_id, correlation_id = require_canonical_execution_context(
        _runtime(), opportunity, decision, current_block=10
    )

    assert decision_id
    assert correlation_id
    assert decision.metadata["canonical_decision_id"] == decision_id
    assert decision.metadata["correlation_id"] == correlation_id


def test_canonical_execution_rejects_non_trade_action():
    opportunity = SimpleNamespace(id="opp-2", route_id="route-2", meta={})
    decision = SimpleNamespace(action="skip", metadata={})

    with pytest.raises(CanonicalExecutionInvariantError, match="requires_trade_decision"):
        require_canonical_execution_context(_runtime(), opportunity, decision, current_block=11)


def test_production_auto_dispatch_cannot_fallback_without_canonical_decision():
    assert RuntimeBundle._maybe_dispatch_auto_trade(
        object(), current_block=12, decision=None
    ) is False
