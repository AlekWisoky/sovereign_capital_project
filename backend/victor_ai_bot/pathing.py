from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
LEGACY_ROOT_DATA_DIR = ROOT / "data"
CANONICAL_BACKEND_DATA_DIR = BACKEND_ROOT / "data"

_SAFE_CANONICAL_PATH_EXCEPTIONS = (OSError, RuntimeError, ValueError)
_SAFE_DATA_MIGRATION_EXCEPTIONS = (OSError,)


def canonical_data_dir(data_dir: str | None = None) -> str:
    raw = str(data_dir or "").strip()
    if not raw:
        return str(CANONICAL_BACKEND_DATA_DIR)
    raw_norm = raw.replace("\\", "/").lstrip("./")
    if (
        raw_norm in {"data", "backend/data"}
        or raw_norm.startswith("backend/data/")
        or raw_norm.startswith("data/")
    ):
        base = "backend/data" if raw_norm.startswith("backend/data") else "data"
        suffix = raw_norm[len(base) :].lstrip("/")
        return (
            str(CANONICAL_BACKEND_DATA_DIR / suffix) if suffix else str(CANONICAL_BACKEND_DATA_DIR)
        )
    p = Path(raw)
    try:
        if not p.is_absolute():
            candidate = (Path.cwd() / p).resolve()
            cand_norm = candidate.as_posix()
            bad_prefix = (BACKEND_ROOT / "backend" / "data").as_posix()
            root_data = LEGACY_ROOT_DATA_DIR.as_posix()
            if cand_norm == bad_prefix or cand_norm.startswith(bad_prefix + "/"):
                suffix = cand_norm[len(bad_prefix) :].lstrip("/")
                return (
                    str(CANONICAL_BACKEND_DATA_DIR / suffix)
                    if suffix
                    else str(CANONICAL_BACKEND_DATA_DIR)
                )
            if cand_norm == root_data or cand_norm.startswith(root_data + "/"):
                suffix = cand_norm[len(root_data) :].lstrip("/")
                return (
                    str(CANONICAL_BACKEND_DATA_DIR / suffix)
                    if suffix
                    else str(CANONICAL_BACKEND_DATA_DIR)
                )
            return str(candidate)
    except _SAFE_CANONICAL_PATH_EXCEPTIONS:
        pass
    return os.path.abspath(raw)


def migrate_legacy_data_roots() -> dict[str, str]:
    results: dict[str, str] = {}
    legacy = LEGACY_ROOT_DATA_DIR
    canonical = CANONICAL_BACKEND_DATA_DIR
    canonical.mkdir(parents=True, exist_ok=True)
    if legacy.exists() and legacy.is_dir():
        for path in sorted(legacy.rglob("*")):
            rel = path.relative_to(legacy)
            dst = canonical / rel
            try:
                if path.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                    continue
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(path.read_bytes())
                    results[str(rel)] = "migrated"
                else:
                    results[str(rel)] = "preserved_existing"
            except _SAFE_DATA_MIGRATION_EXCEPTIONS as exc:
                results[str(rel)] = f"skipped:{type(exc).__name__}"
    return results


def _cleanup_empty_nested_backend_residue() -> None:
    nested_backend = BACKEND_ROOT / "backend"
    if not nested_backend.exists() or not nested_backend.is_dir():
        return
    removable_dirs = sorted(
        [path for path in nested_backend.rglob("*") if path.is_dir()],
        key=lambda item: len(item.parts),
        reverse=True,
    )
    for directory in removable_dirs:
        try:
            directory.rmdir()
        except OSError:
            continue
    try:
        nested_backend.rmdir()
    except OSError:
        return


_cleanup_empty_nested_backend_residue()
