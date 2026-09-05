from __future__ import annotations


def test_omar_production_identity_bootstrap_is_installed_at_runtime_import():
    """Production imports install identity/settlement hooks without manual test setup."""
    from victor_ai_bot.omar import lifecycle_bridge, production_lineage_bridge
    from victor_ai_bot.runtime_services.canonical_settlement_interface import (
        install_canonical_settlement_interface,
    )
    from victor_ai_bot.runtime_services.execution_service import ExecutionService
    from victor_ai_bot.runtime_services.runtime_decision_facade import RuntimeDecisionFacade
    from victor_ai_bot.runtime_services.runtime_receipt_facade import RuntimeReceiptFacade

    install_canonical_settlement_interface()

    assert getattr(
        RuntimeDecisionFacade._apply_omar_to_candidate,
        "_production_identity_patched",
        False,
    ) is True
    assert getattr(
        RuntimeDecisionFacade._omar_context,
        "_production_context_patched",
        False,
    ) is True
    assert getattr(
        ExecutionService.handle_post_execute_bookkeeping,
        "_production_identity_patched",
        False,
    ) is True
    assert getattr(
        ExecutionService._build_pending_submission,
        "_production_pending_patched",
        False,
    ) is True
    assert getattr(
        RuntimeReceiptFacade.canonical_settled_outcome,
        "_phase2_canonical_interface",
        False,
    ) is True
    assert callable(getattr(lifecycle_bridge, "_canonical_settled_outcome", None))
    assert callable(getattr(production_lineage_bridge, "install_production_lineage_bridge", None))
