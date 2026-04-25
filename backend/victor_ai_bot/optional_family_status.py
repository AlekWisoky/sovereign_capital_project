from __future__ import annotations

import ast
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
PKG_ROOT = BACKEND / "victor_ai_bot"
OUT_JSON = ROOT / "docs" / "generated" / "optional_family_status.json"
OUT_MD = ROOT / "docs" / "generated" / "optional_family_status.md"
ALLOWED = {"live", "staged", "shadow", "dead"}
CONTRACT_VERSION = "optional_family_status_v2"
CLASSIFICATION_ENGINE = "automatic_runtime_reachability_v3"
STATUS_DERIVATION = [
    "mountedRoutes",
    "runtimeInitialization",
    "importReachability",
    "gatingConditions",
]

CORE_EXCLUDES = {
    "agents",
    "analytics",
    "api_facades",
    "api_routes",
    "engine_control",
    "event_bus",
    "execution_capture",
    "fund_os",
    "governance",
    "internal_prime",
    "persistence",
    "risk_engine",
    "runtime_core",
    "runtime_services",
    "runtime_subsystems",
    "security",
    "strategies",
    "telemetry",
    "treasury",
}

GATING_KEYWORDS = (
    "enable",
    "enabled",
    "disable",
    "disabled",
    "optional",
    "flag",
    "gate",
    "when configured",
    "unless explicitly",
    "allow meta",
    "controls permit",
    "production focus default",
)


@dataclass
class FamilyAccumulator:
    family: str
    path: str
    python_file_count: int
    mounted_routes: set[str] = field(default_factory=set)
    runtime_initialization: set[str] = field(default_factory=set)
    import_reachability: set[str] = field(default_factory=set)
    gating_conditions: set[str] = field(default_factory=set)
    tests: set[str] = field(default_factory=set)
    docs_and_scripts: set[str] = field(default_factory=set)

    def to_row(self) -> dict[str, Any]:
        mounted = sorted(self.mounted_routes)
        runtime = sorted(self.runtime_initialization)
        imports = sorted(self.import_reachability)
        gating = sorted(self.gating_conditions)
        tests = sorted(self.tests)
        docs_scripts = sorted(self.docs_and_scripts)
        ungated_runtime = [item for item in runtime if item not in self.gating_conditions]
        primary_reference_count = len(mounted) + len(runtime) + len(imports) + len(gating)
        supplemental_reference_count = len(tests) + len(docs_scripts)

        if mounted or ungated_runtime:
            status = "live"
            why = "Mounted routes or ungated runtime initialization establish live reachability."
        elif runtime or gating:
            status = "staged"
            why = "Runtime or server reachability exists, but only behind explicit gating or optional initialization."
        elif imports:
            status = "shadow"
            why = "External imports establish reachability, but no mounted-route or runtime-init proof was found."
        else:
            status = "dead"
            why = "No mounted-route, runtime-init, or external import reachability was found outside the subsystem tree."

        if status not in ALLOWED:
            raise SystemExit(f"invalid status for {self.family}: {status}")

        return {
            "family": self.family,
            "path": self.path,
            "status": status,
            "why": why,
            "pythonFileCount": self.python_file_count,
            "referenceCount": primary_reference_count + supplemental_reference_count,
            "primaryEvidenceCount": primary_reference_count,
            "supplementalReferenceCount": supplemental_reference_count,
            "statusInputs": {
                "mountedRoutes": len(mounted),
                "runtimeInitialization": len(runtime),
                "importReachability": len(imports),
                "gatingConditions": len(gating),
            },
            "evidence": {
                "mountedRoutes": mounted,
                "runtimeInitialization": runtime,
                "importReachability": imports,
                "gatingConditions": gating,
                "tests": tests,
                "docsAndScripts": docs_scripts,
            },
        }


def _discover_families() -> dict[str, FamilyAccumulator]:
    found: dict[str, FamilyAccumulator] = {}
    for entry in sorted(PKG_ROOT.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name in CORE_EXCLUDES or entry.name.startswith("__"):
            continue
        py_count = sum(1 for _ in entry.rglob("*.py"))
        if py_count == 0:
            continue
        found[entry.name] = FamilyAccumulator(
            family=entry.name,
            path=str(entry.relative_to(ROOT)),
            python_file_count=py_count,
        )
    return found


def _module_for(path: Path) -> str:
    try:
        rel = path.relative_to(BACKEND).with_suffix("")
    except ValueError:
        rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _resolve_import_module(path: Path, node: ast.ImportFrom) -> str | None:
    current_module = _module_for(path)
    current_package_parts = current_module.split(".")[:-1]
    level = int(node.level or 0)
    module = str(node.module or "")
    if level <= 0:
        return module or None
    keep = len(current_package_parts) - (level - 1)
    if keep < 0:
        return None
    base = current_package_parts[:keep]
    if module:
        return ".".join(base + module.split("."))
    return ".".join(base) if base else None


def _imports_for_file(path: Path) -> set[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(errors="ignore")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve_import_module(path, node)
            if resolved:
                modules.add(resolved)
    return modules


def _relevant_files() -> list[Path]:
    roots = [
        PKG_ROOT,
        ROOT / "backend" / "tests",
        ROOT / "scripts",
        ROOT / "docs",
        ROOT / "mobile",
        ROOT / ".github",
    ]
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.rglob("*.py"))
    return files


def _mounted_route_files() -> set[str]:
    from victor_ai_bot.server import app

    files: set[str] = set()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        src = inspect.getsourcefile(endpoint)
        if not src:
            continue
        try:
            files.add(str(Path(src).relative_to(ROOT)))
        except ValueError:
            continue
    return files


def _has_gating(path: Path, family: str) -> bool:
    lines = path.read_text(encoding="utf-8", errors="ignore").lower().splitlines()
    family_l = family.lower()
    for idx, line in enumerate(lines):
        if family_l not in line:
            continue
        window = " ".join(lines[max(0, idx - 1) : min(len(lines), idx + 2)])
        if any(keyword in window for keyword in GATING_KEYWORDS):
            return True
    return False


def build_optional_family_status() -> dict[str, Any]:
    families = _discover_families()
    mounted_route_files = _mounted_route_files()
    files = _relevant_files()

    for path in files:
        rel = str(path.relative_to(ROOT))
        imports = _imports_for_file(path)
        for family, acc in families.items():
            family_module = f"victor_ai_bot.{family}"
            named_route_module = f"victor_ai_bot.api_routes.{family}"
            imports_family = any(
                mod == family_module
                or mod.startswith(f"{family_module}.")
                or mod == named_route_module
                for mod in imports
            )
            is_named_route_file = rel == f"backend/victor_ai_bot/api_routes/{family}.py"
            if not imports_family and not is_named_route_file:
                continue

            family_dir = ROOT / acc.path
            try:
                path.relative_to(family_dir)
                continue
            except ValueError:
                pass

            if imports_family:
                acc.import_reachability.add(rel)
            if is_named_route_file and rel in mounted_route_files:
                acc.mounted_routes.add(rel)
            if imports_family and rel in mounted_route_files:
                acc.mounted_routes.add(rel)
            if (
                rel == "backend/victor_ai_bot/server.py"
                or rel.startswith("backend/victor_ai_bot/runtime_services/")
                or rel.startswith("backend/victor_ai_bot/runtime_core/")
                or rel.startswith("backend/victor_ai_bot/runtime_subsystems/")
            ):
                if imports_family:
                    acc.runtime_initialization.add(rel)
                    if _has_gating(path, family):
                        acc.gating_conditions.add(rel)
            elif rel.startswith("backend/tests/"):
                if imports_family:
                    acc.tests.add(rel)
            elif (
                rel.startswith("docs/")
                or rel.startswith("scripts/")
                or rel.startswith("mobile/")
                or rel.startswith(".github/")
            ):
                if imports_family:
                    acc.docs_and_scripts.add(rel)

    rows = [acc.to_row() for _, acc in sorted(families.items())]
    status_counts = {status: 0 for status in sorted(ALLOWED)}
    for row in rows:
        status_counts[row["status"]] += 1
    return {
        "contractVersion": CONTRACT_VERSION,
        "classificationEngine": CLASSIFICATION_ENGINE,
        "statusDerivation": STATUS_DERIVATION,
        "evidencePolicy": "status derives only from mounted routes, runtime initialization, import reachability, and gating conditions; tests and docs are supplemental evidence only",
        "summary": {
            "familyCount": len(rows),
            "statusCounts": status_counts,
        },
        "families": rows,
    }


def render_optional_family_status_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Optional family status",
        "",
        f"- Contract: {payload['contractVersion']}",
        f"- Classification engine: {payload['classificationEngine']}",
        f"- Evidence policy: {payload['evidencePolicy']}",
        f"- Status counts: {json.dumps(payload['summary']['statusCounts'], sort_keys=True)}",
        "",
        "| Family | Status | Py files | Refs | Primary evidence | Mounted | Runtime init | Imports | Gating |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["families"]:
        inputs = row["statusInputs"]
        lines.append(
            f"| {row['family']} | {row['status']} | {row['pythonFileCount']} | {row['referenceCount']} | {row['primaryEvidenceCount']} | {inputs['mountedRoutes']} | {inputs['runtimeInitialization']} | {inputs['importReachability']} | {inputs['gatingConditions']} |"
        )
        lines.append("")
        lines.append(row["why"])
        lines.append("")
        for key in (
            "mountedRoutes",
            "runtimeInitialization",
            "importReachability",
            "gatingConditions",
            "tests",
            "docsAndScripts",
        ):
            items = row["evidence"][key]
            if items:
                lines.append(f"- **{row['family']} {key}**")
                for item in items[:8]:
                    lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)


def optional_family_status_is_fresh(existing: dict[str, Any], live: dict[str, Any]) -> bool:
    return existing == live


def build_optional_family_status_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "contractVersion": payload["contractVersion"],
        "classificationEngine": payload["classificationEngine"],
        "familyCount": payload["summary"]["familyCount"],
        "statusCounts": payload["summary"]["statusCounts"],
    }


def write_optional_family_status() -> dict[str, Any]:
    payload = build_optional_family_status()
    json_text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    md_text = render_optional_family_status_markdown(payload)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json_text, encoding="utf-8")
    OUT_MD.write_text(md_text, encoding="utf-8")
    return payload
