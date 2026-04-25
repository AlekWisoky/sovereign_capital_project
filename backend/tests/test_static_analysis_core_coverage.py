from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
MYPY_SLICE_INDEX = ROOT / "backend" / "mypy_targets.txt"


def _normalized_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def _slice_targets() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for slice_path in _normalized_lines(MYPY_SLICE_INDEX):
        path = ROOT / slice_path
        out[slice_path] = set(_normalized_lines(path))
    return out


def test_core_paths_are_declared_and_targeted_explicitly() -> None:
    data = tomllib.loads(PYPROJECT.read_text())
    coverage = data["tool"]["static_analysis_coverage"]
    core_paths = set(coverage["core_paths"])
    slices = list(coverage["slices"])
    workflow = WORKFLOW.read_text()
    indexed_slices = _normalized_lines(MYPY_SLICE_INDEX)
    targets_by_slice = _slice_targets()

    assert slices
    assert indexed_slices == slices
    union_targets = set().union(*targets_by_slice.values()) if targets_by_slice else set()
    assert core_paths
    assert core_paths.issubset(union_targets)
    assert "while read -r slice; do" in workflow
    assert 'xargs -a "$slice" ruff check' in workflow
    assert 'xargs -a "$slice" black --check' in workflow
    assert 'mypy @"$slice"' in workflow


def test_governance_reporting_slice_contains_next_ring_contract_consumers() -> None:
    targets_by_slice = _slice_targets()
    reporting_slice = targets_by_slice["backend/mypy_targets/governance_reporting.txt"]

    assert "backend/victor_ai_bot/runtime_legacy_single_chain_views.py" in reporting_slice
    assert "backend/victor_ai_bot/command_center_overlay.py" in reporting_slice
    assert "backend/victor_ai_bot/fioa/runtime.py" in reporting_slice
    assert "backend/victor_ai_bot/analytics/quicksight/datasets.py" in reporting_slice
    assert "backend/victor_ai_bot/analytics/quicksight/dashboards.py" in reporting_slice
    assert "backend/victor_ai_bot/analytics/quicksight/runtime.py" in reporting_slice


def test_auxiliary_dashboard_readiness_slice_contains_expanded_execution_capital_readiness_surfaces() -> (
    None
):
    targets_by_slice = _slice_targets()
    readiness_slice = targets_by_slice["backend/mypy_targets/auxiliary_dashboard_readiness.txt"]

    assert "backend/victor_ai_bot/runtime_services/summary_read_contract.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/telemetry_service.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/cio_service.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/analytics_service.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/runtime_state_facade.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/runtime_operator_facade.py" in readiness_slice
    assert (
        "backend/victor_ai_bot/runtime_services/runtime_multiruntime_state_facade.py"
        in readiness_slice
    )
    assert "backend/victor_ai_bot/runtime_services/launch_service.py" in readiness_slice
    assert "backend/victor_ai_bot/runtime_services/capital_truth_service.py" in readiness_slice
    assert "backend/victor_ai_bot/api_routes/telemetry.py" in readiness_slice
    assert "backend/victor_ai_bot/api_routes/risk_routes.py" in readiness_slice
    assert "backend/victor_ai_bot/api_routes/frontend_routes.py" in readiness_slice
    assert "backend/victor_ai_bot/api_routes/multichain_routes.py" in readiness_slice


def test_dashboard_auxiliary_capital_lifecycle_slice_contains_route_and_withdraw_surfaces() -> None:
    targets_by_slice = _slice_targets()
    lifecycle_slice = targets_by_slice[
        "backend/mypy_targets/dashboard_auxiliary_capital_lifecycle.txt"
    ]

    assert "backend/victor_ai_bot/api_routes/_route_helpers.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/system_routes.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/treasury_extra.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/wealth.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/analytics_routes.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/agents.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/strategies.py" in lifecycle_slice
    assert "backend/victor_ai_bot/api_routes/risk_routes.py" in lifecycle_slice
    assert "backend/victor_ai_bot/runtime_services/withdraw_all_service.py" in lifecycle_slice


def test_optional_family_aux_reads_slice_contains_noncore_read_and_capital_facade_surfaces() -> (
    None
):
    targets_by_slice = _slice_targets()
    extra_slice = targets_by_slice["backend/mypy_targets/optional_family_aux_reads.txt"]

    assert "backend/victor_ai_bot/api_routes/advanced.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/engine_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/governance_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/intelligence_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/overlay_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/ops_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/runtime_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/superstructure_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/command_center_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/evolution.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/operator_command_routes.py" in extra_slice
    assert "backend/victor_ai_bot/api_routes/withdraw_all_routes.py" in extra_slice
    assert "backend/victor_ai_bot/runtime_services/runtime_capital_facade.py" in extra_slice
