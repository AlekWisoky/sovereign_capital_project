from __future__ import annotations

import asyncio
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from victor_ai_bot.api_routes.system_routes import _system_summary_payload
from victor_ai_bot.runtime_services.operator_summary_service import OperatorSummaryService
from victor_ai_bot.runtime_services.summary_read_contract import SUMMARY_READ_CONTRACT_VERSION
from test_capital_summary_canonicalization import _Runtime as _OperatorRuntime
from test_dashboard_capital_contract_adoption import _DashboardRuntime
from test_fund_summary_component_sync_maintenance import _FundSummarySuccessRuntime


def test_fund_summary_exposes_canonical_summary_contract():
    runtime = _FundSummarySuccessRuntime()
    payload = runtime._fund_service.summary(runtime)
    assert payload["summaryContract"]["contractVersion"] == SUMMARY_READ_CONTRACT_VERSION
    assert payload["summaryContract"]["truthFamily"] == "fund"
    assert payload["summaryContract"]["readModel"] == "fund_summary_projection_v1"


def test_operator_summary_exposes_canonical_summary_contract():
    runtime = _OperatorRuntime()
    payload = asyncio.run(OperatorSummaryService().build_snapshot(runtime))
    assert payload["summaryContract"]["contractVersion"] == SUMMARY_READ_CONTRACT_VERSION
    assert payload["summaryContract"]["truthFamily"] == "operator"
    assert payload["summaryContract"]["readModel"] == "operator_summary_projection_v1"


def test_command_center_and_system_summaries_expose_canonical_summary_contracts():
    runtime = _DashboardRuntime()
    command_payload = asyncio.run(runtime._command_center_service.snapshot(runtime))
    system_payload = _system_summary_payload(runtime)
    assert command_payload["summaryContract"]["contractVersion"] == SUMMARY_READ_CONTRACT_VERSION
    assert command_payload["summaryContract"]["truthFamily"] == "command_center"
    assert system_payload["summaryContract"]["contractVersion"] == SUMMARY_READ_CONTRACT_VERSION
    assert system_payload["summaryContract"]["truthFamily"] == "system"
