from __future__ import annotations

import inspect

from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService
from victor_ai_bot.runtime_services.canonical_receipt_service import CanonicalReceiptService
from victor_ai_bot.runtime_services.runtime_institutional_init import initialize_runtime_institutional_stack


def test_runtime_institutional_stack_installs_canonical_settlement_services():
    source = inspect.getsource(initialize_runtime_institutional_stack)
    assert "runtime._receipt_service = CanonicalReceiptService()" in source
    assert "runtime._capital_write_service = CanonicalCapitalWriteService()" in source
    assert CanonicalReceiptService.__mro__[1].__name__ == "ReceiptService"
    assert CanonicalCapitalWriteService.__mro__[1].__name__ == "CapitalWriteService"
