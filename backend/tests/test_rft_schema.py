import pytest
from pydantic import ValidationError

from victor_ai_bot.rft.schema import PROPOSAL_SCHEMA_VERSION, ProposalOutput


def _proposal() -> dict:
    return {
        "proposal_schema_version": PROPOSAL_SCHEMA_VERSION,
        "backend_builder_version": "test-builder",
        "opportunity_id": "opp-1",
        "strategy_id": "flashloan_atomic",
        "notional_usd_micro": 250_000_000,
        "send_mode": "protected_rpc",
        "why": ["net_after_gas_positive", "sandbox_not_active"],
        "constraints": {
            "max_slippage_bps": 50,
            "deadline_seconds": 30,
        },
        "mode": {
            "sandbox_only": False,
            "defensive": False,
            "probation": False,
        },
    }


def test_proposal_schema_accepts_valid_payload():
    parsed = ProposalOutput.model_validate(_proposal())
    assert parsed.opportunity_id == "opp-1"
    assert parsed.send_mode == "protected_rpc"
    assert parsed.constraints.max_slippage_bps == 50


def test_proposal_schema_rejects_unknown_keys():
    payload = _proposal()
    payload["unknown"] = 123
    with pytest.raises(ValidationError):
        ProposalOutput.model_validate(payload)


def test_proposal_json_schema_is_draft07_and_forbids_drift():
    schema = ProposalOutput.json_schema_draft07()
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema.get("additionalProperties") is False
