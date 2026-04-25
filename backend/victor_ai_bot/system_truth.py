from __future__ import annotations

import ast
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .fund_os.health_states import HealthState
from .fund_os.launch_modes import DEFAULT_ACTIVATION_ORDER, LaunchMode
from .fund_os.mandate_registry import fund_mandate_registry
from .security.permissions import Capability
from .pathing import CANONICAL_BACKEND_DATA_DIR, LEGACY_ROOT_DATA_DIR
from .repo_inspection import list_broad_exception_handlers

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
MOBILE_ROOT = ROOT / "mobile"
DOCS_ROOT = ROOT / "docs"
GENERATED_DOCS_DIR = "docs/generated"


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def _generated_ts_ms() -> int:
    src = os.environ.get("SOURCE_DATE_EPOCH")
    if src:
        try:
            return int(float(src) * 1000)
        except (TypeError, ValueError, OverflowError):
            pass
    return int(time.time() * 1000)


def _generated_ts_iso(ts_ms: int) -> str:
    return (
        datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    )


def _route_inventory() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    import sys

    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from victor_ai_bot.server import app

    rows: List[Dict[str, Any]] = []
    counts: Counter[tuple[str, str]] = Counter()
    summary: Counter[str] = Counter()
    for route in list(app.routes):
        path = str(getattr(route, "path", "") or "")
        route_type = type(route).__name__
        summary["app_route_count"] += 1
        if route_type == "APIWebSocketRoute":
            summary["websocket_route_count"] += 1
        methods = sorted(
            m for m in list(getattr(route, "methods", []) or []) if m not in {"HEAD", "OPTIONS"}
        )
        endpoint = getattr(route, "endpoint", None)
        module = str(getattr(endpoint, "__module__", "") or "")
        handler = str(getattr(route, "name", "") or getattr(endpoint, "__name__", "") or "")
        if not path or not methods:
            continue
        if module.startswith("fastapi."):
            summary["framework_route_count"] += len(methods)
        else:
            summary["application_route_count"] += len(methods)
        for method in methods:
            row = {
                "method": method,
                "path": path,
                "handler": handler,
                "module": module,
                "route_type": route_type,
            }
            rows.append(row)
            counts[(method, path)] += 1
    rows.sort(key=lambda x: (x["path"], x["method"], x["module"], x["handler"]))
    duplicates = [
        {"method": method, "path": path, "count": count}
        for (method, path), count in sorted(counts.items())
        if count > 1
    ]
    summary["http_route_count"] = len(rows)
    return rows, duplicates, dict(summary)


def _test_inventory() -> Dict[str, Any]:
    backend_tests = sorted(p.name for p in (BACKEND_ROOT / "tests").glob("test_*.py"))
    mobile_tests = sorted(p.name for p in (MOBILE_ROOT / "tests").glob("*.test.ts"))
    return {
        "backend_test_files": len(backend_tests),
        "mobile_test_files": len(mobile_tests),
        "backend_test_names": backend_tests,
        "mobile_test_names": mobile_tests,
    }


def _broad_exception_inventory() -> Dict[str, Any]:
    files = [
        BACKEND_ROOT / "victor_ai_bot" / "runtime_legacy.py",
        BACKEND_ROOT / "victor_ai_bot" / "api_legacy.py",
    ]
    total = 0
    by_file: Dict[str, int] = {}
    legacy_sites: Dict[str, List[Dict[str, Any]]] = {}
    for file in files:
        sites = list_broad_exception_handlers(file, relative_to=ROOT)
        rel = str(file.relative_to(ROOT))
        by_file[rel] = len(sites)
        legacy_sites[rel] = sites
        total += len(sites)
    backend_sites: List[Dict[str, Any]] = []
    for path in (BACKEND_ROOT / "victor_ai_bot").rglob("*.py"):
        backend_sites.extend(list_broad_exception_handlers(path, relative_to=ROOT))
    backend_sites.sort(key=lambda item: (str(item["path"]), int(item["lineno"])))
    return {
        "legacy_files": by_file,
        "legacy_sites": legacy_sites,
        "legacy_total": total,
        "backend_total": len(backend_sites),
        "backend_sites": backend_sites,
    }


def _service_inventory() -> Dict[str, Any]:
    runtime_services = sorted(
        p.stem
        for p in (BACKEND_ROOT / "victor_ai_bot" / "runtime_services").glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )
    api_routes = sorted(
        p.stem
        for p in (BACKEND_ROOT / "victor_ai_bot" / "api_routes").glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith("_")
    )
    runtime_service_count = len(runtime_services)
    api_route_module_count = len(api_routes)
    return {
        "runtime_services": runtime_services,
        "api_routes": api_routes,
        "runtime_service_count": runtime_service_count,
        "runtime_service_module_count": runtime_service_count,
        "api_route_module_count": api_route_module_count,
    }


def _runtime_bundle_definition_count() -> int:
    runtime_legacy = BACKEND_ROOT / "victor_ai_bot" / "runtime_legacy.py"
    module = ast.parse(runtime_legacy.read_text(encoding="utf-8"))
    return sum(
        1 for node in module.body if isinstance(node, ast.ClassDef) and node.name == "RuntimeBundle"
    )


def build_system_truth() -> Dict[str, Any]:
    routes, duplicates, route_summary = _route_inventory()
    tests = _test_inventory()
    services = _service_inventory()
    exception_inventory = _broad_exception_inventory()
    ts_ms = _generated_ts_ms()
    generated_at_iso = _generated_ts_iso(ts_ms)
    truth = {
        # flat canonical fields
        "generated_at": generated_at_iso,
        "generated_at_ms": ts_ms,
        "generated_at_iso": generated_at_iso,
        "docs_generated_dir": GENERATED_DOCS_DIR,
        "thin_shell_runtime_py_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "runtime.py"),
        "thin_shell_api_py_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "api.py"),
        "backend_test_file_count": tests["backend_test_files"],
        "mobile_test_file_count": tests["mobile_test_files"],
        "backend_test_files": tests["backend_test_names"],
        "mobile_test_files": tests["mobile_test_names"],
        "launch_modes": [x.value for x in LaunchMode],
        "health_states": [x.value for x in HealthState],
        "activation_order": list(DEFAULT_ACTIVATION_ORDER),
        "capabilities": [c.value for c in Capability],
        "family_mandates": fund_mandate_registry().get("families") or {},
        "route_inventory": routes,
        "route_count": route_summary.get("app_route_count", len(list(routes))),
        "route_count_basis": "app_routes",
        "http_route_count": route_summary.get("http_route_count", len(routes)),
        "http_route_count_basis": "http_methods_excluding_head_options",
        "application_route_count": route_summary.get("application_route_count", 0),
        "framework_route_count": route_summary.get("framework_route_count", 0),
        "app_route_count": route_summary.get("app_route_count", 0),
        "websocket_route_count": route_summary.get("websocket_route_count", 0),
        "duplicate_routes": duplicates,
        "duplicate_route_count": len(duplicates),
        "duplicate_route_policy": "deduplicated_mount_surface",
        "runtime_services": services["runtime_services"],
        "canonical_data_root": str(CANONICAL_BACKEND_DATA_DIR.relative_to(ROOT)),
        "legacy_data_roots": [str(LEGACY_ROOT_DATA_DIR.relative_to(ROOT))],
        "runtime_service_count": services["runtime_service_count"],
        "runtime_service_module_count": services["runtime_service_module_count"],
        "api_route_modules": services["api_routes"],
        "api_route_module_count": services["api_route_module_count"],
        "runtime_legacy_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "runtime_legacy.py"),
        "api_legacy_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "api_legacy.py"),
        "runtime_bundle_definition_count": _runtime_bundle_definition_count(),
        "runtime_legacy_broad_except_count": exception_inventory["legacy_files"].get("backend/victor_ai_bot/runtime_legacy.py", 0),
        "api_legacy_broad_except_count": exception_inventory["legacy_files"].get("backend/victor_ai_bot/api_legacy.py", 0),
        "legacy_broad_except_count": exception_inventory["legacy_total"],
        "backend_broad_except_count": exception_inventory["backend_total"],
        "legacy_broad_exception_sites": exception_inventory["legacy_sites"],
        "backend_broad_exception_sites": exception_inventory["backend_sites"],
        "broad_exception_inventory": exception_inventory,
        "contract_validation_command": "./scripts/verify_contracts.sh",
        "contract_validation_workflow": "contracts/README.md + GitHub Actions foundry job",
        # legacy compatibility mirrors
        "generatedAt": generated_at_iso,
        "generatedAtMs": ts_ms,
        "generatedAtIso": generated_at_iso,
        "thin_shells": {
            "runtime_py_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "runtime.py"),
            "api_py_lines": _line_count(BACKEND_ROOT / "victor_ai_bot" / "api.py"),
        },
        "tests": tests,
        "service_inventory": services,
    }
    return truth


def truth_freshness_snapshot(truth: Dict[str, Any]) -> Dict[str, Any]:
    """Return the deterministic subset used to verify generated truth freshness."""
    keys = [
        "thin_shell_runtime_py_lines",
        "thin_shell_api_py_lines",
        "backend_test_file_count",
        "mobile_test_file_count",
        "route_count",
        "route_count_basis",
        "http_route_count",
        "http_route_count_basis",
        "application_route_count",
        "framework_route_count",
        "app_route_count",
        "websocket_route_count",
        "runtime_legacy_lines",
        "api_legacy_lines",
        "runtime_bundle_definition_count",
        "runtime_legacy_broad_except_count",
        "api_legacy_broad_except_count",
        "legacy_broad_except_count",
        "backend_broad_except_count",
        "legacy_broad_exception_sites",
        "backend_broad_exception_sites",
        "canonical_data_root",
        "duplicate_route_count",
        "duplicate_route_policy",
        "runtime_service_count",
        "runtime_service_module_count",
        "api_route_module_count",
        "launch_modes",
        "health_states",
        "activation_order",
        "capabilities",
        "runtime_services",
        "api_route_modules",
        "family_mandates",
        "duplicate_routes",
        "route_inventory",
        "backend_test_files",
        "mobile_test_files",
        "contract_validation_command",
        "contract_validation_workflow",
    ]
    return {key: truth.get(key) for key in keys}


def generated_truth_is_fresh(existing: Dict[str, Any], live: Dict[str, Any]) -> bool:
    return truth_freshness_snapshot(existing) == truth_freshness_snapshot(live)


def render_system_truth_markdown(truth: Dict[str, Any]) -> str:
    lines = [
        "# System Truth",
        "",
        f"- generated_at: {truth['generated_at']}",
        f"- generated_at_ms: {truth['generated_at_ms']}",
        f"- generated_at_iso: {truth['generated_at_iso']}",
        f"- thin_shell_runtime_py_lines: {truth['thin_shell_runtime_py_lines']}",
        f"- thin_shell_api_py_lines: {truth['thin_shell_api_py_lines']}",
        f"- backend_test_file_count: {truth['backend_test_file_count']}",
        f"- mobile_test_file_count: {truth['mobile_test_file_count']}",
        f"- route_count: {truth['route_count']}",
        f"- route_count_basis: {truth['route_count_basis']}",
        f"- http_route_count: {truth['http_route_count']}",
        f"- http_route_count_basis: {truth['http_route_count_basis']}",
        f"- application_route_count: {truth['application_route_count']}",
        f"- framework_route_count: {truth['framework_route_count']}",
        f"- app_route_count: {truth['app_route_count']}",
        f"- websocket_route_count: {truth['websocket_route_count']}",
        f"- runtime_legacy_lines: {truth['runtime_legacy_lines']}",
        f"- api_legacy_lines: {truth['api_legacy_lines']}",
        f"- runtime_bundle_definition_count: {truth['runtime_bundle_definition_count']}",
        f"- runtime_legacy_broad_except_count: {truth['runtime_legacy_broad_except_count']}",
        f"- api_legacy_broad_except_count: {truth['api_legacy_broad_except_count']}",
        f"- legacy_broad_except_count: {truth['legacy_broad_except_count']}",
        f"- backend_broad_except_count: {truth['backend_broad_except_count']}",
        f"- canonical_data_root: {truth['canonical_data_root']}",
        f"- duplicate_route_count: {truth['duplicate_route_count']}",
        f"- duplicate_route_policy: {truth['duplicate_route_policy']}",
        f"- contract_validation_command: {truth['contract_validation_command']}",
        "",
        "## Broad exception sites",
    ]
    backend_sites = truth.get("backend_broad_exception_sites") or []
    if backend_sites:
        lines.extend([f"- {site['path']}:{site['lineno']} {site['line']}" for site in backend_sites])
    else:
        lines.append("- none")
    lines.extend(["", "## Runtime services"])
    lines.extend([f"- {name}" for name in truth["runtime_services"]])
    lines.extend(["", "## API route modules"])
    lines.extend([f"- {name}" for name in truth["api_route_modules"]])
    lines.extend(["", "## Launch modes"])
    lines.extend([f"- {mode}" for mode in truth["launch_modes"]])
    lines.extend(["", "## Health states"])
    lines.extend([f"- {state}" for state in truth["health_states"]])
    lines.extend(["", "## Families"])
    for family, mandate in sorted((truth.get("family_mandates") or {}).items()):
        lines.append(
            f"- {family}: promotion={mandate.get('promotion_status', '')}, stages={', '.join(list(mandate.get('stage_restrictions') or []))}"
        )
    lines.extend(["", "## Duplicate routes"])
    if truth["duplicate_routes"]:
        for item in truth["duplicate_routes"]:
            lines.append(f"- {item['method']} {item['path']} x{item['count']}")
    else:
        lines.append("- none")
    lines.extend(["", "## Routes"])
    for item in truth["route_inventory"][:60]:
        lines.append(f"- {item['method']} {item['path']} ({item['module']}.{item['handler']})")
    return "\n".join(lines) + "\n"


def write_system_truth(*, out_dir: str | Path | None = None) -> Dict[str, Any]:
    truth = build_system_truth()
    target = Path(out_dir) if out_dir is not None else DOCS_ROOT / "generated"
    target.mkdir(parents=True, exist_ok=True)
    (target / "system_truth.json").write_text(
        json.dumps(truth, indent=2, sort_keys=True), encoding="utf-8"
    )
    (target / "system_truth.md").write_text(render_system_truth_markdown(truth), encoding="utf-8")
    return truth
