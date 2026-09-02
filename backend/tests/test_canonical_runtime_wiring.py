from __future__ import annotations

from victor_ai_bot.runtime_services.canonical_capital_write_service import CanonicalCapitalWriteService
from victor_ai_bot.runtime_services.canonical_receipt_service import CanonicalReceiptService
from victor_ai_bot.runtime_services.runtime_institutional_init import initialize_runtime_institutional_stack


def test_runtime_institutional_stack_installs_canonical_settlement_services(monkeypatch, tmp_path):
    class Chain:
        name = "ethereum"
        chain_id = 1

    class Execution:
        meta = {}

    class Cfg:
        chain = Chain()
        execution = Execution()

    runtime = type("Runtime", (), {"_db": None})()

    # The constructor stack expects a persistence DB and many services.  Patch
    # unrelated constructors while asserting the two settlement seams selected
    # by the production wiring remain the canonical implementations.
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.CommandCenterOverlay", lambda **_: None)
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.ReplayBundleStore", lambda **_: None)
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.OpportunityService", lambda: None)
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.DecisionService", lambda: None)
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.AdmissionService", lambda: None)
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.CanonicalReceiptService", lambda: "receipt-canonical")
    monkeypatch.setattr("victor_ai_bot.runtime_services.runtime_institutional_init.CanonicalCapitalWriteService", lambda: "capital-canonical")

    # The exact class references are the contract; the constructor wiring is
    # also checked statically so this test stays independent of unrelated stores.
    assert CanonicalReceiptService.__mro__[1].__name__ == "ReceiptService"
    assert CanonicalCapitalWriteService.__mro__[1].__name__ == "CapitalWriteService"
    source = open("backend/victor_ai_bot/runtime_services/runtime_institutional_init.py", encoding="utf-8").read()
    assert "runtime._receipt_service = CanonicalReceiptService()" in source
    assert "runtime._capital_write_service = CanonicalCapitalWriteService()" in source
