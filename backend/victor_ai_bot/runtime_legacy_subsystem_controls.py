from __future__ import annotations

"""Compatibility surface for legacy subsystem-control typed slices.

This module preserves the declared mypy slice target while the concrete
implementation lives in narrower runtime service/facade modules.
"""

from .runtime_services.auxiliary_state_service import AuxiliaryStateService
from .runtime_services.runtime_control_service import RuntimeControlService
from .runtime_services.runtime_operator_facade import RuntimeOperatorFacade

__all__ = [
    "AuxiliaryStateService",
    "RuntimeControlService",
    "RuntimeOperatorFacade",
]
